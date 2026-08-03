"""Test CAD template generation."""

import pytest
from pathlib import Path
from src.cadgen.templates import (
    generate_hook,
    generate_bracket,
    generate_holder,
    generate_spacer,
    generate_from_template,
)


def test_generate_hook(tmp_path):
    """Test hook generation produces valid STL."""
    output = tmp_path / "test_hook.stl"
    result = generate_hook(
        height=80.0,
        width=30.0,
        depth=20.0,
        thickness=5.0,
        mount_hole_dia=6.0,
        output_path=str(output)
    )
    
    assert result.exists()
    assert result.stat().st_size > 0
    # STL files should be at least a few KB
    assert result.stat().st_size > 1000


def test_generate_bracket(tmp_path):
    """Test bracket generation."""
    output = tmp_path / "test_bracket.stl"
    result = generate_bracket(
        length=100.0,
        width=50.0,
        height=50.0,
        thickness=5.0,
        hole_pattern="single",
        output_path=str(output)
    )
    
    assert result.exists()
    assert result.stat().st_size > 1000


def test_generate_holder(tmp_path):
    """Test holder generation."""
    output = tmp_path / "test_holder.stl"
    result = generate_holder(
        inner_dia=40.0,
        height=60.0,
        wall_thickness=3.0,
        base_dia=50.0,
        output_path=str(output)
    )
    
    assert result.exists()
    assert result.stat().st_size > 1000


def test_generate_spacer(tmp_path):
    """Test spacer generation."""
    output = tmp_path / "test_spacer.stl"
    result = generate_spacer(
        outer_dia=20.0,
        inner_dia=10.0,
        thickness=5.0,
        output_path=str(output)
    )
    
    assert result.exists()
    assert result.stat().st_size > 1000


def test_generate_from_template(tmp_path):
    """Test template registry."""
    output = tmp_path / "test_template.stl"
    result = generate_from_template(
        "hook",
        {"height": 100.0, "width": 40.0, "depth": 25.0},
        str(output)
    )
    
    assert result.exists()


def test_invalid_template():
    """Test invalid template raises error."""
    with pytest.raises(ValueError, match="Unknown template"):
        generate_from_template("invalid_template", {}, "test.stl")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
