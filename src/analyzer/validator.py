import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import ValidationError
from src.analyzer.models import ArgonAnalysisResult

logger = logging.getLogger(__name__)


def extract_json_from_text(text: str) -> Optional[dict]:
    """Extracts JSON object from plain text or markdown codeblocks."""
    if not text or not text.strip():
        return None

    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding outermost { ... }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        snippet = text[first_brace : last_brace + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            pass

    return None


def validate_analysis_result(
    raw_data: Any,
    expected_checklist_ids: Optional[List[str]] = None,
) -> Tuple[Optional[ArgonAnalysisResult], str]:
    """
    Validates model output against ArgonAnalysisResult schema.
    Returns: (parsed_result, error_message)
    """
    if isinstance(raw_data, str):
        json_obj = extract_json_from_text(raw_data)
        if json_obj is None:
            return None, "Output does not contain valid JSON syntax."
    elif isinstance(raw_data, dict):
        json_obj = raw_data
    else:
        return None, f"Unsupported data type for validation: {type(raw_data)}"

    try:
        result = ArgonAnalysisResult.model_validate(json_obj)
    except ValidationError as e:
        return None, f"Pydantic schema validation failed: {str(e)}"

    # Check that all expected checklist IDs are present
    if expected_checklist_ids:
        reported_ids = {c.condition_id for c in result.checklist}
        missing_ids = set(expected_checklist_ids) - reported_ids
        if missing_ids:
            return (
                None,
                f"Missing evaluation for condition IDs: {', '.join(missing_ids)}",
            )

    return result, ""

