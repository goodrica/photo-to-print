"""Test scale calibration from college-ruled paper."""

import pytest
import numpy as np
import cv2
from pathlib import Path
from src.dimension.calibration import (
    detect_paper_lines,
    calibrate_from_image,
    pixels_to_mm,
    mm_to_pixels,
    ScaleCalibration,
)


def create_test_image_with_lines(
    width: int = 800,
    height: int = 600,
    line_spacing_px: float = 71.0,  # 10mm at 7.1 px/mm
    num_lines: int = 8
) -> np.ndarray:
    """Create synthetic test image with horizontal lines."""
    # White background
    image = np.ones((height, width, 3), dtype=np.uint8) * 255
    
    # Draw horizontal lines
    start_y = 50
    for i in range(num_lines):
        y = int(start_y + i * line_spacing_px)
        if y < height - 50:
            cv2.line(image, (0, y), (width, y), (0, 0, 255), 2)
    
    return image


def test_detect_paper_lines_synthetic():
    """Test line detection on synthetic image."""
    # Create test image with known spacing
    line_spacing_px = 71.0  # pixels
    expected_spacing_mm = 7.1  # mm
    expected_px_per_mm = line_spacing_px / expected_spacing_mm  # 10 px/mm
    
    image = create_test_image_with_lines(
        line_spacing_px=line_spacing_px,
        num_lines=8
    )
    
    calibration = detect_paper_lines(image, expected_spacing_mm)
    
    assert calibration is not None
    assert calibration.pixels_per_mm > 0
    # Allow 20% tolerance for detection accuracy
    assert abs(calibration.pixels_per_mm - expected_px_per_mm) < 2.0
    assert calibration.confidence > 0.5
    assert calibration.line_count >= 2


def test_detect_paper_lines_insufficient():
    """Test that detection fails with too few lines."""
    # Create image with only 1 line
    image = np.ones((600, 800, 3), dtype=np.uint8) * 255
    cv2.line(image, (0, 100), (800, 100), (0, 0, 255), 2)
    
    calibration = detect_paper_lines(image)
    
    # Should fail - need at least 2 lines
    assert calibration is None


def test_pixels_to_mm_conversion():
    """Test pixel to mm conversion."""
    calibration = ScaleCalibration(
        pixels_per_mm=10.0,
        confidence=0.95,
        line_count=5,
        avg_line_spacing_px=71.0
    )
    
    # 100 pixels at 10 px/mm = 10 mm
    assert pixels_to_mm(100.0, calibration) == 10.0
    
    # 50 pixels at 10 px/mm = 5 mm
    assert pixels_to_mm(50.0, calibration) == 5.0


def test_mm_to_pixels_conversion():
    """Test mm to pixel conversion."""
    calibration = ScaleCalibration(
        pixels_per_mm=10.0,
        confidence=0.95,
        line_count=5,
        avg_line_spacing_px=71.0
    )
    
    # 10 mm at 10 px/mm = 100 pixels
    assert mm_to_pixels(10.0, calibration) == 100.0
    
    # 5 mm at 10 px/mm = 50 pixels
    assert mm_to_pixels(5.0, calibration) == 50.0


def test_calibrate_from_image_file(tmp_path):
    """Test calibration from saved image file."""
    # Create and save test image
    image = create_test_image_with_lines(line_spacing_px=71.0, num_lines=8)
    image_path = tmp_path / "test_paper.png"
    cv2.imwrite(str(image_path), image)
    
    # Calibrate
    calibration = calibrate_from_image(str(image_path), expected_spacing_mm=7.1)
    
    assert calibration is not None
    assert calibration.pixels_per_mm > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
