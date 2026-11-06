from pathlib import Path
from PIL import Image
import pytest
from src.capture.screen_capture import BlackImageError, ScreenCaptureService


def test_black_image_detection(tmp_path: Path):
    svc = ScreenCaptureService(output_dir=str(tmp_path), black_threshold=5.0)

    # Pure black image
    black_img = Image.new("RGB", (100, 100), color=(0, 0, 0))
    is_black, lum = svc.is_black_image(black_img)
    assert is_black is True
    assert lum == 0.0

    # Normal chart image with color
    chart_img = Image.new("RGB", (100, 100), color=(100, 150, 200))
    is_black, lum = svc.is_black_image(chart_img)
    assert is_black is False
    assert lum > 5.0


def test_cleanup_captures(tmp_path: Path):
    svc = ScreenCaptureService(output_dir=str(tmp_path))
    (tmp_path / "chart_left_1.png").write_text("test")
    (tmp_path / "chart_right_1.png").write_text("test")
    (tmp_path / "chart_stitched_1.png").write_text("test")
    (tmp_path / "keep_this.txt").write_text("keep")

    assert len(list(tmp_path.glob("*.png"))) == 3
    deleted = svc.cleanup_captures()
    assert deleted == 3
    assert len(list(tmp_path.glob("*.png"))) == 0
    assert (tmp_path / "keep_this.txt").exists()

