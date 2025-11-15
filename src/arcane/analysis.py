import os
import subprocess
import time
import requests
import logging
from pathlib import Path
from dotenv import load_dotenv

# Import our new shared utility
from .utils import compile_with_gradle

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

load_dotenv()

SONAR_METRICS = "technical_debt,cognitive_complexity,code_smells,vulnerabilities"

def run_analysis(code_directory: Path, config):
    """
    Runs a full SonarCloud analysis on a directory and returns the metrics.
    """
    log.info(f"--- 1. ANALYZE: Starting SonarCloud scan on {code_directory} ---")
    
    sonar_config = config.sonar
    project_key = sonar_config.project_key
    organization = sonar_config.organization
    host_url = sonar_config.host_url
    
    sonar_token = os.getenv("SONAR_TOKEN")
    
    if not sonar_token:
        log.error("SONAR_TOKEN not found in .env file. Skipping analysis.")
        return None

    try:
        benchmark_dir = code_directory.parent 
        
        if not compile_with_gradle(benchmark_dir):
            raise Exception("Gradle build failed, cannot proceed with Sonar analysis.")

        ce_task_url = _run_scanner(code_directory, benchmark_dir, project_key, organization, host_url, sonar_token)
        
        if not ce_task_url:
            log.warning("Could not find ceTaskUrl. Waiting 15s as a fallback.")
            time.sleep(15)
        else:
            _wait_for_task_completion(ce_task_url, sonar_token)
        
        log.info("Fetching metrics from SonarCloud API...")
        metrics = _get_scan_results(project_key, organization, sonar_token)
        
        log.info(f"--- ANALYZE complete. Metrics found: {metrics} ---")
        return metrics
        
    except Exception as e:
        log.error(f"An unexpected error occurred during analysis: {e}")
    
    return None


def _run_scanner(code_dir: Path, benchmark_dir: Path, project_key, org, host_url, token):
    """Helper function to run the sonar-scanner CLI tool."""
    
    binary_path = benchmark_dir / "build" / "classes" / "java" / "main"
    test_binary_path = benchmark_dir / "build" / "classes" / "java" / "test"

    command = [
        "sonar-scanner",
        f"-Dsonar.projectKey={project_key}",
        f"-Dsonar.organization={org}",
        f"-Dsonar.sources=.",
        f"-Dsonar.host.url={host_url}",
        f"-Dsonar.login={token}",
        f"-Dsonar.java.binaries={binary_path}",
        f"-Dsonar.java.test.binaries={test_binary_path}",
        "-Dsonar.log.level=INFO"
    ]
    
    log.info("Starting sonar-scanner process...")
    
    result = subprocess.run(
        command,
        cwd=code_dir,
        capture_output=True,
        text=True,
        check=True
    )
    
    log.info("Sonar-scanner run successful.")
    
    ce_task_url = None
    for line in result.stdout.splitlines():
        if "ceTaskUrl" in line:
            ce_task_url = line.split("=")[1].strip()
            break
            
    if not ce_task_url:
        log.warning("Could not find ceTaskUrl in scanner output.")
        log.debug(f"Full scanner output: {result.stdout}")
        
    return ce_task_url


def _wait_for_task_completion(task_url, token):
    """Polls the SonarCloud Compute Engine task URL until analysis is complete."""
    
    log.info("Waiting for SonarCloud to process the report...")
    start_time = time.time()
    timeout_seconds = 300
    
    while True:
        if time.time() - start_time > timeout_seconds:
            raise Exception("SonarCloud analysis task timed out.")
            
        try:
            response = requests.get(task_url, auth=(token, ""))
            response.raise_for_status() 
            
            task_status = response.json().get("task", {}).get("status")
            log.info(f"Current task status: {task_status}")
            
            if task_status == "SUCCESS":
                log.info("Analysis processing finished successfully.")
                break
            elif task_status in ("FAILED", "CANCELED"):
                raise Exception(f"SonarCloud analysis task {task_status}.")
                
        except requests.RequestException as e:
            log.error(f"Error polling task status: {e}. Retrying...")
        
        time.sleep(5)


def _get_scan_results(project_key, org, token):
    """Helper function to call the SonarCloud Web API for the metrics."""
    
    api_url = f"https://sonarcloud.io/api/measures/component"
    params = {
        "component": project_key,
        "organization": org,
        "metricKeys": SONAR_METRICS
    }
    
    response = requests.get(api_url, params=params, auth=(token, ""))
    response.raise_for_status()
            
    data = response.json()
    
    metrics = {}
    for measure in data.get("component", {}).get("measures", []):
        metric_name = measure.get("metric")
        metric_value = measure.get("value")
        metrics[metric_name] = metric_value
            
    if not metrics:
        log.warning("SonarCloud API returned no metrics. Check SonarCloud dashboard.")
        
    return metrics