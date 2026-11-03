import json
from pathlib import Path
from typing import Any, Dict, List
from src.mt5.models import RawPrices


def build_analysis_prompt(
    image_path: Path,
    raw_prices: RawPrices,
    checklist_config: Dict[str, Any],
    retry_feedback: str = "",
) -> str:
    """
    Constructs the prompt sent to Argon (via agy CLI).
    Includes absolute image path, verified MT5 numbers, and checklist items.
    """
    conditions: List[Dict[str, Any]] = checklist_config.get("conditions", [])

    checklist_text = []
    for c in conditions:
        req = "[REQUIRED]" if c.get("required", True) else "[OPTIONAL]"
        checklist_text.append(
            f"- ID: {c['id']}\n"
            f"  Name: {c['name']} {req}\n"
            f"  Rule: {c['description']}"
        )

    formatted_checklist = "\n".join(checklist_text)

    prompt = f"""You are an expert quantitative and technical trading assistant analyzing a financial chart.
Inspect the chart image located at: {image_path.resolve()}

VERIFIED RAW PRICES FROM MT5 (Do not attempt to read numbers from image axes; use these exact values):
- Symbol: {raw_prices.symbol}
- Current Price: {raw_prices.current_price:.2f} (Bid: {raw_prices.bid:.2f}, Ask: {raw_prices.ask:.2f})
- 15-Minute Recent High: {raw_prices.m15_high:.2f}
- 15-Minute Recent Low: {raw_prices.m15_low:.2f}

TRADING PLAN CHECKLIST:
Evaluate EACH of the following rules strictly against the chart setup:
{formatted_checklist}

RULES:
1. Examine candlestick patterns, structure, key levels, and price action visible in the chart image.
2. For EVERY checklist condition, output 'met': true/false and a concise 'reason' (exactly 1 sentence).
3. If setup is a valid Long/Buy, set 'direction': 'BUY'.
4. If setup is a valid Short/Sell, set 'direction': 'SELL'.
5. If no clear setup or conflicting signals, set 'direction': 'NONE'.
6. Return output in strict JSON format.
"""

    if retry_feedback:
        prompt += f"\nPREVIOUS ATTEMPT FAILED VALIDATION:\n{retry_feedback}\nPlease correct the schema errors."

    return prompt

