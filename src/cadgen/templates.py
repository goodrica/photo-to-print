"""
Parametric CAD templates for common functional objects.
Each template is a CadQuery script that generates an STL from parameters.
"""

import cadquery as cq
from typing import Dict, Any
from pathlib import Path


def generate_hook(
    height: float = 80.0,
    width: float = 30.0,
    depth: float = 20.0,
    thickness: float = 5.0,
    mount_hole_dia: float = 6.0,
    output_path: str = "hook.stl"
) -> Path:
    """
    Generate a simple S-hook or wall hook.
    
    Args:
        height: Total height in mm
        width: Hook opening width in mm
        depth: Hook depth (how far it sticks out) in mm
        thickness: Material thickness in mm
        mount_hole_dia: Diameter of mounting hole in mm
        output_path: Where to save the STL
    
    Returns:
        Path to generated STL file
    """
    # Create vertical mounting plate
    hook = (
        cq.Workplane("XY")
        .box(thickness, width, height)
    )
    
    # Add horizontal hook arm at bottom
    hook_arm = (
        cq.Workplane("XY")
        .center(thickness/2 + depth/2, -height/2 + thickness/2)
        .box(depth, width, thickness)
    )
    
    # Combine
    hook = hook.union(hook_arm)
    
    # Add mounting hole on the front face
    if mount_hole_dia > 0:
        hook = (
            hook.faces(">Z")
            .workplane()
            .center(0, height/2 - 15)  # 15mm from top
            .hole(mount_hole_dia, thickness)
        )
    
    # Export
    cq.exporters.export(hook, output_path)
    return Path(output_path)


def generate_bracket(
    length: float = 100.0,
    width: float = 50.0,
    height: float = 50.0,
    thickness: float = 5.0,
    hole_pattern: str = "single",
    output_path: str = "bracket.stl"
) -> Path:
    """
    Generate an L-bracket.
    
    Args:
        length: Horizontal arm length in mm
        width: Bracket width in mm
        height: Vertical arm height in mm
        thickness: Material thickness in mm
        hole_pattern: "single", "double", or "quad"
        output_path: Where to save the STL
    """
    # Vertical arm
    vertical = (
        cq.Workplane("XY")
        .box(thickness, width, height)
    )
    
    # Horizontal arm
    horizontal = (
        cq.Workplane("XY")
        .center(length/2 - thickness/2, -height/2 + thickness/2)
        .box(length, width, thickness)
    )
    
    # Combine
    bracket = vertical.union(horizontal)
    
    # Add holes based on pattern
    if hole_pattern != "none":
        # Vertical arm holes - drill through the thickness
        bracket = (
            bracket.faces(">X")
            .workplane()
            .center(0, height/2 - 15)
            .hole(5, thickness)
        )
        
        # Horizontal arm holes - drill through the thickness
        bracket = (
            bracket.faces(">Z")
            .workplane()
            .center(length/2 - thickness, 0)
            .hole(5, thickness)
        )
    
    cq.exporters.export(bracket, output_path)
    return Path(output_path)


def generate_holder(
    inner_dia: float = 40.0,
    height: float = 60.0,
    wall_thickness: float = 3.0,
    base_dia: float = 50.0,
    output_path: str = "holder.stl"
) -> Path:
    """
    Generate a cylindrical holder (cup, tool holder, etc).
    
    Args:
        inner_dia: Inner diameter in mm
        height: Holder height in mm
        wall_thickness: Wall thickness in mm
        base_dia: Base diameter in mm (for stability)
        output_path: Where to save the STL
    """
    outer_dia = inner_dia + 2 * wall_thickness
    
    # Outer cylinder
    outer = (
        cq.Workplane("XY")
        .circle(outer_dia / 2)
        .extrude(height)
    )
    
    # Inner cavity
    inner = (
        cq.Workplane("XY")
        .circle(inner_dia / 2)
        .extrude(height - wall_thickness)  # Leave solid base
    )
    
    # Cut cavity from outer
    holder = outer.cut(inner)
    
    # Add wider base for stability
    base = (
        cq.Workplane("XY")
        .circle(base_dia / 2)
        .extrude(wall_thickness)
    )
    
    holder = holder.union(base)
    
    cq.exporters.export(holder, output_path)
    return Path(output_path)


def generate_spacer(
    outer_dia: float = 20.0,
    inner_dia: float = 10.0,
    thickness: float = 5.0,
    output_path: str = "spacer.stl"
) -> Path:
    """
    Generate a simple washer/spacer.
    """
    spacer = (
        cq.Workplane("XY")
        .circle(outer_dia / 2)
        .circle(inner_dia / 2)
        .extrude(thickness)
    )
    
    cq.exporters.export(spacer, output_path)
    return Path(output_path)


# Template registry
TEMPLATES = {
    "hook": generate_hook,
    "bracket": generate_bracket,
    "holder": generate_holder,
    "spacer": generate_spacer,
}


def generate_from_template(
    template_name: str,
    params: Dict[str, Any],
    output_path: str
) -> Path:
    """
    Generate STL from template name and parameters.
    
    Args:
        template_name: One of "hook", "bracket", "holder", "spacer"
        params: Dictionary of template parameters
        output_path: Where to save the STL
    
    Returns:
        Path to generated STL
    """
    if template_name not in TEMPLATES:
        raise ValueError(f"Unknown template: {template_name}. Available: {list(TEMPLATES.keys())}")
    
    generator = TEMPLATES[template_name]
    return generator(**params, output_path=output_path)
