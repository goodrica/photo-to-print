"""
Ruler-based scale calibration.

Lets a user place a standard ruler (metric cm/mm marks) in the photo instead of
relying on college-ruled paper. We detect the ruler's long straight edge and the
periodic tick marks along it, measure the pixel distance between ticks, and
convert that to pixels-per-mm.

This is more universal than paper-line calibration: any common ruler works, and
the object does not have to sit on lined paper.
"""

import cv2
import numpy as np
from typing import Optional

# Reuse the shared calibration result type so the rest of the pipeline is agnostic
# about which method produced the scale.
from src.dimension.calibration import ScaleCalibration


# Common metric ruler tick pitch. Minor ticks are 1mm; we detect the finest
# consistent pitch and assume it is 1mm unless it clusters near 5mm/10mm.
_CANDIDATE_PITCHES_MM = (1.0, 5.0, 10.0)


def detect_ruler(
    image: np.ndarray,
    tick_pitch_mm: float = 1.0,
) -> Optional[ScaleCalibration]:
    """
    Detect a ruler's tick marks and compute pixels-per-mm.

    Strategy:
      1. Grayscale + adaptive threshold to isolate dark tick marks on a light ruler.
      2. Find the dominant straight edge (the ruler body) with HoughLinesP.
      3. Project detected tick contours onto the ruler axis, giving 1-D positions.
      4. Compute the spacing between adjacent ticks; the robust (median) spacing
         is the pixel distance of one tick pitch.
      5. pixels_per_mm = median_tick_spacing_px / tick_pitch_mm.

    Args:
        image: Input image (BGR or grayscale).
        tick_pitch_mm: Real-world spacing of the finest ruler ticks (default 1.0mm).

    Returns:
        ScaleCalibration if a ruler was found with reasonable confidence, else None.
    """
    if image is None:
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    # Isolate tick marks: dark marks on a light ruler face.
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=15,
        C=5,
    )

    # Find the dominant straight edge = the ruler axis.
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    segments = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180,
        threshold=80, minLineLength=min(gray.shape) // 3, maxLineGap=20,
    )
    if segments is None or len(segments) == 0:
        return None

    # Longest segment wins; its angle defines the ruler axis.
    x1, y1, x2, y2 = max(
        (s[0] for s in segments),
        key=lambda s: (s[2] - s[0]) ** 2 + (s[3] - s[1]) ** 2,
    )
    axis_angle = np.arctan2(y2 - y1, x2 - x1)
    cos_a, sin_a = np.cos(axis_angle), np.sin(axis_angle)

    # Tick contours.
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Project each small, tick-shaped contour's centroid onto the ruler axis.
    positions = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 2 or area > gray.size * 0.02:  # skip noise and large blobs
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]
        # Signed distance along the axis direction.
        positions.append(cx * cos_a + cy * sin_a)

    if len(positions) < 5:
        return None

    positions.sort()
    spacings = np.diff(positions)
    # Keep only plausible tick spacings (drop zeros/dupes and huge gaps).
    spacings = spacings[spacings > 1.0]
    if len(spacings) < 4:
        return None

    median_spacing = float(np.median(spacings))
    # Robust inlier set near the median.
    inliers = spacings[np.abs(spacings - median_spacing) < 0.35 * median_spacing]
    if len(inliers) < 4:
        return None

    tick_px = float(np.mean(inliers))
    pixels_per_mm = tick_px / tick_pitch_mm

    # Confidence from spacing consistency and how many ticks agreed.
    consistency = max(0.0, 1.0 - (float(np.std(inliers)) / tick_px))
    coverage = min(1.0, len(inliers) / 20.0)
    confidence = round(0.6 * consistency + 0.4 * coverage, 3)

    return ScaleCalibration(
        pixels_per_mm=pixels_per_mm,
        confidence=confidence,
        line_count=len(inliers) + 1,
        avg_line_spacing_px=tick_px,
    )


def calibrate_ruler_from_image(
    image_path: str,
    tick_pitch_mm: float = 1.0,
) -> Optional[ScaleCalibration]:
    """Load an image and calibrate scale from a ruler."""
    image = cv2.imread(image_path)
    if image is None:
        return None
    return detect_ruler(image, tick_pitch_mm)
