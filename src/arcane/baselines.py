import logging
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional # <-- Added import

# Import our custom modules
from .validator import run_validation, PASS
from .planning import run_plan as run_aware_plan
from .planning import client as openai_client

log = logging.getLogger(__name__)


class BaseBaselineAgent(ABC):
    """
    Abstract base class for all baseline agents.
    """
    def __init__(self, config):
        self.config = config
        self.agent_name = "BaseAgent"
    
    @abstractmethod
    def _get_patch(self, original_code: str) -> Optional[str]:
        """The-subclass-specific method for generating a patch."""
        pass
    
    def run_fix(self, bug_path: Path, algorithm_name: str):
        """Runs the full fix and validation process."""
        log.info(f"===== Starting {self.agent_name} run for: {algorithm_name} =====")
        
        try:
            original_code = bug_path.read_text(encoding="utf-8")
        except Exception as e:
            log.error(f"Failed to read bug file at {bug_path}: {e}")
            return self._create_result(algorithm_name, "FAIL_LOAD")

        patch_code = self._get_patch(original_code)
        
        if not patch_code:
            log.error(f"{self.agent_name} plan failed to generate a patch.")
            return self._create_result(algorithm_name, "FAIL_PLAN")

        validation_status, error_message = run_validation(patch_code, str(bug_path), algorithm_name)
        
        if validation_status == PASS:
            error_message = None

        return self._create_result(
            algorithm_name, 
            validation_status, 
            patch_code if validation_status == PASS else None,
            error_message
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


class BaselineNaive(BaseBaselineAgent):
    """
    A "naive" baseline agent (B1).
    """
    def __init__(self, config):
        super().__init__(config)
        self.agent_name = "BaselineNaive"
        log.info(f"{self.agent_name} initialized.")
    
    def _get_patch(self, original_code: str) -> Optional[str]:
        if not openai_client:
            log.error("OpenAI client not initialized.")
            return None
        try:
            prompt_content = f"Fix the bug in the following Python code. Only return the full, corrected code block.\n\n```python\n{original_code}\n```"
            
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful coding assistant."},
                    {"role": "user", "content": prompt_content}
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content
            
            if "```" in content:
                parts = content.split("```")
                if len(parts) > 1:
                    code_block = parts[1]
                    if code_block.lower().startswith("python\n"):
                        code_block = code_block[7:]
                    return code_block.strip()
            return content.strip()

        except Exception as e:
            log.error(f"OpenAI API call failed for NaiveBaseline: {e}")
            return None


class BaselineAware(BaseBaselineAgent):
    """
    An "architecturally-aware" baseline agent (B2).
    """
    def __init__(self, config):
        super().__init__(config)
        self.agent_name = "BaselineAware"
        log.info(f"{self.agent_name} initialized.")
    
    def _get_patch(self, original_code: str) -> Optional[str]:
        return run_aware_plan(original_code, metrics_json=None, config=self.config)