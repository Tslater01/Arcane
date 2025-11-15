import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Tuple, Optional

# Import our new shared utility
from .utils import compile_with_gradle, get_java_classpath

log = logging.getLogger(__name__)

# Validation status constants
PASS = "PASS"
FAIL_COMPILE = "FAIL_COMPILE"
FAIL_TEST = "FAIL_TEST"
FAIL_TIMEOUT = "FAIL_TIMEOUT"
FAIL_ERROR = "FAIL_ERROR"

# For robustly killing processes on Windows
CREATE_NEW_PROCESS_GROUP = 0x00000200

def run_validation(patch_code: str, bug_file_path: str, algorithm_name: str) -> Tuple[str, Optional[str]]:
    """
    Validates a given patch by applying it, compiling, and running the test.
    """
    log.info(f"--- 3. EXECUTE: Validating patch for {algorithm_name} ---")
    
    original_file = Path(bug_file_path)
    backup_file = original_file.with_suffix(".java.bak")
    benchmark_dir = original_file.parent.parent 

    if not original_file.exists():
        log.error(f"Validator error: Bug file not found at {original_file}")
        return FAIL_ERROR, "Bug file not found"

    try:
        shutil.copy(original_file, backup_file)
        
        with open(original_file, "w", encoding="utf-8") as f:
            f.write(patch_code)
        
        # Stage 1: Compile the project with the new patch
        if not compile_with_gradle(benchmark_dir):
            log.warning("Validation failed: Patch did not compile.")
            return FAIL_COMPILE, "Gradle build failed. Patch likely has a syntax error."

        # Stage 2: Run the specific JUnit test
        status, error = _run_java_test(benchmark_dir, algorithm_name)
        
        log.info(f"--- EXECUTE complete. Result: {status} ---")
        return status, error

    except Exception as e:
        log.error(f"An unexpected error occurred during validation: {e}")
        return FAIL_ERROR, str(e)
        
    finally:
        if backup_file.exists():
            shutil.move(str(backup_file), str(original_file))
            log.info(f"Restored original file: {original_file.name}")


def _run_java_test(benchmark_dir: Path, algorithm_name: str) -> Tuple[str, Optional[str]]:
    """
    Runs a single JUnit test directly using java.
    """
    log.info(f"Running direct Java test for {algorithm_name}...")

    # --- THIS IS THE FIX ---
    # Get the full, correct classpath, including junit AND hamcrest
    classpath = get_java_classpath(benchmark_dir)
    
    test_class_name = f"java_testcases.junit.{algorithm_name.upper()}_TEST"
    
    command = [
        "java",
        "-cp",
        classpath,
        "org.junit.runner.JUnitCore",
        test_class_name
    ]
    
    process = None
    try:
        process = subprocess.Popen(
            command,
            cwd=benchmark_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
            creationflags=CREATE_NEW_PROCESS_GROUP
        )
        
        stdout, stderr = process.communicate(timeout=60)

        if process.returncode == 0 and "OK" in stdout:
            log.info("Validation successful: JUnit test passed.")
            return PASS, None
        else:
            log.warning("Validation failed: JUnit test failed.")
            full_error = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
            return FAIL_TEST, full_error[-1500:] 

    except subprocess.TimeoutExpired:
        log.error("Validation failed: Test run timed out after 60 seconds.")
        try:
            log.info(f"Force-killing timed-out process tree (PID: {process.pid})...")
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                check=True,
                capture_output=True
            )
            log.info(f"Process tree killed successfully.")
        except Exception as kill_e:
            log.error(f"Failed to kill process {process.pid}: {kill_e}")
            process.kill()
            
        return FAIL_TIMEOUT, "Test run exceeded 60-second timeout (potential infinite loop)."
    
    except Exception as e:
        log.error(f"Failed to execute Java test: {e}")
        if process:
            process.kill()
        return FAIL_ERROR, str(e)