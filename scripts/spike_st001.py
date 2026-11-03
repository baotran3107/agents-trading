#!/usr/bin/env python3
"""
ST-001 Spike: Verify calling Argon automatically from Python via agy CLI.
Measures latency, quota/token consumption, and JSON schema compliance.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont

from src.analyzer.models import ArgonAnalysisResult, get_analysis_json_schema
from src.analyzer.validator import validate_analysis_result


def create_sample_chart(image_path: Path):
    """Generates a synthetic 5M candlestick chart for the benchmark."""
    width, height = 600, 400
    img = Image.new("RGB", (width, height), color=(20, 24, 35))
    draw = ImageDraw.Draw(img)

    # Draw gridlines
    for y in range(50, height, 50):
        draw.line([(0, y), (width, y)], fill=(35, 40, 55), width=1)

    # Draw simple candlesticks
    candles = [
        (60, 2690, 2702, 2688, 2700, True),
        (120, 2700, 2708, 2698, 2706, True),
        (180, 2706, 2715, 2704, 2712, True),
        (240, 2712, 2714, 2701, 2703, False),
        (300, 2703, 2718, 2700, 2716, True),
    ]

    for x, o, h, l, c, bull in candles:
        # Scale to canvas
        y_open = height - int((o - 2680) * 8)
        y_close = height - int((c - 2680) * 8)
        y_high = height - int((h - 2680) * 8)
        y_low = height - int((l - 2680) * 8)

        color = (38, 166, 154) if bull else (239, 83, 80)
        # Wick
        draw.line([(x, y_high), (x, y_low)], fill=color, width=2)
        # Body
        top = min(y_open, y_close)
        bot = max(y_open, y_close)
        draw.rectangle([x - 12, top, x + 12, bot], fill=color)

    draw.text((20, 20), "ST-001 BENCHMARK - XAUUSD M5", fill=(255, 255, 255))
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(image_path)
    return image_path


def run_single_call(cli_path: str, model_name: str, image_path: Path, schema_str: str) -> dict:
    prompt = f"""Examine this chart image at: {image_path.resolve()}
Current price: 2716.00, M15 High: 2718.00, M15 Low: 2688.00.
Evaluate:
1. Is there a bullish rejection or breakout?
2. Is the path to 2:1 TP clear?
Return strictly adhering to the schema with direction (BUY, SELL, NONE) and checklist items.
"""
    cmd = [
        cli_path,
        "-p", prompt,
        "--model", model_name,
        "--disable-slash-commands",
        "--output-format", "json",
        "--json-schema", schema_str,
    ]

    start_t = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        duration = time.perf_counter() - start_t
        exit_code = proc.returncode
        stdout_text = proc.stdout
    except subprocess.TimeoutExpired:
        duration = time.perf_counter() - start_t
        return {
            "success": False,
            "is_valid_schema": False,
            "duration_seconds": duration,
            "exit_code": -1,
            "usage": {},
            "parsed_output": None,
            "error": "TimeoutExpired",
        }

    success = (exit_code == 0)
    parsed_output = None
    is_valid_schema = False
    usage = {}

    if success:
        try:
            cli_json = json.loads(stdout_text)
            usage = cli_json.get("usage", {})
            data = cli_json.get("structured_output") or cli_json.get("response")
            result, err = validate_analysis_result(data)
            is_valid_schema = (result is not None)
            parsed_output = result
        except Exception as e:
            success = False

    return {
        "success": success,
        "is_valid_schema": is_valid_schema,
        "duration_seconds": duration,
        "exit_code": exit_code,
        "usage": usage,
        "parsed_output": parsed_output,
    }


def main():
    parser = argparse.ArgumentParser(description="ST-001 CLI Spike Runner")
    parser.add_argument("--calls", type=int, default=3, help="Number of test calls to make (default 3)")
    parser.add_argument("--model", type=str, default="gemini-4-argon-medium", help="Argon model to benchmark")
    parser.add_argument("--cli", type=str, default="agy", help="Path to agy CLI executable")
    args = parser.parse_args()

    print(f"=== ST-001 SPIKE: BENCHMARKING ARGON VIA AGY CLI ===")
    print(f"Model: {args.model}")
    print(f"Calls: {args.calls}")
    print(f"Target Timeframe: T-10s before 5-min candle close\n")

    test_img = Path("data/captures/st001_sample.png")
    create_sample_chart(test_img)
    schema_str = json.dumps(get_analysis_json_schema())

    results = []
    total_tokens_all = 0

    for i in range(1, args.calls + 1):
        print(f"[{i}/{args.calls}] Sending request...", end="", flush=True)
        res = run_single_call(args.cli, args.model, test_img, schema_str)
        results.append(res)
        dur = res["duration_seconds"]
        tot_tok = res["usage"].get("total_tokens", 0)
        total_tokens_all += tot_tok
        print(f" Done in {dur:.2f}s | Valid: {res['is_valid_schema']} | Tokens: {tot_tok}")

    # Summary calculations
    successful_calls = [r for r in results if r["success"] and r["is_valid_schema"]]
    success_rate = (len(successful_calls) / len(results)) * 100.0
    durations = [r["duration_seconds"] for r in successful_calls]

    avg_dur = sum(durations) / len(durations) if durations else 0.0
    min_dur = min(durations) if durations else 0.0
    max_dur = max(durations) if durations else 0.0
    avg_tokens = total_tokens_all / max(1, len(results))

    print("\n" + "=" * 50)
    print("ST-001 SPIKE RESULTS SUMMARY:")
    print("=" * 50)
    print(f"• Total Runs: {args.calls}")
    print(f"• Successful & Schema Valid: {len(successful_calls)} ({success_rate:.1f}%)")
    print(f"• Latency: Avg = {avg_dur:.2f}s, Min = {min_dur:.2f}s, Max = {max_dur:.2f}s")
    print(f"• Avg Tokens / Call: {avg_tokens:.0f} tokens")
    print(f"• Estimated Daily Tokens (288 cycles): {avg_tokens * 288:,.0f} tokens")

    print("\n--- AC-3 GO / NO-GO ASSESSMENT ---")
    if success_rate >= 90.0:
        if avg_dur <= 10.0:
            print("🟢 VERDICT: GO (CLI). Latency fits within the T-10s capture window.")
        elif avg_dur <= 15.0:
            print("🟡 VERDICT: GO WITH CONFIGURATION ADJUSTMENT.")
            print(f"   Average latency is {avg_dur:.2f}s (> 10s).")
            print("   Recommendation: Increase capture lead time 't_minus_seconds' to 15s or 20s (Risk 77).")
        else:
            print("🔴 VERDICT: CONSIDER GEMINI API DIRECTLY.")
            print(f"   CLI latency is {avg_dur:.2f}s, which might arrive after candle close.")
    else:
        print("🔴 VERDICT: NO-GO. Schema validation or execution failure rate too high.")


if __name__ == "__main__":
    main()
