import logging
from pathlib import Path

# Import our custom modules
from .planning import run_plan, run_retry_plan
from .validator import run_validation, PASS

log = logging.getLogger(__name__)

MAX_RETRIES = 3 # We will allow 3 total attempts

class ArcaneAgent:
    """
    The main agent class that orchestrates the retry loop (Python-only).
    """
    def __init__(self, config):
        self.config = config
        self.agent_name = "ArcaneAgent"
        log.info("ArcaneAgent initialized (Retry-Loop-Only).")

    def run_fix(self, bug_path: Path, algorithm_name: str):
        """
        Runs the full Monitor-Plan-Execute (MPE) retry loop on a single bug.
        """
        log.info(f"===== Starting ARCANE run for: {algorithm_name} =====")
        
        # --- MONITOR (M) ---
        try:
            original_code = bug_path.read_text(encoding="utf-8")
        except Exception as e:
            log.error(f"Failed to read bug file at {bug_path}: {e}")
            return self._create_result(algorithm_name, "FAIL_LOAD")

        # --- PLAN (P) & EXECUTE (E) LOOP ---
        current_patch = None
        validation_status = "FAIL_PLAN"
        error_message = "No patch generated yet."
        
        for attempt in range(MAX_RETRIES):
            log.info(f"Starting attempt {attempt + 1}/{MAX_RETRIES} for {algorithm_name}...")
            
            if attempt == 0:
                current_patch = run_plan(original_code, metrics_json=None, config=self.config)
            else:
                log.info(f"Retrying with error context: {error_message}")
                current_patch = run_retry_plan(
                    original_code, 
                    current_patch,
                    error_message, 
                    self.config
                )

            if not current_patch:
                log.error("Planning step failed to generate a patch.")
                validation_status = "FAIL_PLAN"
                continue 

            # --- EXECUTE (E) ---
            status, error = run_validation(current_patch, str(bug_path), algorithm_name)
            validation_status = status
            error_message = error

            if status == PASS:
                log.info(f"SUCCESS! Patch passed validation on attempt {attempt + 1}.")
                break
            else:
                log.warning(f"Attempt {attempt + 1} failed. Status: {status}.")
        
        log.info(f"===== Run complete for: {algorithm_name}. Final Status: {validation_status} =====")
        
        return self._create_result(
            algorithm_name, 
            validation_status, 
            current_patch if validation_status == PASS else None,
            error_message if validation_status != PASS else None
        )

    def _create_result(self, algo_name, status, patch=None, error=None):
        """Helper to format the final result dictionary."""
        return {
            "agent": self.agent_name,
            "algorithm": algo_name,
            "status": status,
            "patch": patch,
            "metrics_before": None,
            "metrics_after": None,
            "error_message": error
        }