import pytest
from src.analyzer.models import ArgonAnalysisResult
from src.analyzer.validator import extract_json_from_text, validate_analysis_result


def test_extract_json_from_text():
    raw_markdown = """```json
    {
        "direction": "BUY",
        "checklist": [
            {"condition_id": "c1", "description": "Trend", "met": true, "reason": "Bullish trend."}
        ],
        "confidence": "HIGH",
        "summary": "Solid bullish setup."
    }
    ```"""
    parsed = extract_json_from_text(raw_markdown)
    assert parsed is not None
    assert parsed["direction"] == "BUY"


def test_validate_analysis_result_valid():
    data = {
        "direction": "BUY",
        "checklist": [
            {"condition_id": "c1", "description": "Trend", "met": True, "reason": "Uptrend confirmed."},
            {"condition_id": "c2", "description": "Level", "met": True, "reason": "Support held."},
        ],
        "confidence": "HIGH",
        "summary": "Great setup.",
    }
    result, err = validate_analysis_result(data, expected_checklist_ids=["c1", "c2"])
    assert result is not None
    assert err == ""
    assert result.direction == "BUY"
    assert len(result.checklist) == 2


def test_validate_analysis_result_missing_id():
    data = {
        "direction": "BUY",
        "checklist": [
            {"condition_id": "c1", "description": "Trend", "met": True, "reason": "Uptrend confirmed."}
        ],
        "confidence": "HIGH",
        "summary": "Great setup.",
    }
    result, err = validate_analysis_result(data, expected_checklist_ids=["c1", "c2"])
    assert result is None
    assert "Missing evaluation for condition IDs: c2" in err

