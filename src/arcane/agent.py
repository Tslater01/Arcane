import logging
from pathlib import Path

# Import our custom modules
from .analysis import run_analysis
from .planning import run_plan
from .validator import run_validation, PASS

# We will add 'run_retry_plan' to planning.py in our *next* step.
# For now, we'll import it, and Python will be fine until we run the code.
try:
    from .planning import run_retry_plan
except ImportError:
    # This is a placeholder so the file is valid Python
    # We will write this function in the next step.
    log.warning("run_retry_plan not yet defined in planning.py. This is expected.")
    run_retry_plan = None 

log = logging.getLogger(__name__)

MAX_RETRIES = 3 # We will allow 3 total attempts

class ArcaneAgent:
    """
    The main agent class that orchestrates the MAPE-K loop.
    Now with a self-healing retry loop.
    """
    def __init__(self, config):
        self.config = config
        self.agent_name = "ArcaneAgent"
        log.info("ArcaneAgent initialized with retry logic.")

    def run_fix(self, bug_path: Path, algorithm_name: str):
        """
        Runs the full Monitor-Analyze-Plan-Execute (MAPE) loop on a single bug.
        """
        log.info(f"===== Starting ARCANE run for: {algorithm_name} =====")
        
        # --- MONITOR (M) ---
        try:
            original_code = bug_path.read_text(encoding="utf-8")
            code_directory = bug_path.parent
        except Exception as e:
            log.error(f"Failed to read bug file at {bug_path}: {e}")
            return self._create_result(algorithm_name, "FAIL_LOAD", None, None)

        # --- ANALYZE (A) ---
        metrics_dict = run_analysis(code_directory, self.config)
        metrics_json = str(metrics_dict) if metrics_dict else "N/A"

        # --- PLAN (P) & EXECUTE (E) LOOP ---
        current_patch = None
        validation_status = "FAIL_PLAN"
        error_message = "No patch generated yet."
        
        for attempt in range(MAX_RETRIES):
            log.info(f"Starting attempt {attempt + 1}/{MAX_RETRIES} for {algorithm_name}...")
            
            if attempt == 0:
                # First attempt: use the "brainstorm" plan
                current_patch = run_plan(original_code, metrics_json, self.config)
            else:
                # Subsequent attempts: use the "retry" plan
                if not run_retry_plan:
                    log.error("run_retry_plan is not defined! Stopping retry loop.")
                    break # Safety check
                    
                log.info(f"Retrying with error context: {error_message}")
                current_patch = run_retry_plan(
                    original_code, 
                    current_patch, # The patch that just failed
                    error_message, 
                    self.config
                )

            if not current_patch:
                log.error("Planning step failed to generate a patch.")
                validation_status = "FAIL_PLAN"
                continue # Go to the next retry, if any

            # --- EXECUTE (E) ---
            # Our upgraded validator returns (status, error)
            status, error = run_validation(current_patch, str(bug_path), algorithm_name)
            validation_status = status # Save the latest status
            error_message = error    # Save the latest error

            if status == PASS:
                log.info(f"SUCCESS! Patch passed validation on attempt {attempt + 1}.")
                break # Exit the retry loop
            else:
                log.warning(f"Attempt {attempt + 1} failed. Status: {status}.")
                # Loop continues to the next attempt
        
        # --- (KNOWLEDGE) & FINAL ANALYSIS ---
        log.info(f"===== Run complete for: {algorithm_name}. Final Status: {validation_status} =====")
        
        final_metrics_dict = None
        if validation_status == PASS:
            log.info("Patch passed. Running final analysis for RQ2...")
            final_metrics_dict = run_analysis(code_directory, self.config)
        
        return self._create_result(
            algorithm_name, 
            validation_status, 
            metrics_dict, 
            final_metrics_dict,
            current_patch if validation_status == PASS else None,
            error_message # Pass the final error message
        )

    def _create_result(self, algo_name, status, before_metrics, after_metrics, patch=None, error=None):
        """Helper to format the final result dictionary."""
        return {
            "agent": self.agent_name,
            "algorithm": algo_name,
            "status": status,
            "patch": patch,
            "metrics_before": before_metrics,
            "metrics_after": after_metrics,
            "error_message": error
        }