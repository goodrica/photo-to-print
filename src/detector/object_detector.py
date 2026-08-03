"""
Object detection and classification for functional objects.

Uses a hybrid approach:
1. HuggingFace Inference API for classification (lightweight)
2. OpenCV for bounding box detection
3. Vision LLM for interpreting object type and suggesting parameters
"""

import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ObjectCategory(Enum):
    """Categories of functional objects we can recreate."""
    HOOK = "hook"
    BRACKET = "bracket"
    HOLDER = "holder"
    CLIP = "clip"
    KNOB = "knob"
    BASKET = "basket"
    SPACER = "spacer"
    UNKNOWN = "unknown"


@dataclass
class DetectedObject:
    """A detected object with bounding box and classification."""
    category: ObjectCategory
    bbox: Tuple[int, int, int, int]  # (x, y, width, height) in pixels
    confidence: float
    suggested_params: Dict[str, float]


@dataclass
class DetectionResult:
    """Result of object detection on an image."""
    objects: List[DetectedObject]
    image_size: Tuple[int, int]  # (width, height)


# Mapping from common object names to our categories
OBJECT_NAME_MAPPING = {
    # Hooks
    "hook": ObjectCategory.HOOK,
    "s-hook": ObjectCategory.HOOK,
    "coat hook": ObjectCategory.HOOK,
    "garage hook": ObjectCategory.HOOK,
    
    # Brackets
    "bracket": ObjectCategory.BRACKET,
    "l-bracket": ObjectCategory.BRACKET,
    "shelf bracket": ObjectCategory.BRACKET,
    "corner bracket": ObjectCategory.BRACKET,
    
    # Holders
    "holder": ObjectCategory.HOLDER,
    "cup": ObjectCategory.HOLDER,
    "mug": ObjectCategory.HOLDER,
    "tool holder": ObjectCategory.HOLDER,
    "pen holder": ObjectCategory.HOLDER,
    "phone holder": ObjectCategory.HOLDER,
    
    # Clips
    "clip": ObjectCategory.CLIP,
    "cable clip": ObjectCategory.CLIP,
    "panel clip": ObjectCategory.CLIP,
    
    # Knobs
    "knob": ObjectCategory.KNOB,
    "dial": ObjectCategory.KNOB,
    "handle": ObjectCategory.KNOB,
    
    # Baskets
    "basket": ObjectCategory.BASKET,
    "bin": ObjectCategory.BASKET,
    "container": ObjectCategory.BASKET,
    "box": ObjectCategory.BASKET,
    
    # Spacers
    "spacer": ObjectCategory.SPACER,
    "washer": ObjectCategory.SPACER,
    "ring": ObjectCategory.SPACER,
}


def detect_objects_opencv(image: np.ndarray, debug: bool = False) -> List[Tuple[int, int, int, int]]:
    """
    Detect object candidates using OpenCV (contour detection).
    
    This is a simple fallback when ML models aren't available.
    Filters out full-width contours (paper lines) and small noise.
    
    Args:
        image: Input image (BGR)
        debug: If True, save intermediate images for debugging
    
    Returns:
        List of bounding boxes as (x, y, width, height)
    """
    h, w = image.shape[:2]
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Apply threshold - use Otsu's for better results
    thresh_val, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    if debug:
        cv2.imwrite("debug_thresh.png", thresh)
        print(f"  Debug: Otsu threshold value = {thresh_val}")
    
    # Morphological close to merge nearby regions (small kernel to preserve object shape)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    if debug:
        cv2.imwrite("debug_closed.png", closed)
    
    # Find contours
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if debug:
        print(f"  Debug: Found {len(contours)} contours before filtering")
    
    # Filter by area and aspect ratio
    min_area = (w * h) * 0.005  # At least 0.5% of image
    max_width_ratio = 0.7  # Object shouldn't span 70%+ of image width (that's a paper line)
    max_height_ratio = 0.7  # Or 70%+ of height
    
    bboxes = []
    for i, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        x, y, cw, ch = cv2.boundingRect(contour)
        
        if debug:
            print(f"  Debug: Contour {i}: area={area}, bbox=({x},{y},{cw},{ch})")
        
        # Skip if too small
        if area < min_area:
            if debug:
                print(f"    -> Skipped: too small")
            continue
        
        # Skip if spans full width/height (paper lines, background)
        if cw > w * max_width_ratio or ch > h * max_height_ratio:
            if debug:
                print(f"    -> Skipped: too wide/tall")
            continue
        
        bboxes.append((x, y, cw, ch))
        if debug:
            print(f"    -> Accepted")
    
    return bboxes


def classify_object_by_name(object_name: str) -> ObjectCategory:
    """
    Classify object based on name string.
    
    Args:
        object_name: Name or description of object
    
    Returns:
        ObjectCategory
    """
    name_lower = object_name.lower()
    
    # Check direct mapping
    if name_lower in OBJECT_NAME_MAPPING:
        return OBJECT_NAME_MAPPING[name_lower]
    
    # Check if any key is contained in the name
    for key, category in OBJECT_NAME_MAPPING.items():
        if key in name_lower:
            return category
    
    return ObjectCategory.UNKNOWN


def suggest_default_params(
    category: ObjectCategory,
    bbox: Tuple[int, int, int, int],
    pixels_per_mm: float
) -> Dict[str, float]:
    """
    Suggest default parameters based on category and bounding box.
    
    Args:
        category: Object category
        bbox: Bounding box (x, y, width, height) in pixels
        pixels_per_mm: Scale calibration
    
    Returns:
        Dictionary of suggested parameters in mm (Python floats, not numpy)
    """
    _, _, w_px, h_px = bbox
    
    # Convert to mm and ensure Python float (not numpy)
    w_mm = float(w_px / pixels_per_mm)
    h_mm = float(h_px / pixels_per_mm)
    
    if category == ObjectCategory.HOOK:
        return {
            "height": h_mm,
            "width": float(w_mm * 0.4),
            "depth": float(w_mm * 0.3),
            "thickness": 5.0,
            "mount_hole_dia": 6.0,
        }
    
    elif category == ObjectCategory.BRACKET:
        return {
            "length": w_mm,
            "width": float(w_mm * 0.5),
            "height": float(h_mm * 0.5),
            "thickness": 5.0,
            "hole_pattern": "single",
        }
    
    elif category == ObjectCategory.HOLDER:
        diameter = float(min(w_mm, h_mm))
        return {
            "inner_dia": float(diameter * 0.8),
            "height": h_mm,
            "wall_thickness": 3.0,
            "base_dia": diameter,
        }
    
    elif category == ObjectCategory.SPACER:
        diameter = float(min(w_mm, h_mm))
        return {
            "outer_dia": diameter,
            "inner_dia": float(diameter * 0.5),
            "thickness": 5.0,
        }
    
    else:
        return {
            "length": w_mm,
            "width": float(w_mm * 0.5),
            "height": h_mm,
        }


def detect_objects_with_ml(
    image: np.ndarray,
    classifier_fn=None
) -> List[DetectedObject]:
    """
    Detect objects using ML classifier.
    
    Args:
        image: Input image
        classifier_fn: Optional function that takes image and returns list of (name, bbox, confidence)
    
    Returns:
        List of DetectedObject
    """
    if classifier_fn is None:
        # Fallback to OpenCV detection
        bboxes = detect_objects_opencv(image)
        return [
            DetectedObject(
                category=ObjectCategory.UNKNOWN,
                bbox=bbox,
                confidence=0.5,
                suggested_params={}
            )
            for bbox in bboxes
        ]
    
    # Use provided classifier
    detections = classifier_fn(image)
    
    detected_objects = []
    for name, bbox, confidence in detections:
        category = classify_object_by_name(name)
        detected_objects.append(
            DetectedObject(
                category=category,
                bbox=bbox,
                confidence=confidence,
                suggested_params={}  # Will be filled later with scale info
            )
        )
    
    return detected_objects


def visualize_detections(
    image: np.ndarray,
    detections: List[DetectedObject],
    output_path: Optional[str] = None
) -> np.ndarray:
    """
    Draw bounding boxes and labels on image.
    
    Args:
        image: Input image
        detections: List of detected objects
        output_path: If provided, save annotated image
    
    Returns:
        Annotated image
    """
    annotated = image.copy()
    
    for det in detections:
        x, y, w, h = det.bbox
        
        # Draw bounding box
        color = (0, 255, 0) if det.category != ObjectCategory.UNKNOWN else (0, 0, 255)
        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
        
        # Add label
        label = f"{det.category.value} ({det.confidence:.2f})"
        cv2.putText(
            annotated,
            label,
            (x, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2
        )
    
    if output_path:
        cv2.imwrite(output_path, annotated)
    
    return annotated
