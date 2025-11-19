import sys
import logging
import hydra
import pandas as pd
from pathlib import Path
from omegaconf import DictConfig
from typing import List, Tuple, Set
from tqdm import tqdm  # <-- 1. IMPORT TQDM

# --- Project-level Imports ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

try:
    from arcane.agent import ArcaneAgent
    from arcane.baselines import BaselineNaive, BaselineAware
except ImportError as e:
    print(f"FATAL: Could not import arcane modules: {e}")
    print("This is likely because you are running from the wrong directory.")
    print("Please run this script from the main 'ARCANE' project root.")
    sys.exit(1)

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

RESULTS_FILE = "results.csv"
JSON_TESTCASES_DIR = "json_testcases"
PYTHON_PROGRAMS_DIR = "python_programs"
RESULTS_COLUMNS = [
    "agent", "algorithm", "status", "patch", 
    "metrics_before", "metrics_after", "error_message"
]

def load_benchmark(benchmark_path: Path) -> List[Tuple[str, Path]]:
    """
    Finds all valid, runnable Python bugs in the QuixBugs benchmark.
    """
    json_dir = benchmark_path / JSON_TESTCASES_DIR
    py_dir = benchmark_path / PYTHON_PROGRAMS_DIR
    bugs_to_run = []

    if not json_dir.exists() or not py_dir.exists():
        log.error(f"Benchmark directories not found at {benchmark_path}")
        return []

    for json_file in json_dir.glob("*.json"):
        algorithm_name_lower = json_file.stem 
        py_file_name = algorithm_name_lower + ".py"
        py_file_path = py_dir / py_file_name
        
        if py_file_path.exists():
            bugs_to_run.append((algorithm_name_lower, py_file_path))
        else:
            log.warning(f"Found test {json_file.name} but missing Python file: {py_file_name}")
            
    log.info(f"Found {len(bugs_to_run)} total valid bugs.")
    
    # --- Full Run ---
    return bugs_to_run


def load_processed_bugs(results_path: Path) -> Set[Tuple[str, str]]:
    """Loads the results.csv to find which (agent, algorithm) pairs are done."""
    if not results_path.exists():
        pd.DataFrame(columns=RESULTS_COLUMNS).to_csv(results_path, index=False)
        return set()
        
    try:
        df = pd.read_csv(results_path)
        if df.empty:
            return set()
        processed = set(zip(df['agent'], df['algorithm']))
        log.info(f"Loaded {len(processed)} existing results from {RESULTS_FILE}.")
        return processed
    except (pd.errors.EmptyDataError, FileNotFoundError):
        log.warning(f"{RESULTS_FILE} is empty or not found. Starting from scratch.")
        pd.DataFrame(columns=RESULTS_COLUMNS).to_csv(results_path, index=False)
        return set()


def save_result(results_path: Path, result_data: dict):
    """Appends a single result to the results.csv file."""
    try:
        complete_data = {col: result_data.get(col) for col in RESULTS_COLUMNS}
        new_row_df = pd.DataFrame([complete_data])
        new_row_df.to_csv(results_path, mode='a', header=False, index=False)
    except Exception as e:
        log.error(f"Failed to save result for {result_data.get('algorithm')}: {e}")


@hydra.main(config_path="../configs", config_name="config", version_base=None)
def run_evaluation(cfg: DictConfig):
    """
    Main experiment script orchestrated by Hydra.
    """
    
    original_cwd = Path(hydra.utils.get_original_cwd())
    benchmark_path = original_cwd / cfg.paths.test_benchmark
    results_path = Path.cwd() / RESULTS_FILE 
    
    log.info("Starting ARCANE evaluation...")
    log.info(f"Benchmark Path: {benchmark_path}")
    log.info(f"Results will be saved to: {results_path}")

    all_bugs = load_benchmark(benchmark_path)
    processed_bugs = load_processed_bugs(results_path)
    
    agents = [
        ArcaneAgent(cfg),
        BaselineAware(cfg),
        BaselineNaive(cfg)
    ]
    
    # --- 2. BUILD THE MASTER TASK LIST ---
    # Create a master list of all (bug, agent) pairs
    all_tasks = [
        (algorithm_name, bug_file_path, agent)
        for (algorithm_name, bug_file_path) in all_bugs
        for agent in agents
    ]
    
    # Filter out tasks that are already processed
    tasks_to_run = []
    for algorithm_name, bug_file_path, agent in all_tasks:
        if (agent.agent_name, algorithm_name) in processed_bugs:
            log.info(f"Skipping {agent.agent_name} for {algorithm_name} (already processed).")
        else:
            tasks_to_run.append((algorithm_name, bug_file_path, agent))
            
    log.info(f"Total tasks: {len(all_tasks)}. Remaining tasks: {len(tasks_to_run)}")
    
    # --- 3. RUN THE MAIN LOOP WITH TQDM ---
    # Wrap 'tasks_to_run' with tqdm for a progress bar
    for algorithm_name, bug_file_path, agent in tqdm(tasks_to_run, desc="Overall Experiment Progress"):
        
        log.info(f"========== Processing Bug: {algorithm_name} | Agent: {agent.agent_name} ==========")
        agent_name = agent.agent_name
        
        try:
            # Run the full fix/validation loop
            result = agent.run_fix(bug_file_path, algorithm_name)
            
            # Save the result immediately
            save_result(results_path, result)
            
        except Exception as e:
            # Catch any critical errors during an agent's run
            log.error(f"CRITICAL ERROR running {agent_name} on {algorithm_name}: {e}", exc_info=True)
            result = {
                "agent": agent_name, 
                "algorithm": algorithm_name, 
                "status": "CRASH"
            }
            save_result(results_path, result)

    log.info("========== Evaluation Complete ==========")
    log.info(f"All results saved to: {results_path}")


if __name__ == "__main__":
    run_evaluation()