import shutil
import subprocess
import logging
from pathlib import Path
from typing import Tuple, Optional

log = logging.getLogger(__name__)

# Validation status constants
PASS = "PASS"
FAIL_COMPILE = "FAIL_COMPILE" # We'll re-purpose this for Python syntax errors
FAIL_TEST = "FAIL_TEST"
FAIL_TIMEOUT = "FAIL_TIMEOUT"
FAIL_ERROR = "FAIL_ERROR"

def run_validation(patch_code: str, bug_file_path: str, algorithm_name: str) -> Tuple[str, Optional[str]]:
    """
    Validates a Python patch by applying it and running tester.py.
    """
    log.info(f"--- 3. EXECUTE: Validating Python patch for {algorithm_name} ---")
    
    original_file = Path(bug_file_path)
    backup_file = original_file.with_suffix(".py.bak")
    benchmark_dir = original_file.parent.parent 

    if not original_file.exists():
        log.error(f"Validator error: Bug file not found at {original_file}")
        return FAIL_ERROR, "Bug file not found"

    try:
        shutil.copy(original_file, backup_file)
        with open(original_file, "w", encoding="utf-8") as f:
            f.write(patch_code)
        
        status, error = _run_python_test(benchmark_dir, algorithm_name)
        
        log.info(f"--- EXECUTE complete. Result: {status} ---")
        return status, error

    except Exception as e:
        log.error(f"An unexpected error occurred during validation: {e}")
        return FAIL_ERROR, str(e)
        
    finally:
        if backup_file.exists():
            shutil.move(str(backup_file), str(original_file))
            log.info(f"Restored original file: {original_file.name}")


def _run_python_test(benchmark_dir: Path, algorithm_name: str) -> Tuple[str, Optional[str]]:
    """
    Runs the QuixBugs tester.py script for a Python bug.
    Uses subprocess.run for robust, hang-free execution.
    """
    log.info(f"Running Python test for {algorithm_name}...")
    
    # Command to run the tester script
    command = ["python", "tester.py", algorithm_name]
    
    try:
        # subprocess.run is the modern, hang-free way to do this.
        # It handles the timeout and captures stdout/stderr without deadlocking.
        result = subprocess.run(
            command,
            cwd=benchmark_dir,
            capture_output=True,
            text=True,
            timeout=60, # 60-second timeout
            check=True  # Will raise CalledProcessError if returncode != 0
        )

        # If check=True passes, the return code was 0, meaning success
        log.info("Validation successful: Python test passed.")
        return PASS, None

    except subprocess.TimeoutExpired as e:
        log.error("Validation failed: Test run timed out after 60 seconds.")
        return FAIL_TIMEOUT, "Test run exceeded 60-second timeout (potential infinite loop)."
    
    except subprocess.CalledProcessError as e:
        # The script ran but failed (the bug is still present or a new one was intro'd)
        log.warning("Validation failed: Python test failed.")
        
        # tester.py prints the real bug to stderr
        error_output = e.stderr
        error_snippet = error_output.split("Traceback (most recent call last):")[-1].strip()
        return FAIL_TEST, error_snippet[-1500:] # Return the clean error
    
    except Exception as e:
        # A different error, like the script not being found
        log.error(f"Failed to execute tester.py: {e}")
        return FAIL_ERROR, str(e)