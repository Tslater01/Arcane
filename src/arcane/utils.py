import os
import subprocess
import logging
import requests
from pathlib import Path

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# Create a 'junit_libs' folder to hold our downloaded JARs
JUNIT_DIR = PROJECT_ROOT / "data" / "benchmarks" / "QuixBugs" / "java_testcases" / "junit_libs"
JUNIT_PATH = JUNIT_DIR / "junit-4.12.jar"
HAMCREST_PATH = JUNIT_DIR / "hamcrest-core-1.3.jar"

JUNIT_URL = "https://repo1.maven.org/maven2/junit/junit/4.12/junit-4.12.jar"
HAMCREST_URL = "https://repo1.maven.org/maven2/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar"

def _download_jar(url: str, path: Path):
    """Downloads a JAR file if it's missing."""
    if path.exists():
        log.info(f"{path.name} already exists.")
        return

    log.warning(f"{path.name} not found. Downloading...")
    try:
        JUNIT_DIR.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        log.info(f"Successfully downloaded {path.name}.")

    except Exception as e:
        log.error(f"FATAL: Failed to download {path.name}: {e}")
        raise e

def _ensure_dependencies():
    """Ensures all required .jar files are downloaded."""
    _download_jar(JUNIT_URL, JUNIT_PATH)
    _download_jar(HAMCREST_URL, HAMCREST_PATH)

def get_java_classpath(benchmark_dir: Path) -> str:
    """Builds the full classpath needed for compilation and testing."""
    _ensure_dependencies() # Make sure JARs are downloaded

    main_classes = benchmark_dir / "build" / "classes" / "java" / "main"
    test_classes = benchmark_dir / "build" / "classes" / "java" / "test"

    # Use ; for classpath separator on Windows
    # This now includes hamcrest-core, fixing the NoClassDefFoundError
    return f".;{JUNIT_PATH};{HAMCREST_PATH};{main_classes};{test_classes}"

def compile_with_gradle(benchmark_dir: Path):
    """
    Compiles the entire QuixBugs project using its own build.gradle file.
    """
    log.info("Compiling .java files using Gradle...")

    command = ["gradle", "build", "-x", "test", "--quiet"]

    try:
        result = subprocess.run(
            command,
            cwd=benchmark_dir,
            capture_output=True,
            text=True,
            check=True,
            shell=True
        )
        log.info("Gradle build successful.")
        return True

    except subprocess.CalledProcessError as e:
        log.error(f"Gradle build FAILED. This is a critical error. {e.stderr}")
        return False