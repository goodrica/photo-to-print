# Photo-to-Print 📸 → 🖨️

**Turn photos into 3D printable parts — $2 filament instead of $20 plastic.**

The marketplace is full of art prints. This is for the homeowner who needs a garage hook, a replacement bracket, or a holder for that thing. Take a photo on college-ruled paper, upload it, get STL files.

## How It Works

```
Photo on paper → Scale calibration → Object detection → Parametric template → STL files
```

1. **Scale Calibration**: College-ruled paper has lines 7.1mm apart. We detect these lines to compute pixels-per-mm.
2. **Object Detection**: Identify what the object is (hook, bracket, holder, clip, knob, basket, spacer).
3. **Dimension Extraction**: Convert bounding box pixels to real-world mm using the scale.
4. **Parametric Generation**: Map to a CadQuery template and generate manifold STL files.
5. **ZIP Download**: Get all STLs + assembly instructions in one download.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the web app
python -m src.web.app

# Open http://localhost:8000
```

## Project Structure

```
photo-to-print/
├── src/
│   ├── cadgen/
│   │   └── templates.py      # Parametric CAD templates (CadQuery)
│   ├── detector/
│   │   ├── object_detector.py # Object detection + classification
│   │   └── vision_llm.py     # Vision LLM integration (HuggingFace)
│   ├── dimension/
│   │   └── calibration.py    # Scale calibration from paper lines
│   ├── pipeline/
│   │   └── main_pipeline.py  # Full pipeline orchestration
│   └── web/
│       └── app.py            # FastAPI web app
├── static/
│   └── index.html            # Frontend
├── tests/
│   ├── test_cadgen.py
│   └── test_calibration.py
└── requirements.txt
```

## Parametric Templates

| Template | Parameters | Use Case |
|----------|-----------|----------|
| `hook` | height, width, depth, thickness, mount_hole_dia | Garage hooks, S-hooks |
| `bracket` | length, width, height, thickness, hole_pattern | L-brackets, shelf brackets |
| `holder` | inner_dia, height, wall_thickness, base_dia | Cup holders, tool holders |
| `clip` | width, depth, gap, thickness, flex_length | Cable clips, panel clips |
| `knob` | diameter, height, shaft_dia, shaft_depth | Replacement knobs |
| `basket` | length, width, height, wall_thickness, hole_pattern | Small bins, organizers |
| `spacer` | outer_dia, inner_dia, thickness | Washers, spacers |

## Tips for Best Results

- Use **college-ruled paper** (standard notebook paper with blue lines)
- Take photo from **directly above** (not at an angle)
- Ensure good **lighting** and **contrast**
- Works best for: hooks, brackets, holders, clips, knobs, baskets, spacers

## Architecture Decisions

**Why parametric templates instead of full 3D reconstruction?**
- Full reconstruction (NeRF, photogrammetry) produces non-manifold meshes unsuitable for printing
- Parametric templates guarantee watertight, printable geometry
- Functional objects have standard shapes — a hook IS a hook
- Much faster and more reliable

**Why college-ruled paper for scale?**
- Everyone has it
- Known, consistent spacing (7.1mm)
- Provides reference without special equipment
- Works with a single photo (no stereo vision needed)

## Roadmap

- [ ] Multi-part assembly splitting (for large objects)
- [ ] Vision LLM integration for smarter classification
- [ ] More parametric templates (gears, joints, enclosures)
- [ ] User correction interface (adjust dimensions before generating)
- [ ] Print orientation optimization
- [ ] Cost estimation (filament usage + time)

## License

MIT
