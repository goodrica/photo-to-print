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

    Strategy (projection-profile, robust to ticks touching the ruler edge):
      1. Grayscale + adaptive threshold to isolate dark marks on a light ruler.
      2. Find the dominant straight edge (the ruler body) with HoughLinesP to
         get the ruler's orientation.
      3. Rotate the thresholded image so the ruler axis is horizontal.
      4. Collapse to a 1-D profile by summing ink per column; ruler ticks show
         up as periodic peaks.
      5. The dominant spatial frequency of that profile (via autocorrelation)
         is the pixel distance of one tick pitch.
      6. pixels_per_mm = tick_spacing_px / tick_pitch_mm.

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

    # Find the dominant straight edge = the ruler axis, to get orientation.
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
    axis_angle_deg = np.degrees(np.arctan2(y2 - y1, x2 - x1))

    # Rotate so the ruler axis is horizontal, then profile columns.
    h, w = thresh.shape
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), axis_angle_deg, 1.0)
    rotated = cv2.warpAffine(thresh, M, (w, h), flags=cv2.INTER_NEAREST)

    # Column ink profile: periodic peaks = ticks.
    profile = rotated.sum(axis=0).astype(np.float64)
    if profile.max() <= 0:
        return None
    profile -= profile.mean()

    # Autocorrelation to find the dominant period (tick spacing in px).
    ac = np.correlate(profile, profile, mode="full")[len(profile) - 1:]
    if ac[0] <= 0:
        return None
    ac = ac / ac[0]

    # Search a plausible tick-spacing range in pixels.
    min_lag = 4
    max_lag = min(len(ac) - 1, max(min_lag + 1, w // 4))
    if max_lag <= min_lag:
        return None
    search = ac[min_lag:max_lag]

    # First strong local maximum = fundamental tick period.
    peak_lag = None
    for i in range(1, len(search) - 1):
        if search[i] > search[i - 1] and search[i] >= search[i + 1] and search[i] > 0.2:
            peak_lag = i + min_lag
            break
    if peak_lag is None:
        peak_lag = int(np.argmax(search)) + min_lag
        if search[peak_lag - min_lag] <= 0.15:
            return None

    tick_px = float(peak_lag)
    pixels_per_mm = tick_px / tick_pitch_mm

    # Confidence: autocorrelation strength at the detected period, and how many
    # full periods fit across the ruler (more periods = more reliable).
    ac_strength = float(np.clip(ac[peak_lag], 0.0, 1.0))
    periods = w / tick_px if tick_px > 0 else 0
    coverage = float(np.clip(periods / 30.0, 0.0, 1.0))
    confidence = round(0.65 * ac_strength + 0.35 * coverage, 3)

    if confidence < 0.15:
        return None

    return ScaleCalibration(
        pixels_per_mm=pixels_per_mm,
        confidence=confidence,
        line_count=int(periods) + 1,
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
