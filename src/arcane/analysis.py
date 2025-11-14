import os
import subprocess
import time
import requests
import logging
from dotenv import load_dotenv

# Set up a simple logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Load secret keys (SONAR_TOKEN) from our .env file
load_dotenv()

SONAR_METRICS = "technical_debt,cognitive_complexity,code_smells,vulnerabilities"

def run_analysis(code_directory, config):
    """
    Runs a full SonarCloud analysis on a directory and returns the metrics.

    :param code_directory: The full path to the code to be analyzed.
    :param config: The Hydra config object.
    :return: A dictionary of metrics, or None if analysis fails.
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
        # Step 1: Run the scanner and get the task URL for polling
        ce_task_url = _run_scanner(code_directory, project_key, organization, host_url, sonar_token)
        
        # Step 2: Poll the task URL until the analysis is complete
        _wait_for_task_completion(ce_task_url, sonar_token)
        
        # Step 3: Call the SonarCloud Web API to get the final results
        log.info("Fetching metrics from SonarCloud API...")
        metrics = _get_scan_results(project_key, organization, sonar_token)
        
        log.info(f"--- ANALYZE complete. Metrics found: {metrics} ---")
        return metrics
        
    except subprocess.CalledProcessError as e:
        log.error(f"Sonar-scanner execution failed: {e.stderr}")
    except requests.RequestException as e:
        log.error(f"API request failed: {e}")
    except Exception as e:
        log.error(f"An unexpected error occurred during analysis: {e}")
    
    return None


def _run_scanner(code_dir, project_key, org, host_url, token):
    """Helper function to run the sonar-scanner CLI tool."""
    
    command = [
        "sonar-scanner",
        f"-Dsonar.projectKey={project_key}",
        f"-Dsonar.organization={org}",
        f"-Dsonar.sources=.",
        f"-Dsonar.host.url={host_url}",
        f"-Dsonar.login={token}"
    ]
    
    log.info("Starting sonar-scanner process...")
    
    result = subprocess.run(
        command,
        cwd=code_dir,
        capture_output=True,
        text=True,
        check=True # This will raise CalledProcessError if returncode is not 0
    )
    
    log.info("Sonar-scanner run successful.")
    
    # Find the task URL in the scanner's output
    ce_task_url = None
    for line in result.stdout.splitlines():
        if "ceTaskUrl" in line:
            ce_task_url = line.split("=")[1].strip()
            break
            
    if not ce_task_url:
        raise Exception("Could not find ceTaskUrl in scanner output. Analysis may have failed silently.")
        
    log.info(f"Analysis task URL: {ce_task_url}")
    return ce_task_url


def _wait_for_task_completion(task_url, token):
    """Polls the SonarCloud Compute Engine task URL until analysis is complete."""
    
    log.info("Waiting for SonarCloud to process the report...")
    start_time = time.time()
    timeout_seconds = 300  # 5 minutes
    
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
        
        time.sleep(5) # Poll every 5 seconds


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
        log.warning("SonarCloud API returned no metrics. Check project key.")
        
    return metrics