"""
Main pipeline: Photo → Detection → Dimensions → STL generation.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import tempfile
import zipfile

from src.dimension.calibration import calibrate_from_image, ScaleCalibration, pixels_to_mm
from src.dimension.ruler_calibration import calibrate_ruler_from_image


def calibrate_scale(
    image_path: str,
    method: str = "auto",
    expected_spacing_mm: float = 7.1,
    tick_pitch_mm: float = 1.0,
    min_confidence: float = 0.3,
):
    """
    Calibrate scale from an image using the chosen method.

    method:
      "auto"  -> try ruler first, fall back to paper lines (best confidence wins)
      "ruler" -> ruler ticks only
      "paper" -> college-ruled paper only

    Returns (ScaleCalibration | None, method_used: str).
    """
    method = (method or "auto").lower()

    def _paper():
        return calibrate_from_image(image_path, expected_spacing_mm)

    def _ruler():
        return calibrate_ruler_from_image(image_path, tick_pitch_mm)

    if method == "paper":
        return _paper(), "paper"
    if method == "ruler":
        return _ruler(), "ruler"

    # auto: prefer whichever gives higher confidence above the floor
    ruler = _ruler()
    paper = _paper()
    candidates = []
    if ruler is not None and ruler.confidence >= min_confidence:
        candidates.append((ruler.confidence, ruler, "ruler"))
    if paper is not None and paper.confidence >= min_confidence:
        candidates.append((paper.confidence, paper, "paper"))
    if not candidates:
        # return the best of whatever we got, even if below floor, for error context
        best = max(
            [c for c in (ruler, paper) if c is not None],
            key=lambda c: c.confidence,
            default=None,
        )
        used = "ruler" if best is ruler else ("paper" if best is paper else "none")
        return best, used
    candidates.sort(key=lambda t: t[0], reverse=True)
    _, cal, used = candidates[0]
    return cal, used
from src.detector.object_detector import (
    detect_objects_with_ml,
    suggest_default_params,
    ObjectCategory,
    DetectedObject,
)
from src.cadgen.templates import generate_from_template, TEMPLATES


@dataclass
class GeneratedPart:
    """A generated 3D printable part."""
    name: str
    stl_path: Path
    category: str
    params: Dict[str, float]
    print_time_estimate_min: int  # Rough estimate


@dataclass
class ViewInfo:
    """Calibration + detection info for one uploaded view."""
    role: str                     # front / side / top
    filename: str
    pixels_per_mm: float
    confidence: float
    category: str
    bbox_px: Tuple[int, int, int, int]


@dataclass
class PipelineResult:
    """Result of the full pipeline."""
    success: bool
    parts: List[GeneratedPart]
    zip_path: Optional[Path]
    calibration: Optional[ScaleCalibration]
    error: Optional[str]
    views: Optional[List[ViewInfo]] = None
    axis_consistency: Optional[Dict[str, Optional[float]]] = None


# Which object axes each view role can measure: (horizontal, vertical)
VIEW_AXES = {
    "front": ("width", "height"),
    "side": ("depth", "height"),
    "top": ("width", "depth"),
}

DEFAULT_ROLE_SEQUENCE = ["front", "side", "top"]


def calibrate_view(
    image_path: str,
    role: str,
    expected_spacing_mm: float = 7.1,
    classifier_fn=None,
    calibration_method: str = "auto",
    tick_pitch_mm: float = 1.0,
) -> Tuple[Optional[ScaleCalibration], List[DetectedObject], np.ndarray]:
    """
    Calibrate and detect the main object in a single view.

    Returns:
        (calibration, detections, image) - detections sorted largest-first,
        empty lists on failure.
    """
    image = cv2.imread(image_path)
    if image is None:
        return None, [], None

    calibration, _ = calibrate_scale(
        image_path,
        method=calibration_method,
        expected_spacing_mm=expected_spacing_mm,
        tick_pitch_mm=tick_pitch_mm,
    )
    if calibration is None or calibration.confidence < 0.3:
        return calibration, [], image

    detections = detect_objects_with_ml(image, classifier_fn)
    # Main object = largest bbox area first
    detections.sort(key=lambda d: d.bbox[2] * d.bbox[3], reverse=True)
    return calibration, detections, image


def merge_view_dimensions(
    view_data: List[Tuple[str, ScaleCalibration, DetectedObject]]
) -> Dict[str, float]:
    """
    Merge per-view bounding box measurements into object dimensions (mm).

    view_data: list of (role, calibration, detection) tuples.
    Each view contributes its horizontal and vertical axis measurement.
    Axes measured in multiple views are averaged and reported with
    agreement info in consistency_pct.
    """
    axis_measurements: Dict[str, List[float]] = {}
    for role, cal, det in view_data:
        _, _, w_px, h_px = det.bbox
        ppm = float(cal.pixels_per_mm)
        for axis, px in zip(VIEW_AXES.get(role, ("width", "height")), (w_px, h_px)):
            axis_measurements.setdefault(axis, []).append(float(px) / ppm)

    merged: Dict[str, float] = {}
    for axis, values in axis_measurements.items():
        merged[axis] = float(np.mean(values))
    return merged


def axis_consistency_pct(
    view_data: List[Tuple[str, ScaleCalibration, DetectedObject]]
) -> Dict[str, Optional[float]]:
    """
    For each axis measured by 2+ views, return 100 * min/max agreement.
    None if only one view measured it.
    """
    axis_measurements: Dict[str, List[float]] = {}
    for role, cal, det in view_data:
        _, _, w_px, h_px = det.bbox
        ppm = float(cal.pixels_per_mm)
        for axis, px in zip(VIEW_AXES.get(role, ("width", "height")), (w_px, h_px)):
            axis_measurements.setdefault(axis, []).append(float(px) / ppm)

    result: Dict[str, Optional[float]] = {}
    for axis, values in axis_measurements.items():
        if len(values) >= 2:
            result[axis] = round(100.0 * min(values) / max(values), 1)
        else:
            result[axis] = None
    return result


def run_pipeline(
    image_path: str,
    output_dir: str,
    expected_spacing_mm: float = 7.1,
    classifier_fn=None,
    calibration_method: str = "auto",
    tick_pitch_mm: float = 1.0,
) -> PipelineResult:
    """
    Run the full photo-to-print pipeline.
    
    Args:
        image_path: Path to input photo
        output_dir: Directory to save outputs
        expected_spacing_mm: Expected paper line spacing (7.1mm for college rule)
        classifier_fn: Optional ML classifier function
        calibration_method: "auto" (ruler then paper), "ruler", or "paper"
        tick_pitch_mm: Ruler finest-tick pitch in mm (default 1.0)
    
    Returns:
        PipelineResult with generated parts
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Load image
    image = cv2.imread(image_path)
    if image is None:
        return PipelineResult(
            success=False,
            parts=[],
            zip_path=None,
            calibration=None,
            error="Failed to load image"
        )
    
    # Step 2: Calibrate scale (ruler and/or paper lines)
    calibration, method_used = calibrate_scale(
        image_path,
        method=calibration_method,
        expected_spacing_mm=expected_spacing_mm,
        tick_pitch_mm=tick_pitch_mm,
    )
    
    if calibration is None or calibration.confidence < 0.3:
        return PipelineResult(
            success=False,
            parts=[],
            zip_path=None,
            calibration=None,
            error=(
                "Failed to calibrate scale. Include a metric ruler or college-ruled "
                "paper clearly visible in the photo."
            )
        )
    
    # Step 3: Detect objects
    detections = detect_objects_with_ml(image, classifier_fn)
    
    if not detections:
        return PipelineResult(
            success=False,
            parts=[],
            zip_path=None,
            calibration=calibration,
            error="No objects detected in image"
        )
    
    # Step 4: Generate STL for each detected object
    parts = []
    for i, det in enumerate(detections):
        # For unknown categories, try to infer from bounding box aspect ratio
        if det.category == ObjectCategory.UNKNOWN:
            _, _, w_px, h_px = det.bbox
            aspect_ratio = h_px / w_px if w_px > 0 else 1.0
            
            # Simple heuristic: tall narrow = hook, square = holder, wide = bracket
            if aspect_ratio > 1.5:
                det.category = ObjectCategory.HOOK
            elif aspect_ratio < 0.7:
                det.category = ObjectCategory.BRACKET
            else:
                det.category = ObjectCategory.HOLDER
        
        # Suggest parameters based on bounding box and scale
        params = suggest_default_params(det.category, det.bbox, calibration.pixels_per_mm)
        
        # Generate STL
        template_name = det.category.value
        stl_filename = f"part_{i+1}_{template_name}.stl"
        stl_path = output_path / stl_filename
        
        try:
            generate_from_template(template_name, params, str(stl_path))
            
            # Estimate print time (rough: 1 minute per cm^3)
            volume_mm3 = estimate_volume(params, template_name)
            print_time_min = int(volume_mm3 / 1000)  # Very rough estimate
            
            parts.append(GeneratedPart(
                name=f"Part {i+1}: {template_name.title()}",
                stl_path=stl_path,
                category=template_name,
                params=params,
                print_time_estimate_min=print_time_min
            ))
        except Exception as e:
            print(f"Failed to generate {template_name}: {e}")
            continue
    
    if not parts:
        return PipelineResult(
            success=False,
            parts=[],
            zip_path=None,
            calibration=calibration,
            error="Failed to generate any printable parts"
        )
    
    # Step 5: Create ZIP file
    zip_path = output_path / "printable_parts.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for part in parts:
            zipf.write(part.stl_path, part.stl_path.name)
        
        # Add README with assembly instructions
        readme_content = generate_readme(parts, calibration)
        zipf.writestr("README.txt", readme_content)
    
    return PipelineResult(
        success=True,
        parts=parts,
        zip_path=zip_path,
        calibration=calibration,
        error=None
    )


def estimate_volume(params: Dict[str, float], template_name: str) -> float:
    """
    Rough volume estimate in mm^3 for print time calculation.
    """
    if template_name == "hook":
        # Approximate as box
        return params.get("height", 80) * params.get("width", 30) * params.get("thickness", 5)
    
    elif template_name == "bracket":
        return params.get("length", 100) * params.get("width", 50) * params.get("thickness", 5)
    
    elif template_name == "holder":
        # Cylinder volume
        import math
        outer_r = (params.get("inner_dia", 40) + 2 * params.get("wall_thickness", 3)) / 2
        inner_r = params.get("inner_dia", 40) / 2
        height = params.get("height", 60)
        return math.pi * (outer_r**2 - inner_r**2) * height
    
    elif template_name == "spacer":
        import math
        outer_r = params.get("outer_dia", 20) / 2
        inner_r = params.get("inner_dia", 10) / 2
        thickness = params.get("thickness", 5)
        return math.pi * (outer_r**2 - inner_r**2) * thickness
    
    return 10000  # Default fallback


def generate_readme(parts: List[GeneratedPart], calibration: ScaleCalibration) -> str:
    """
    Generate README with assembly instructions and print settings.
    """
    lines = [
        "=" * 60,
        "PHOTO-TO-PRINT: Your Custom 3D Printable Parts",
        "=" * 60,
        "",
        f"Generated from photo with scale calibration:",
        f"  - Scale: {calibration.pixels_per_mm:.2f} pixels/mm",
        f"  - Confidence: {calibration.confidence:.2%}",
        "",
        "PARTS INCLUDED:",
        "-" * 60,
    ]
    
    for i, part in enumerate(parts, 1):
        lines.extend([
            f"\n{i}. {part.name}",
            f"   Category: {part.category}",
            f"   File: {part.stl_path.name}",
            f"   Estimated print time: {part.print_time_estimate_min} minutes",
            f"   Parameters (mm):",
        ])
        for key, value in part.params.items():
            lines.append(f"     - {key}: {value:.1f}")
    
    lines.extend([
        "",
        "=" * 60,
        "PRINTING RECOMMENDATIONS:",
        "-" * 60,
        "",
        "Material: PLA or PETG (PLA for indoor, PETG for outdoor/garage)",
        "Layer height: 0.2mm (standard) or 0.3mm (faster)",
        "Infill: 20-30% for functional parts",
        "Supports: Enable if needed (check slicer preview)",
        "Orientation: Print flat side down for best strength",
        "",
        "ASSEMBLY:",
        "-" * 60,
        "",
        "If multiple parts were generated, they may need to be:",
        "  - Glued together (super glue or epoxy)",
        "  - Screwed together (use appropriate hardware)",
        "  - Press-fit together (check dimensions)",
        "",
        "TIPS:",
        "-" * 60,
        "",
        "  - Test fit before final assembly",
        "  - Sand contact surfaces if needed",
        "  - For hooks/brackets: use wall anchors for drywall",
        "  - For holders: check that object fits before mounting",
        "",
        "=" * 60,
        "Generated by Photo-to-Print",
        "Turn your photos into functional 3D prints!",
        "=" * 60,
    ])
    
    return "\n".join(lines)


def run_pipeline_multi_view(
    view_inputs: List[Tuple[str, str]],
    output_dir: str,
    expected_spacing_mm: float = 7.1,
    classifier_fn=None,
    calibration_method: str = "auto",
    tick_pitch_mm: float = 1.0,
) -> PipelineResult:
    """
    Multi-view pipeline: 1-3 angled photos, each calibrated independently.

    Args:
        view_inputs: list of (role, image_path) tuples, role in front/side/top
        output_dir: Directory to save outputs
        expected_spacing_mm: Expected paper line spacing (7.1mm for college rule)
        classifier_fn: Optional ML classifier function

    Returns:
        PipelineResult. Parts share one merged set of dimensions.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not view_inputs:
        return PipelineResult(
            success=False, parts=[], zip_path=None, calibration=None,
            error="No images provided"
        )

    view_data: List[Tuple[str, ScaleCalibration, DetectedObject]] = []
    views: List[ViewInfo] = []
    best_cal: Optional[ScaleCalibration] = None

    for role, path in view_inputs:
        calibration, detections, _ = calibrate_view(
            path, role, expected_spacing_mm, classifier_fn
        )
        if calibration is None or not detections:
            continue
        if best_cal is None or calibration.confidence > best_cal.confidence:
            best_cal = calibration
        det = detections[0]  # main object = largest bbox
        view_data.append((role, calibration, det))
        views.append(ViewInfo(
            role=role,
            filename=Path(path).name,
            pixels_per_mm=float(calibration.pixels_per_mm),
            confidence=float(calibration.confidence),
            category=det.category.value,
            bbox_px=tuple(int(v) for v in det.bbox),
        ))

    if not view_data:
        return PipelineResult(
            success=False, parts=[], zip_path=None, calibration=best_cal,
            error=(
                "Failed to calibrate scale or detect objects in any view. "
                "Ensure each photo shows college-ruled paper."
            )
        )

    # Merge dimensions across views (cross-checks + fills missing axes)
    dims = merge_view_dimensions(view_data)
    consistency = axis_consistency_pct(view_data)

    # Category: majority vote across views, fallback first view
    from collections import Counter
    votes = Counter(det.category for _, _, det in view_data)
    category = votes.most_common(1)[0][0]
    if category == ObjectCategory.UNKNOWN:
        # infer from merged aspect ratio like single-view path
        w = dims.get("width", dims.get("depth", 40.0))
        h = dims.get("height", 40.0)
        ratio = h / w if w > 0 else 1.0
        if ratio > 1.5:
            category = ObjectCategory.HOOK
        elif ratio < 0.7:
            category = ObjectCategory.BRACKET
        else:
            category = ObjectCategory.HOLDER

    # Build params for chosen category from merged dims
    template_name = category.value
    params = params_from_merged_dims(template_name, dims)

    stl_filename = f"part_1_{template_name}.stl"
    stl_path = output_path / stl_filename

    try:
        generate_from_template(template_name, params, str(stl_path))
    except Exception as e:
        return PipelineResult(
            success=False, parts=[], zip_path=None, calibration=best_cal,
            views=views, axis_consistency=consistency,
            error=f"Failed to generate {template_name}: {e}"
        )

    volume_mm3 = estimate_volume(params, template_name)
    part = GeneratedPart(
        name=f"Part 1: {template_name.title()} (multi-view)",
        stl_path=stl_path,
        category=template_name,
        params=params,
        print_time_estimate_min=int(volume_mm3 / 1000),
    )

    # ZIP
    zip_path = output_path / "printable_parts.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(part.stl_path, part.stl_path.name)
        zipf.writestr("README.txt", generate_readme([part], best_cal))
        zipf.writestr("views.txt", format_views_report(views, dims, consistency))

    return PipelineResult(
        success=True,
        parts=[part],
        zip_path=zip_path,
        calibration=best_cal,
        error=None,
        views=views,
        axis_consistency=consistency,
    )


def params_from_merged_dims(
    template_name: str, dims: Dict[str, float]
) -> Dict[str, float]:
    """Map merged axis dimensions (mm) to template parameters."""
    width = dims.get("width", dims.get("depth", 40.0))
    depth = dims.get("depth", width)  # unknown depth: assume round/square
    height = dims.get("height", width)
    length = dims.get("width", dims.get("depth", 40.0))

    if template_name == "hook":
        return {
            "height": float(height),
            "width": float(width * 0.4),
            "depth": float(depth * 0.6),
            "thickness": 5.0,
            "mount_hole_dia": 6.0,
        }
    elif template_name == "bracket":
        return {
            "length": float(length),
            "width": float(depth),
            "height": float(height * 0.5),
            "thickness": 5.0,
            "hole_pattern": "single",
        }
    elif template_name == "holder":
        diameter = float(min(width, depth))
        return {
            "inner_dia": float(diameter * 0.8),
            "height": float(height),
            "wall_thickness": 3.0,
            "base_dia": diameter,
        }
    elif template_name == "spacer":
        diameter = float(min(width, depth))
        return {
            "outer_dia": float(diameter),
            "inner_dia": float(diameter * 0.5),
            "thickness": float(height),
        }
    else:
        return {
            "length": float(length),
            "width": float(depth),
            "height": float(height),
        }


def format_views_report(
    views: List[ViewInfo],
    dims: Dict[str, float],
    consistency: Dict[str, Optional[float]],
) -> str:
    """Human-readable per-view report included in the output ZIP."""
    lines = [
        "=" * 60,
        "MULTI-VIEW MEASUREMENT REPORT",
        "=" * 60,
        "",
    ]
    for v in views:
        lines.append(
            f"{v.role.upper():5s} | {v.filename} | "
            f"{v.pixels_per_mm:.2f} px/mm (conf {v.confidence:.0%}) | "
            f"category: {v.category} | bbox {v.bbox_px[2]}x{v.bbox_px[3]} px"
        )
    lines += ["", "Merged dimensions (mm):"]
    for axis in ("width", "height", "depth"):
        if axis in dims:
            cons = consistency.get(axis)
            cons_str = f" (agreement {cons}%)" if cons is not None else ""
            lines.append(f"  {axis:6s}: {dims[axis]:.1f}{cons_str}")
    lines += ["", "=" * 60]
    return "\n".join(lines)
