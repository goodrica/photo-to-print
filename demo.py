"""
Demo script showing the full photo-to-print pipeline.
Creates a synthetic test image and generates STL files.
"""

import cv2
import numpy as np
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dimension.calibration import detect_paper_lines, visualize_calibration
from src.detector.object_detector import detect_objects_opencv, visualize_detections, ObjectCategory, DetectedObject
from src.cadgen.templates import generate_from_template
from src.pipeline.main_pipeline import run_pipeline


def create_demo_image():
    """Create a synthetic demo image with college-ruled paper and an object."""
    # Create image with paper lines
    width, height = 800, 600
    image = np.ones((height, width, 3), dtype=np.uint8) * 255  # White paper
    
    # Draw college-ruled paper lines - LIGHT BLUE (like real notebook paper)
    # These should be visible but not too dark
    # Real college-ruled lines are light blue: BGR roughly (220, 180, 150)
    line_spacing = 71  # pixels (7.1mm at 10 px/mm)
    for y in range(50, height - 50, line_spacing):
        cv2.line(image, (0, y), (width, y), (220, 180, 150), 2)  # Light blue, 2px thick
    
    # Draw a clear hook shape (dark gray/black object on white paper)
    # This will be the only dark object, easily detected by threshold
    # Vertical part
    cv2.rectangle(image, (300, 160), (360, 440), (40, 40, 40), -1)
    # Horizontal part
    cv2.rectangle(image, (360, 410), (500, 440), (40, 40, 40), -1)
    # Return part (going up)
    cv2.rectangle(image, (470, 300), (500, 410), (40, 40, 40), -1)
    
    return image


def demo_calibration():
    """Demonstrate scale calibration."""
    print("\n" + "="*60)
    print("DEMO 1: Scale Calibration")
    print("="*60)
    
    image = create_demo_image()
    print(f"Created demo image: {image.shape}")
    
    calibration = detect_paper_lines(image)
    
    if calibration:
        print(f"\n✅ Calibration successful!")
        print(f"  Pixels per mm: {calibration.pixels_per_mm:.2f}")
        print(f"  Confidence: {calibration.confidence:.2%}")
        print(f"  Lines detected: {calibration.line_count}")
        print(f"  Avg line spacing: {calibration.avg_line_spacing_px:.1f} pixels")
        
        # Visualize
        output_dir = Path("demo_output")
        output_dir.mkdir(exist_ok=True)
        cv2.imwrite(str(output_dir / "calibration_demo.png"), image)
        print(f"\nSaved annotated image to: demo_output/calibration_demo.png")
    else:
        print("\n❌ Calibration failed")
    
    return calibration


def demo_object_detection():
    """Demonstrate object detection."""
    print("\n" + "="*60)
    print("DEMO 2: Object Detection")
    print("="*60)
    
    image = create_demo_image()
    
    # Detect objects with debug output
    bboxes = detect_objects_opencv(image, debug=True)
    
    print(f"\nDetected {len(bboxes)} object(s)")
    for i, bbox in enumerate(bboxes):
        x, y, w, h = bbox
        print(f"  Object {i+1}: bbox=({x}, {y}, {w}, {h})")
    
    # Visualize
    output_dir = Path("demo_output")
    output_dir.mkdir(exist_ok=True)
    
    # Create dummy detections for visualization
    detections = [
        DetectedObject(
            category=ObjectCategory.HOOK,
            bbox=bbox,
            confidence=0.85,
            suggested_params={}
        )
        for bbox in bboxes
    ]
    
    annotated = visualize_detections(image, detections, str(output_dir / "detection_demo.png"))
    print(f"\nSaved annotated image to: demo_output/detection_demo.png")


def demo_stl_generation():
    """Demonstrate STL generation from templates."""
    print("\n" + "="*60)
    print("DEMO 3: STL Generation")
    print("="*60)
    
    output_dir = Path("demo_output")
    output_dir.mkdir(exist_ok=True)
    
    # Generate a hook
    print("\nGenerating hook...")
    hook_path = generate_from_template(
        "hook",
        {"height": 80.0, "width": 30.0, "depth": 20.0, "thickness": 5.0, "mount_hole_dia": 6.0},
        str(output_dir / "demo_hook.stl")
    )
    print(f"  ✅ Generated: {hook_path.name} ({hook_path.stat().st_size} bytes)")
    
    # Generate a bracket
    print("\nGenerating bracket...")
    bracket_path = generate_from_template(
        "bracket",
        {"length": 100.0, "width": 50.0, "height": 50.0, "thickness": 5.0},
        str(output_dir / "demo_bracket.stl")
    )
    print(f"  ✅ Generated: {bracket_path.name} ({bracket_path.stat().st_size} bytes)")
    
    # Generate a holder
    print("\nGenerating holder...")
    holder_path = generate_from_template(
        "holder",
        {"inner_dia": 40.0, "height": 60.0, "wall_thickness": 3.0, "base_dia": 50.0},
        str(output_dir / "demo_holder.stl")
    )
    print(f"  ✅ Generated: {holder_path.name} ({holder_path.stat().st_size} bytes)")
    
    # Generate a spacer
    print("\nGenerating spacer...")
    spacer_path = generate_from_template(
        "spacer",
        {"outer_dia": 20.0, "inner_dia": 10.0, "thickness": 5.0},
        str(output_dir / "demo_spacer.stl")
    )
    print(f"  ✅ Generated: {spacer_path.name} ({spacer_path.stat().st_size} bytes)")
    
    print(f"\nAll STL files saved to: demo_output/")


def demo_full_pipeline():
    """Demonstrate the full pipeline."""
    print("\n" + "="*60)
    print("DEMO 4: Full Pipeline")
    print("="*60)
    
    # Create and save demo image
    image = create_demo_image()
    output_dir = Path("demo_output")
    output_dir.mkdir(exist_ok=True)
    image_path = output_dir / "demo_photo.png"
    cv2.imwrite(str(image_path), image)
    
    print(f"\nCreated demo photo: {image_path}")
    print("\nRunning full pipeline...")
    
    # Run pipeline
    result = run_pipeline(
        image_path=str(image_path),
        output_dir=str(output_dir / "pipeline_output")
    )
    
    if result.success:
        print(f"\n✅ Pipeline successful!")
        print(f"  Generated {len(result.parts)} part(s)")
        print(f"  ZIP file: {result.zip_path}")
        
        for i, part in enumerate(result.parts, 1):
            print(f"\n  Part {i}: {part.name}")
            print(f"    Category: {part.category}")
            print(f"    File: {part.stl_path.name}")
            print(f"    Print time: ~{part.print_time_estimate_min} min")
    else:
        print(f"\n❌ Pipeline failed: {result.error}")


def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("PHOTO-TO-PRINT DEMO")
    print("="*60)
    print("\nThis demo shows the complete pipeline:")
    print("  1. Scale calibration from college-ruled paper")
    print("  2. Object detection")
    print("  3. Parametric STL generation")
    print("  4. Full pipeline integration")
    
    # Run demos
    demo_calibration()
    demo_object_detection()
    demo_stl_generation()
    demo_full_pipeline()
    
    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)
    print("\nAll outputs saved to: demo_output/")
    print("\nNext steps:")
    print("  - Run the web app: python -m src.web.app")
    print("  - Open http://localhost:8000")
    print("  - Upload a real photo on college-ruled paper!")


if __name__ == "__main__":
    main()
