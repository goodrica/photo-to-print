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
class PipelineResult:
    """Result of the full pipeline."""
    success: bool
    parts: List[GeneratedPart]
    zip_path: Optional[Path]
    calibration: Optional[ScaleCalibration]
    error: Optional[str]


def run_pipeline(
    image_path: str,
    output_dir: str,
    expected_spacing_mm: float = 7.1,
    classifier_fn=None
) -> PipelineResult:
    """
    Run the full photo-to-print pipeline.
    
    Args:
        image_path: Path to input photo
        output_dir: Directory to save outputs
        expected_spacing_mm: Expected paper line spacing (7.1mm for college rule)
        classifier_fn: Optional ML classifier function
    
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
    
    # Step 2: Calibrate scale from paper lines
    calibration = calibrate_from_image(image_path, expected_spacing_mm)
    
    if calibration is None or calibration.confidence < 0.3:
        return PipelineResult(
            success=False,
            parts=[],
            zip_path=None,
            calibration=None,
            error="Failed to calibrate scale from paper. Ensure photo shows college-ruled paper."
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
