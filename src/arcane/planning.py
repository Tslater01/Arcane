import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

# Load .env file for OPENAI_API_KEY
load_dotenv()

log = logging.getLogger(__name__)

# Initialize the OpenAI client.
try:
    client = OpenAI()
except Exception as e:
    log.error(f"Failed to initialize OpenAI client. Is OPENAI_API_KEY set? Error: {e}")
    client = None

def run_plan(code: str, metrics_json: str, config):
    """
    Generates a patch using a two-step "Chain of Thought" (CoT) plan.

    :param code: The original vulnerable code string.
    :param metrics_json: A JSON string of the SonarCloud metrics.
    :param config: The Hydra config object.
    :return: A string containing the generated code patch, or None on failure.
    """
    if not client:
        log.error("OpenAI client not initialized. Cannot run plan.")
        return None

    log.info("--- 2. PLAN: Starting 2-step patch generation ---")

    try:
        # Call 1: Brainstorming 
        prompt_1 = config.prompts.plan_1.format(
            baseline_metrics_json=metrics_json or "N/A",
            vulnerable_code=code
        )
        
        log.info("Running Plan Step 1 (Brainstorming)...")
        strategy_analysis = _call_openai_api(prompt_1)
        
        if not strategy_analysis:
            raise Exception("Plan Step 1 (Brainstorming) failed to return content.")

        # Call 2: Final Patch Generation 
        prompt_2 = config.prompts.plan_2.format(
            vulnerable_code=code,
            strategy_analysis_text=strategy_analysis
        )
        
        log.info("Running Plan Step 2 (Final Patch Generation)...")
        generated_patch = _call_openai_api(prompt_2, extract_code=True)

        if not generated_patch:
            raise Exception("Plan Step 2 (Final Generation) failed to return code.")

        log.info("--- PLAN complete. Generated patch. ---")
        return generated_patch

    except Exception as e:
        log.error(f"An unexpected error occurred during planning: {e}")
        return None


def _call_openai_api(prompt_content: str, extract_code: bool = False):
    """Helper function to call the OpenAI API and handle response extraction."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a 10x Staff Engineer specialized in code security and maintainability."},
                {"role": "user", "content": prompt_content}
            ],
            temperature=0.2, # Low temp for deterministic and non-wild results
        )
        
        content = response.choices[0].message.content
        
        if not content:
            return None
        
        if extract_code:
            # Clean the response to get *only* the code
            if "```" in content:
                parts = content.split("```")
                if len(parts) > 1:
                    code_block = parts[1]
                    # Remove the language hint (e.g., "java\n")
                    if code_block.lower().startswith("java\n"):
                        code_block = code_block[5:]
                    return code_block.strip()
            
            # Fallback: if no ``` found, assume the whole response is code
            log.warning("No ``` code block found in API response. Returning raw content.")
            return content.strip()

        return content.strip()

    except Exception as e:
        log.error(f"OpenAI API call failed: {e}")
        return None