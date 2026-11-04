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

    def capture(self, filename: Optional[str] = None) -> Path:
        """
        Captures the screen or chart window, validates it, and saves it.
        Returns the path to the saved PNG image.
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"chart_{timestamp}.png"

        save_path = self.output_dir / filename
        system_name = platform.system()

        image: Optional[Image.Image] = None

        if system_name == "Windows":
            image = self._capture_windows()
        elif system_name == "Darwin":
            image = self._capture_macos()
        else:
            image = self._capture_generic()

        if image is None:
            raise CaptureError("Failed to acquire screenshot image.")

        # Check for black or blank screen (AC-2)
        is_black, lum = self.is_black_image(image)
        if is_black:
            # Still save for debug/audit if needed, then raise
            image.save(save_path)
            logger.error(f"Captured black image (luminance: {lum:.2f} < threshold {self.black_threshold})")
            raise BlackImageError(f"Image is completely black or blank (mean luminance {lum:.2f})")

        # Save valid PNG
        image.save(save_path)
        logger.info(f"Captured chart saved to {save_path} (luminance: {lum:.2f})")
        return save_path

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

