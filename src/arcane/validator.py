import shutil
import subprocess
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Validation status constants
PASS = "PASS"
FAIL_COMPILE = "FAIL_COMPILE"
FAIL_TEST = "FAIL_TEST"


def run_validation(patch_code: str, bug_file_path: str, algorithm_name: str):
    """
    Validates a given patch by applying it, running tests, and restoring the original.

    :param patch_code: The new code to write to the file.
    :param bug_file_path: The full path to the original buggy .java file.
    :param algorithm_name: The lowercase name of the algorithm (e.g., "breadth_first_search").
    :return: A validation status (PASS, FAIL_COMPILE, FAIL_TEST).
    """
    log.info(f"--- 3. EXECUTE: Validating patch for {algorithm_name} ---")
    
    original_file = Path(bug_file_path)
    backup_file = original_file.with_suffix(".java.bak")
    # Go up from .../java_programs/FILE.java to .../QuixBugs/
    benchmark_dir = original_file.parent.parent 

    if not original_file.exists():
        log.error(f"Validator error: Bug file not found at {original_file}")
        return FAIL_TEST

    try:
        # Step 1: Back up the original file
        shutil.copy(original_file, backup_file)
        
        # Step 2: Apply the patch (write the new code)
        with open(original_file, "w", encoding="utf-8") as f:
            f.write(patch_code)
        
        # Step 3: Run the 3-stage validation
        validation_result = _run_benchmark_test(benchmark_dir, algorithm_name)
        
        log.info(f"--- EXECUTE complete. Result: {validation_result} ---")
        return validation_result

    except Exception as e:
        log.error(f"An unexpected error occurred during validation: {e}")
        return FAIL_TEST
        
    finally:
        # Step 4: Restore the original file NO MATTER WHAT
        if backup_file.exists():
            # Use move for an atomic operation, converting Paths to strings
            shutil.move(str(backup_file), str(original_file))
            log.info(f"Restored original file: {original_file.name}")


def _run_benchmark_test(benchmark_dir: Path, algorithm_name: str):
    """
    Runs the QuixBugs tester.py script, which handles compile and test.
    
    :param benchmark_dir: Path to the root of the QuixBugs directory.
    :param algorithm_name: The lowercase name of the algorithm.
    :return: A validation status.
    """
    command = ["python", "tester.py", algorithm_name, "-t"]
    
    try:
        # Run the test script with a 30-second timeout
        result = subprocess.run(
            command,
            cwd=benchmark_dir,
            capture_output=True,
            text=True,
            timeout=30
        )

        output = result.stdout + result.stderr
        
        # Stage 1: Check for Compilation Failures
        if "Compilation Failed" in output:
            log.warning("Validation failed: Patch did not compile.")
            return FAIL_COMPILE
            
        # Stage 2/3: Check for Functional/Bug Failures
        # The script prints "FAIL" or an Exception/Error if the patch is incorrect
        if "Exception" in output or "Error" in output or "FAIL" in output:
            # Log the last 200 chars for a snippet of the error
            log.warning(f"Validation failed: Patch failed tests. Error snippet: {output[-200:]}")
            return FAIL_TEST

        # If no errors were found, the patch is considered correct.
        log.info("Validation successful: Patch compiled and passed all tests.")
        return PASS

    except subprocess.TimeoutExpired:
        log.error("Validation failed: Test run timed out.")
        return FAIL_TEST
    except Exception as e:
        log.error(f"Failed to execute tester.py: {e}")
        return FAIL_TEST