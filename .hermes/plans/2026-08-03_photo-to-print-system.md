# Photo-to-Print: Parametric 3D Printing from Photos

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a web app where homeowners upload photos of functional objects (hooks, brackets, holders, replacement parts) and get printable STL files back — $2 filament instead of $20 plastic.

**Architecture:** Photo → Scale Calibration (college-ruled paper) → Object Detection/Classification → Dimension Extraction → Parametric Template Selection → CadQuery STL Generation → .zip download with assembly instructions.

**Tech Stack:**
- Python 3.11 + FastAPI (backend)
- CadQuery (parametric CAD → STL)
- GroundingDINO / YOLO (object detection)
- OpenCV (scale calibration from paper grid)
- HuggingFace Inference API (vision LLM for interpretation)
- Vanilla HTML/JS frontend (static-first, per user preference)

---

## System Overview

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│  Photo       │───▶│  Scale Cal.  │───▶│  Object Detect  │
│  Upload      │    │  (paper grid)│    │  + Classify     │
└─────────────┘    └──────────────┘    └────────┬────────┘
                                                │
                    ┌──────────────┐    ┌────────▼────────┐
                    │  STL + ZIP   │◀───│  Parametric     │
                    │  Download    │    │  Template Gen   │
                    └──────────────┘    └─────────────────┘
```

## Key Insight: We're NOT doing 3D reconstruction

We're doing **functional parametric recreation**:
1. Detect object CATEGORY (hook, bracket, holder, basket, knob, clip)
2. Extract DIMENSIONS from photo (using paper grid as scale)
3. Map to PARAMETRIC TEMPLATE with those dimensions
4. Generate STL via CadQuery

This is 100x more tractable than full 3D reconstruction and produces BETTER results for functional prints (manifold, printable orientation, proper wall thickness).

## Scale Calibration (The Clever UX Hack)

College-ruled paper has lines spaced exactly **7.1mm (0.28")** apart. If user photographs object on paper:
1. Detect horizontal lines via Hough transform
2. Measure pixel distance between adjacent lines
3. Compute pixels-per-mm ratio
4. Use that to convert all object measurements to real mm

This gives us real-world dimensions from a single photo — no stereo vision needed.

## Parametric Template Library

Each template is a CadQuery script with named parameters:

| Template | Parameters | Use Case |
|----------|-----------|----------|
| `hook` | height, width, depth, thickness, mount_hole_dia | Garage hooks, S-hooks |
| `bracket` | length, width, height, thickness, hole_pattern | L-brackets, shelf brackets |
| `holder` | inner_dia, height, wall_thickness, base_dia | Cup holders, tool holders |
| `clip` | width, depth, gap, thickness, flex_length | Cable clips, panel clips |
| `knob` | diameter, height, shaft_dia, shaft_depth | Replacement knobs |
| `basket` | length, width, height, wall_thickness, hole_pattern | Small bins, organizers |
| `spacer` | outer_dia, inner_dia, thickness | Washers, spacers |
| `replacement_part` | user-defined (box with cutouts) | Generic box/housing |

## Tasks

### Task 1: Project scaffolding + CadQuery STL generation
### Task 2: Scale calibration from college-ruled paper
### Task 3: Object detection + classification pipeline
### Task 4: Parametric template library (hook, bracket, holder)
### Task 5: Dimension extraction from detected objects
### Task 6: Assembly splitting logic (multi-part prints)
### Task 7: FastAPI backend + ZIP generation
### Task 8: Static HTML frontend
### Task 9: Integration testing with real photos
