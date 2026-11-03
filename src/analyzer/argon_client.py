import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from PIL import Image
from src.analyzer.models import ArgonAnalysisResult, get_analysis_json_schema
from src.analyzer.prompt import build_analysis_prompt
from src.analyzer.validator import validate_analysis_result
from src.config import ModelConfig
from src.mt5.models import RawPrices

logger = logging.getLogger(__name__)


class ArgonClientError(Exception):
    """Base error for Argon client."""
    pass


class ArgonTimeoutError(ArgonClientError):
    """Raised when the model call exceeds the configured timeout."""
    pass


class ArgonClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.json_schema_str = json.dumps(get_analysis_json_schema())
        self._genai_client = None

        if self.config.provider == "gemini_api":
            try:
                from google import genai
                api_key = self.config.api_key or os.getenv("GEMINI_API_KEY")
                self._genai_client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Google GenAI SDK: {e}")

    def _execute_cli_call(self, prompt: str) -> Tuple[int, str, float]:
        """
        Executes agy CLI command.
        Returns: (exit_code, stdout_text, duration_seconds)
        """
        cmd = [
            self.config.cli_path,
            "-p", prompt,
            "--model", self.config.model_name,
            "--disable-slash-commands",
            "--output-format", "json",
            "--json-schema", self.json_schema_str,
        ]

        logger.debug(f"Executing CLI command: {' '.join(cmd[:4])} ...")
        start_t = time.perf_counter()

        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
            duration = time.perf_counter() - start_t
            return process.returncode, process.stdout, duration
        except subprocess.TimeoutExpired as e:
            duration = time.perf_counter() - start_t
            logger.error(f"Argon CLI call timed out after {self.config.timeout_seconds}s (ST-004 AC-3)")
            raise ArgonTimeoutError(f"CLI timed out after {self.config.timeout_seconds}s") from e
        except FileNotFoundError:
            raise ArgonClientError(f"CLI executable '{self.config.cli_path}' not found in PATH.")

    def _execute_gemini_api_call(self, prompt: str, image_path: Path) -> Tuple[Optional[ArgonAnalysisResult], Dict[str, Any]]:
        """Executes direct Gemini API call for fast sub-3s inference."""
        if not self._genai_client:
            raise ArgonClientError("Gemini API client is not configured or missing GEMINI_API_KEY.")

        start_t = time.perf_counter()
        image = Image.open(image_path)
        model_name = self.config.model_name or "gemini-2.5-flash"

        response = self._genai_client.models.generate_content(
            model=model_name,
            contents=[image, prompt],
            config={
                "response_mime_type": "application/json",
                "response_schema": ArgonAnalysisResult,
            },
        )
        duration = time.perf_counter() - start_t

        result = ArgonAnalysisResult.model_validate_json(response.text)
        return result, {"duration_seconds": duration, "usage": getattr(response, "usage_metadata", {})}

    def analyze_chart(
        self,
        image_path: Path,
        raw_prices: RawPrices,
        checklist_config: Dict[str, Any],
    ) -> Tuple[Optional[ArgonAnalysisResult], Dict[str, Any]]:
        """
        Runs the full analysis cycle with ST-004 retry on schema validation failure.
        Returns: (ArgonAnalysisResult or None, metadata_dict)
        """
        expected_ids = [c["id"] for c in checklist_config.get("conditions", [])]
        metadata = {
            "attempts": 0,
            "duration_seconds": 0.0,
            "usage": {},
            "raw_response": None,
            "error": None,
        }

        # Fast path: direct Gemini API
        if self.config.provider == "gemini_api" and self._genai_client:
            prompt = build_analysis_prompt(
                image_path=image_path,
                raw_prices=raw_prices,
                checklist_config=checklist_config,
            )
            try:
                res, meta = self._execute_gemini_api_call(prompt, image_path)
                metadata.update(meta)
                metadata["attempts"] = 1
                return res, metadata
            except Exception as e:
                logger.error(f"Gemini API execution error: {e}")
                metadata["error"] = str(e)
                return None, metadata

        retry_feedback = ""
        max_attempts = 1 + self.config.retry_attempts  # default 1 retry (total 2 attempts)

        for attempt in range(1, max_attempts + 1):
            metadata["attempts"] = attempt
            prompt = build_analysis_prompt(
                image_path=image_path,
                raw_prices=raw_prices,
                checklist_config=checklist_config,
                retry_feedback=retry_feedback,
            )

            try:
                exit_code, stdout, duration = self._execute_cli_call(prompt)
                metadata["duration_seconds"] += duration

                if exit_code != 0:
                    logger.warning(f"CLI returned non-zero exit code {exit_code}: {stdout}")
                    metadata["error"] = f"CLI exit code {exit_code}"
                    retry_feedback = f"CLI call failed with code {exit_code}."
                    continue

                # Parse CLI JSON envelope
                cli_output = json.loads(stdout)
                metadata["usage"] = cli_output.get("usage", {})
                metadata["raw_response"] = cli_output

                # In agy, structured_output or response contains the result
                data_to_validate = (
                    cli_output.get("structured_output")
                    or cli_output.get("response")
                )

                result, val_err = validate_analysis_result(
                    data_to_validate, expected_checklist_ids=expected_ids
                )

                if result is not None:
                    logger.info(
                        f"Argon analysis succeeded on attempt {attempt} in {duration:.2f}s "
                        f"(direction={result.direction}, confidence={result.confidence})"
                    )
                    return result, metadata

                logger.warning(f"Validation failed on attempt {attempt}: {val_err}")
                retry_feedback = val_err
                metadata["error"] = val_err

            except ArgonTimeoutError as e:
                metadata["error"] = "TIMEOUT"
                logger.error(f"Argon timed out on attempt {attempt}. ST-004 AC-3: cancelling call.")
                return None, metadata
            except Exception as e:
                metadata["error"] = str(e)
                logger.error(f"Unexpected error in Argon client: {e}")
                retry_feedback = str(e)

        logger.error("All analysis attempts failed validation or execution (ST-004 AC-2).")
        return None, metadata
