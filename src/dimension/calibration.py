"""
Scale calibration from college-ruled paper.

College-ruled paper has lines spaced exactly 7.1mm (0.28") apart.
By detecting these lines in the photo, we can compute pixels-per-mm
and convert all object measurements to real-world dimensions.
"""

import cv2
import numpy as np
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class ScaleCalibration:
    """Result of scale calibration."""
    pixels_per_mm: float
    confidence: float
    line_count: int
    avg_line_spacing_px: float


def detect_paper_lines(
    image: np.ndarray,
    expected_spacing_mm: float = 7.1
) -> Optional[ScaleCalibration]:
    """
    Detect horizontal lines from college-ruled paper and compute scale.
    
    Args:
        image: Input image (BGR or grayscale)
        expected_spacing_mm: Expected line spacing in mm (7.1mm for college rule)
    
    Returns:
        ScaleCalibration if successful, None if detection failed
    """
    # Convert to grayscale if needed
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Detect edges
    edges = cv2.Canny(blurred, 50, 150, apertureSize=3)
    
    # Detect horizontal lines using Hough transform
    # rho=1 (1 pixel resolution), theta=pi/2 (horizontal only)
    lines = cv2.HoughLines(
        edges,
        rho=1,
        theta=np.pi/180,
        threshold=100,
        min_theta=np.pi/2 - 0.1,  # Only near-horizontal lines
        max_theta=np.pi/2 + 0.1
    )
    
    if lines is None or len(lines) < 2:
        return None
    
    # Extract y-coordinates of detected lines
    y_coords = []
    for line in lines:
        rho, theta = line[0]
        # For horizontal lines, theta ≈ pi/2, so y ≈ rho
        y_coords.append(rho)
    
    # Sort y-coordinates
    y_coords.sort()
    
    # Remove duplicates (lines detected multiple times)
    # Keep lines that are at least 50 pixels apart
    filtered_y = [y_coords[0]]
    for y in y_coords[1:]:
        if y - filtered_y[-1] > 50:
            filtered_y.append(y)
    
    if len(filtered_y) < 2:
        return None
    
    # Calculate spacings between adjacent lines
    spacings = np.diff(filtered_y)
    
    # Filter out outliers (spacings that are very different from median)
    median_spacing = np.median(spacings)
    valid_spacings = spacings[np.abs(spacings - median_spacing) < 0.3 * median_spacing]
    
    if len(valid_spacings) < 2:
        return None
    
    # Average spacing in pixels
    avg_spacing_px = np.mean(valid_spacings)
    
    # Compute pixels per mm
    pixels_per_mm = avg_spacing_px / expected_spacing_mm
    
    # Confidence based on consistency (lower variance = higher confidence)
    std_spacing = np.std(valid_spacings)
    confidence = max(0, 1.0 - (std_spacing / avg_spacing_px))
    
    return ScaleCalibration(
        pixels_per_mm=pixels_per_mm,
        confidence=confidence,
        line_count=len(filtered_y),
        avg_line_spacing_px=avg_spacing_px
    )


def calibrate_from_image(
    image_path: str,
    expected_spacing_mm: float = 7.1
) -> Optional[ScaleCalibration]:
    """
    Load image and calibrate scale from paper lines.
    
    Args:
        image_path: Path to image file
        expected_spacing_mm: Expected line spacing in mm
    
    Returns:
        ScaleCalibration if successful, None if failed
    """
    image = cv2.imread(image_path)
    if image is None:
        return None
    
    return detect_paper_lines(image, expected_spacing_mm)


def pixels_to_mm(
    pixels: float,
    calibration: ScaleCalibration
) -> float:
    """Convert pixel measurement to mm using calibration."""
    return pixels / calibration.pixels_per_mm


def mm_to_pixels(
    mm: float,
    calibration: ScaleCalibration
) -> float:
    """Convert mm measurement to pixels using calibration."""
    return mm * calibration.pixels_per_mm


def visualize_calibration(
    image: np.ndarray,
    calibration: ScaleCalibration,
    output_path: Optional[str] = None
) -> np.ndarray:
    """
    Draw detected lines and scale info on image for debugging.
    
    Args:
        image: Input image
        calibration: Scale calibration result
        output_path: If provided, save annotated image
    
    Returns:
        Annotated image
    """
    annotated = image.copy()
    
    # Add text overlay
    text_lines = [
        f"Scale: {calibration.pixels_per_mm:.2f} px/mm",
        f"Confidence: {calibration.confidence:.2%}",
        f"Lines detected: {calibration.line_count}",
        f"Avg spacing: {calibration.avg_line_spacing_px:.1f} px"
    ]
    
    y_offset = 30
    for line in text_lines:
        cv2.putText(
            annotated,
            line,
            (10, y_offset),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )
        y_offset += 30
    
    if output_path:
        cv2.imwrite(output_path, annotated)
    
    return annotated
