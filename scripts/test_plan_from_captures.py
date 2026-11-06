#!/usr/bin/env python3
"""
Test script to verify reading images from folder (data/captures/),
running Argon AI Order Flow Daily Plan analysis, and sending the plan to Telegram.
"""

import argparse
import glob
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple
import httpx
from PIL import Image, ImageDraw

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer.argon_client import ArgonClient
from src.capture.screen_capture import ScreenCaptureService
from src.config import load_config
from src.mt5.client import get_mt5_client
from src.notifier.telegram_bot import TelegramNotifier
from src.planner.daily_planner import DailyPlanner
from src.storage.logger import CycleStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("TestPlanFromCaptures")


def stitch_screenshots(p_left: Path, p_right: Path, out_path: Path) -> Path:
    """Stitches left and right screenshots with labeled header."""
    logger.info(f"Stitching left={p_left.name} and right={p_right.name}...")
    im_left = Image.open(p_left)
    im_right = Image.open(p_right)

    banner_h = 60
    total_w = im_left.width + im_right.width
    max_h = max(im_left.height, im_right.height) + banner_h

    comp = Image.new("RGB", (total_w, max_h), color=(18, 22, 30))
    comp.paste(im_left, (0, banner_h))
    comp.paste(im_right, (im_left.width, banner_h))

    draw = ImageDraw.Draw(comp)
    draw.text((30, 20), "◀ LEFT MONITOR: VOLUME PROFILE & FOOTPRINT", fill=(74, 222, 128))
    draw.text((im_left.width + 30, 20), "▶ RIGHT MONITOR: BOOKMAP (LIQUIDITY HEATMAP & CVD)", fill=(96, 165, 250))
    draw.line([(im_left.width, 0), (im_left.width, max_h)], fill=(70, 80, 100), width=4)

    # Resize to standard 3200px width for fast AI tokenization
    target_w = 3200
    target_h = int(max_h * (target_w / total_w))
    resized = comp.resize((target_w, target_h), Image.Resampling.LANCZOS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    resized.save(out_path, quality=92)
    logger.info(f"Stitched composite saved to: {out_path} ({resized.size})")
    return out_path


def resolve_capture_image(captures_dir: Path) -> Path:
    """Selects or stitches screenshots from captures folder."""
    stitched_path = captures_dir / "test_stitched_overview.png"
    if stitched_path.exists():
        return stitched_path

    png_files = sorted(list(captures_dir.glob("Screenshot*.png")))
    if len(png_files) >= 2:
        return stitch_screenshots(png_files[0], png_files[1], stitched_path)
    elif len(png_files) == 1:
        return png_files[0]

    all_pngs = sorted(list(captures_dir.glob("*.png")))
    if all_pngs:
        return all_pngs[0]

    raise FileNotFoundError(f"No chart images found in {captures_dir}")


def verify_or_detect_chat_id(bot_token: str, chat_id: str) -> str:
    """
    Ensures chat_id is valid. If chat_id is the bot username, polls Telegram
    to automatically retrieve the user's numeric chat ID from incoming messages.
    """
    if chat_id and chat_id.lstrip("-").isdigit():
        return chat_id

    print("\n" + "=" * 60)
    print("⚠️ CẢNH BÁO TELEGRAM CHAT ID:")
    print(f"Giá trị TELEGRAM_CHAT_ID hiện tại là: '{chat_id}'")
    print("Telegram cần Chat ID dạng SỐ (ví dụ: 123456789) của tài khoản của bạn,")
    print("chứ không phải username của bot (@double_eleven_bot).")
    print("\n👉 BƯỚC CẦN LÀM:")
    print("1. Mở app Telegram trên điện thoại hoặc máy tính.")
    print("2. Tìm kiếm bot: @double_eleven_bot")
    print("3. Bấm START (hoặc gửi bất kỳ tin nhắn nào, ví dụ: 'hi')")
    print("\nĐang chờ bạn gửi tin nhắn cho bot để tự động lấy Chat ID (chờ tối đa 40s)...")
    print("=" * 60)

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    for i in range(40):
        try:
            resp = httpx.get(url, timeout=5.0)
            if resp.status_code == 200:
                updates = resp.json().get("result", [])
                for u in reversed(updates):
                    if "message" in u and "chat" in u["message"]:
                        detected_id = str(u["message"]["chat"]["id"])
                        first_name = u["message"]["chat"].get("first_name", "")
                        username = u["message"]["chat"].get("username", "")
                        print(f"\n✅ ĐÃ TÌM THẤY BẠN TRÊN TELEGRAM!")
                        print(f"• Tên: {first_name} (@{username})")
                        print(f"• Chat ID số: {detected_id}")

                        # Update .env
                        env_path = Path(".env")
                        if env_path.exists():
                            content = env_path.read_text(encoding="utf-8")
                            content = content.replace(f"TELEGRAM_CHAT_ID={chat_id}", f"TELEGRAM_CHAT_ID={detected_id}")
                            env_path.write_text(content, encoding="utf-8")
                            print("✅ Đã tự động cập nhật TELEGRAM_CHAT_ID vào file .env!\n")
                        return detected_id
        except Exception as e:
            pass
        time.sleep(1)
        print(".", end="", flush=True)

    print("\n❌ Chưa nhận được tin nhắn từ bạn. Vui lòng kiểm tra lại bot @double_eleven_bot và gửi /start.")
    return chat_id


def main():
    parser = argparse.ArgumentParser(description="Test Plan Generation from Captures Folder")
    parser.add_argument("--image", type=str, default=None, help="Custom image path in data/captures")
    parser.add_argument("--stitch", action="store_true", help="Force re-stitching screenshots")
    args = parser.parse_args()

    cfg = load_config()
    captures_dir = Path("data/captures")

    print("\n🚀 BẮT ĐẦU TEST QUY TRÌNH LÊN PLAN TỪ THƯ MỤC CAPTURES...")

    # 1. Check & verify Telegram
    bot_token = cfg.telegram.bot_token
    chat_id = verify_or_detect_chat_id(bot_token, cfg.telegram.chat_id)
    cfg.telegram.chat_id = chat_id

    # 2. Resolve image
    if args.image:
        image_path = Path(args.image)
    elif args.stitch:
        png_files = sorted(list(captures_dir.glob("Screenshot*.png")))
        if len(png_files) >= 2:
            image_path = stitch_screenshots(png_files[0], png_files[1], captures_dir / "test_stitched_overview.png")
        else:
            image_path = resolve_capture_image(captures_dir)
    else:
        image_path = resolve_capture_image(captures_dir)

    print(f"📸 Sử dụng hình ảnh phân tích: {image_path} ({os.path.getsize(image_path) / (1024*1024):.2f} MB)")

    # 3. Initialize components
    storage = CycleStorage(db_path=cfg.storage.db_path, jsonl_path=cfg.storage.log_file)
    notifier = TelegramNotifier(cfg.telegram, storage)
    capture_svc = ScreenCaptureService(output_dir=cfg.capture.output_dir)
    analyzer = ArgonClient(cfg.model)

    planner = DailyPlanner(
        config=cfg,
        analyzer=analyzer,
        capture_service=capture_svc,
    )

    # 4. Generate plan via Argon AI
    print("\n🧠 Đang gọi Argon AI để phân tích Volume Profile, Footprint và Bookmap...")
    start_t = time.perf_counter()
    plan = planner.generate_plan(image_path=image_path)
    elapsed = time.perf_counter() - start_t

    if not plan:
        print("\n❌ LỖI: Không thể tạo Daily Plan từ Argon AI. Vui lòng kiểm tra log.")
        sys.exit(1)

    print(f"\n✅ ĐÃ TẠO DAILY PLAN THÀNH CÔNG trong {elapsed:.2f}s!")
    print("=" * 60)
    print(planner.format_plan_message(plan))
    print("=" * 60)

    # 5. Send to Telegram
    print("\n📲 Đang gửi kết quả Daily Plan + ảnh chart sang Telegram...")
    notifier.send_daily_plan(plan=plan, image_path=image_path)
    print("✅ ĐÃ GỬI XONG! Vui lòng kiểm tra Telegram của bạn.")


if __name__ == "__main__":
    main()

