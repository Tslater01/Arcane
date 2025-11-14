import logging
from pathlib import Path

# Import our custom modules
from .analysis import run_analysis
from .planning import run_plan
from .validator import run_validation, PASS

log = logging.getLogger(__name__)

class ArcaneAgent:
    """
    The main agent class that orchestrates the MAPE-K loop.
    """
    def __init__(self, config):
        self.config = config
        log.info("ArcaneAgent initialized.")

    def run_fix(self, bug_path: Path, algorithm_name: str):
        """
        Runs the full Monitor-Analyze-Plan-Execute (MAPE) loop on a single bug.

        :param bug_path: The Path object pointing to the buggy .java file.
        :param algorithm_name: The lowercase name of the algorithm (e.g., "breadth_first_search").
        :return: A dictionary containing the results of the run.
        """
        log.info(f"===== Starting ARCANE run for: {algorithm_name} =====")

        # MONITOR (M)
        # We "monitor" by loading the file's current state.
        try:
            original_code = bug_path.read_text(encoding="utf-8")
            code_directory = bug_path.parent
        except Exception as e:
            log.error(f"Failed to read bug file at {bug_path}: {e}")
            return self._create_result(algorithm_name, "FAIL_LOAD", None, None)

        # ANALYZE (A) 
        # Get architectural metrics from SonarCloud
        metrics_dict = run_analysis(code_directory, self.config)
        metrics_json = str(metrics_dict) if metrics_dict else None # Convert to string for prompt

        # PLAN (P) 
        # Generate a patch using the code and metrics
        patch_code = run_plan(original_code, metrics_json, self.config)

        if not patch_code:
            log.error("Planning step failed to generate a patch.")
            return self._create_result(algorithm_name, "FAIL_PLAN", metrics_json, None)

        # EXECUTE (E) 
        # Validate the generated patch
        validation_result = run_validation(patch_code, str(bug_path), algorithm_name)

        # (KNOWLEDGE is the log file + this return value)
        log.info(f"===== Run complete for: {algorithm_name}. Result: {validation_result} =====")

        # ANALYZE (A) - Post-Patch
        # If the patch passed, re-run analysis to get "after" metrics for RQ2
        final_metrics_dict = None
        if validation_result == PASS:
            log.info("Patch passed. Running final analysis for RQ2...")
            final_metrics_dict = run_analysis(code_directory, self.config)

        return self._create_result(
            algorithm_name, 
            validation_result, 
            metrics_dict, 
            final_metrics_dict,
            patch_code if validation_result == PASS else None
        )

    def _create_result(self, algo_name, status, before_metrics, after_metrics, patch=None):
        """Helper to format the final result dictionary."""
        return {
            "agent": "ArcaneAgent",
            "algorithm": algo_name,
            "status": status,
            "patch": patch,
            "metrics_before": before_metrics,
            "metrics_after": after_metrics
        }