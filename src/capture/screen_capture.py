import logging
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageStat
import mss

logger = logging.getLogger(__name__)


class CaptureError(Exception):
    """Base exception for screen capture failures."""
    pass


class BlackImageError(CaptureError):
    """Raised when the captured image is black or blank."""
    pass


class WindowNotFoundError(CaptureError):
    """Raised when the target window is not found."""
    pass


class ScreenCaptureService:
    def __init__(
        self,
        output_dir: str = "data/captures",
        window_title: str = "MetaTrader 5",
        black_threshold: float = 5.0,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.window_title = window_title
        self.black_threshold = black_threshold

    def is_black_image(self, image: Image.Image) -> Tuple[bool, float]:
        """Calculates image luminance and determines if it is effectively black."""
        grayscale = image.convert("L")
        stat = ImageStat.Stat(grayscale)
        mean_luminance = stat.mean[0]
        return mean_luminance < self.black_threshold, mean_luminance

    def capture_dual_monitors(self, prefix: str = "chart") -> Tuple[Path, Path, Path]:
        """
        Captures each monitor individually:
        - Left monitor: VP & Footprint -> saved as {prefix}_left_{timestamp}.png
        - Right monitor: Bookmap -> saved as {prefix}_right_{timestamp}.png
        Also creates and saves the stitched overview {prefix}_stitched_{timestamp}.png for AI multimodal inspection.
        Returns: (left_path, right_path, stitched_path)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        with mss.mss() as sct:
            physical_monitors = sct.monitors[1:]

            if len(physical_monitors) >= 2:
                # Sort horizontally: left screen (VP/Footprint) vs right screen (Bookmap)
                sorted_monitors = sorted(physical_monitors, key=lambda m: m["left"])
                left_mon = sorted_monitors[0]
                right_mon = sorted_monitors[1]

                # 1. Grab & save Left Monitor (VP & Footprint)
                raw_left = sct.grab(left_mon)
                img_left = Image.frombytes("RGB", raw_left.size, raw_left.bgra, "raw", "BGRX")
                is_black, lum_left = self.is_black_image(img_left)
                if is_black:
                    raise BlackImageError(f"Left monitor image is black (luminance {lum_left:.2f})")
                left_path = self.output_dir / f"{prefix}_left_{timestamp}.png"
                img_left.save(left_path)
                logger.info(f"Saved Left Monitor screenshot: {left_path} ({img_left.size})")

                # 2. Grab & save Right Monitor (Bookmap)
                raw_right = sct.grab(right_mon)
                img_right = Image.frombytes("RGB", raw_right.size, raw_right.bgra, "raw", "BGRX")
                is_black, lum_right = self.is_black_image(img_right)
                if is_black:
                    raise BlackImageError(f"Right monitor image is black (luminance {lum_right:.2f})")
                right_path = self.output_dir / f"{prefix}_right_{timestamp}.png"
                img_right.save(right_path)
                logger.info(f"Saved Right Monitor screenshot: {right_path} ({img_right.size})")

                # 3. Stitch side-by-side with section labels
                banner_height = 40
                total_width = img_left.width + img_right.width
                max_content_height = max(img_left.height, img_right.height)
                total_height = max_content_height + banner_height

                composite = Image.new("RGB", (total_width, total_height), color=(20, 24, 32))
                composite.paste(img_left, (0, banner_height))
                composite.paste(img_right, (img_left.width, banner_height))

                from PIL import ImageDraw
                draw = ImageDraw.Draw(composite)
                draw.text(
                    (20, 12),
                    "◀ LEFT MONITOR: VOLUME PROFILE & FOOTPRINT",
                    fill=(74, 222, 128),
                )
                draw.text(
                    (img_left.width + 20, 12),
                    "▶ RIGHT MONITOR: BOOKMAP (LIQUIDITY HEATMAP & CVD)",
                    fill=(96, 165, 250),
                )
                draw.line([(img_left.width, 0), (img_left.width, total_height)], fill=(60, 70, 90), width=3)

                stitched_path = self.output_dir / f"{prefix}_stitched_{timestamp}.png"
                composite.save(stitched_path, quality=92)
                logger.info(f"Saved Stitched Overview: {stitched_path} ({composite.size})")

                return left_path, right_path, stitched_path

            else:
                # Single monitor fallback
                target_mon = physical_monitors[0] if physical_monitors else sct.monitors[0]
                sct_img = sct.grab(target_mon)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                path = self.output_dir / f"{prefix}_main_{timestamp}.png"
                img.save(path)
                return path, path, path

    def cleanup_captures(self) -> int:
        """
        Deletes all images in the captures folder after processing and Telegram transmission.
        """
        deleted_count = 0
        if not self.output_dir.exists():
            return 0

        for pattern in ("*.png", "*.jpg", "*.jpeg"):
            for file_path in self.output_dir.glob(pattern):
                try:
                    file_path.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Could not delete {file_path}: {e}")

        logger.info(f"🧹 Cleaned up {deleted_count} image(s) from {self.output_dir}.")
        return deleted_count

    def capture(self, filename: Optional[str] = None) -> Path:
        """
        Captures dual monitors, saves individual and stitched images, and returns stitched path.
        """
        left_path, right_path, stitched_path = self.capture_dual_monitors(prefix="chart")
        if filename:
            target_path = self.output_dir / filename
            if stitched_path != target_path:
                stitched_path.rename(target_path)
                return target_path
        return stitched_path

    def _capture_windows(self) -> Image.Image:
        """Capture window or primary screen on Windows."""
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(self.window_title)
            if windows:
                win = windows[0]
                if win.isMinimized:
                    win.restore()
                win.activate()
                import pyautogui
                return pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
        except Exception as e:
            logger.warning(f"Windows window-specific capture failed ({e}), falling back to mss")

        return self._capture_generic()

    def _capture_macos(self) -> Image.Image:
        """Capture on macOS using screencapture or mss."""
        return self._capture_generic()

    def _capture_generic(self) -> Image.Image:
        """
        Dual-monitor aware capture:
        Finds monitors, sorts horizontally (left screen = VP & Footprint, right screen = Bookmap),
        and stitches them side-by-side with clear visual labels for AI multimodal analysis.
        """
        with mss.mss() as sct:
            physical_monitors = sct.monitors[1:]

            if len(physical_monitors) >= 2:
                # Sort monitors horizontally by their X 'left' coordinate
                sorted_monitors = sorted(physical_monitors, key=lambda m: m["left"])
                left_mon = sorted_monitors[0]
                right_mon = sorted_monitors[1]

                # Grab left monitor (Volume Profile & Footprint)
                raw_left = sct.grab(left_mon)
                img_left = Image.frombytes("RGB", raw_left.size, raw_left.bgra, "raw", "BGRX")

                # Grab right monitor (Bookmap)
                raw_right = sct.grab(right_mon)
                img_right = Image.frombytes("RGB", raw_right.size, raw_right.bgra, "raw", "BGRX")

                # Stitch horizontally
                banner_height = 40
                total_width = img_left.width + img_right.width
                max_content_height = max(img_left.height, img_right.height)
                total_height = max_content_height + banner_height

                composite = Image.new("RGB", (total_width, total_height), color=(20, 24, 32))
                composite.paste(img_left, (0, banner_height))
                composite.paste(img_right, (img_left.width, banner_height))

                # Draw section headers on banner
                from PIL import ImageDraw
                draw = ImageDraw.Draw(composite)
                draw.text(
                    (20, 12),
                    "◀ LEFT MONITOR: VOLUME PROFILE & FOOTPRINT",
                    fill=(74, 222, 128),
                )
                draw.text(
                    (img_left.width + 20, 12),
                    "▶ RIGHT MONITOR: BOOKMAP (LIQUIDITY HEATMAP & CVD)",
                    fill=(96, 165, 250),
                )
                draw.line([(img_left.width, 0), (img_left.width, total_height)], fill=(60, 70, 90), width=3)

                return composite

            elif len(physical_monitors) == 1:
                # Single monitor fallback
                sct_img = sct.grab(physical_monitors[0])
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            else:
                sct_img = sct.grab(sct.monitors[0])
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

