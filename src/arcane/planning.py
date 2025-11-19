import os
import re
import logging
from typing import Optional  # <-- This was the missing import
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

try:
    client = OpenAI()
except Exception as e:
    log.error(f"Failed to initialize OpenAI client. Is OPENAI_API_KEY set? Error: {e}")
    client = None

def run_plan(code: str, metrics_json: str, config):
    """
    Generates a patch using the two-step "Chain of Thought" (CoT) plan.
    This is used for the FIRST attempt.
    """
    if not client:
        log.error("OpenAI client not initialized. Cannot run plan.")
        return None

    log.info("--- 2. PLAN (Attempt 1): Starting 2-step patch generation ---")

    try:
        prompt_1 = config.prompts.plan_1.format(
            baseline_metrics_json=metrics_json or "N/A", # Will be N/A
            vulnerable_code=code
        )
        strategy_analysis = _call_openai_api(prompt_1)
        
        if not strategy_analysis:
            raise Exception("Plan Step 1 (Brainstorming) failed.")

        prompt_2 = config.prompts.plan_2.format(
            vulnerable_code=code,
            strategy_analysis_text=strategy_analysis
        )
        generated_patch = _call_openai_api(prompt_2, extract_code=True)

        if not generated_patch:
            raise Exception("Plan Step 2 (Final Generation) failed.")

        log.info("--- PLAN (Attempt 1) complete. Generated patch. ---")
        return generated_patch

    except Exception as e:
        log.error(f"An unexpected error occurred during planning: {e}")
        return None


def run_retry_plan(original_code: str, failed_patch: str, error_message: str, config):
    """
    Generates a new patch using the "Chain-of-Thought (CoT) retry" logic.
    This is used for attempts 2 and 3.
    """
    if not client:
        log.error("OpenAI client not initialized. Cannot run retry_plan.")
        return None
    
    log.info("--- 2. PLAN (Retry): Starting CoT error correction plan ---")

    try:
        prompt_3 = config.prompts.prompt_plan_3_retry.format(
            vulnerable_code=original_code,
            failed_patch=failed_patch or "N/A",
            error_message=error_message
        )
        
        full_cot_response = _call_openai_api(prompt_3, temperature=0.3)
        
        if not full_cot_response:
            raise Exception("Retry Plan failed to return any content.")
            
        new_patch = _extract_cot_patch(full_cot_response)

        if not new_patch:
            log.error(f"Could not parse <patch> block from LLM response: {full_cot_response}")
            raise Exception("Retry Plan failed to parse <patch> block.")

        log.info("--- PLAN (Retry) complete. Generated new patch. ---")
        return new_patch

    except Exception as e:
        log.error(f"An unexpected error occurred during retry planning: {e}")
        return None


def _call_openai_api(prompt_content: str, extract_code: bool = False, temperature: float = 0.2):
    """Helper function to call the OpenAI API."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a 10x Staff Engineer specialized in code security and maintainability."},
                {"role": "user", "content": prompt_content}
            ],
            temperature=temperature,
        )
        content = response.choices[0].message.content
        
        if not content:
            return None
        
        if extract_code:
            return _extract_simple_patch(content)
        else:
            return content.strip()

    except Exception as e:
        log.error(f"OpenAI API call failed: {e}")
        return None


def _extract_simple_patch(content: str) -> Optional[str]:
    """Extracts a simple ```python ... ``` block."""
    if "```" in content:
        parts = content.split("```")
        if len(parts) > 1:
            code_block = parts[1]
            if code_block.lower().startswith("python\n"):
                code_block = code_block[7:]
            return code_block.strip()
    log.warning("No ``` code block found in API response. Returning raw content.")
    return content.strip()


def _extract_cot_patch(content: str) -> Optional[str]:
    """Extracts the <patch>...</patch> block from a CoT response."""
    try:
        match = re.search(r"<patch>(.*?)</patch>", content, re.DOTALL | re.IGNORECASE)
        if match:
            patch_content = match.group(1).strip()
            return _extract_simple_patch(patch_content)
        
        log.warning("No <patch> block found. Falling back to simple extraction.")
        return _extract_simple_patch(content)
        
    except Exception as e:
        log.error(f"Error during CoT patch extraction: {e}")
        return None