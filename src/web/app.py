"""
FastAPI backend for Photo-to-Print web app.
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import List
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import tempfile
import shutil
import uuid

from src.pipeline.main_pipeline import run_pipeline, run_pipeline_multi_view
from dataclasses import asdict


app = FastAPI(
    title="Photo-to-Print",
    description="Turn photos into 3D printable STL files",
    version="0.1.0"
)

# Create temp directory for uploads/outputs
UPLOAD_DIR = Path(tempfile.gettempdir()) / "photo-to-print"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files
STATIC_DIR = Path(__file__).parent.parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main web page."""
    html_path = Path(__file__).parent.parent.parent / "static" / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>Photo-to-Print</h1><p>Frontend not found. API is running.</p>")
    
    return HTMLResponse(html_path.read_text())


@app.post("/api/upload")
async def upload_and_process(
    file: UploadFile = File(...),
    paper_spacing: float = 7.1,  # mm, college-ruled paper default
    calibration_method: str = "auto",  # "auto" | "ruler" | "paper"
    tick_pitch_mm: float = 1.0,  # ruler finest-tick pitch in mm
):
    """
    Upload photo and generate 3D printable parts.
    
    Args:
        file: Uploaded image file
        paper_spacing: Expected paper line spacing in mm (default 7.1 for college rule)
        calibration_method: "auto" tries a ruler then paper lines; "ruler" or
            "paper" force one method
        tick_pitch_mm: Ruler finest-tick real spacing in mm (default 1.0)
    
    Returns:
        JSON with download URL and part info
    """
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Create unique job directory
    job_id = str(uuid.uuid4())[:8]
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Save uploaded file
    image_path = job_dir / f"upload_{file.filename}"
    with open(image_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Run pipeline
    result = run_pipeline(
        image_path=str(image_path),
        output_dir=str(job_dir),
        expected_spacing_mm=paper_spacing,
        calibration_method=calibration_method,
        tick_pitch_mm=tick_pitch_mm,
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    # Build response
    parts_info = []
    for part in result.parts:
        parts_info.append({
            "name": part.name,
            "category": part.category,
            "filename": part.stl_path.name,
            "print_time_min": part.print_time_estimate_min,
            "params": part.params,
        })
    
    return {
        "success": True,
        "job_id": job_id,
        "calibration": {
            "pixels_per_mm": result.calibration.pixels_per_mm,
            "confidence": result.calibration.confidence,
            "line_count": result.calibration.line_count,
        },
        "parts": parts_info,
        "download_url": f"/api/download/{job_id}",
        "num_parts": len(result.parts),
    }


MAX_VIEWS = 3
VALID_ROLES = ("front", "side", "top")


@app.post("/api/upload-multi")
async def upload_multi_view(
    files: List[UploadFile] = File(...),
    roles: str = Form(""),  # comma-separated: "front,side,top"
    paper_spacing: float = Form(7.1),
    calibration_method: str = Form("auto"),  # "auto" | "ruler" | "paper"
    tick_pitch_mm: float = Form(1.0),
):
    """
    Upload 1-3 photos of the same object from different angles.

    Each photo must show a scale reference (a metric ruler or college-ruled
    paper). Views are calibrated independently; dimensions are merged across
    views with a cross-check on axes seen by more than one view.

    Args:
        files: 1-3 image files
        roles: comma-separated view roles matching file order
               (front/side/top). Defaults to front,side,top in order.
        paper_spacing: Expected paper line spacing in mm
        calibration_method: "auto" tries a ruler then paper lines; "ruler" or
            "paper" force one method
        tick_pitch_mm: Ruler finest-tick real spacing in mm (default 1.0)

    Returns:
        JSON with download URL, per-view info, merged dims, and
        per-axis agreement percentages.
    """
    if not (1 <= len(files) <= MAX_VIEWS):
        raise HTTPException(
            status_code=400,
            detail=f"Upload 1 to {MAX_VIEWS} images"
        )

    role_list = [r.strip().lower() for r in roles.split(",") if r.strip()]
    if not role_list:
        role_list = list(VALID_ROLES)
    if len(role_list) != len(files) or any(r not in VALID_ROLES for r in role_list):
        raise HTTPException(
            status_code=400,
            detail=f"roles must be comma-separated values from {VALID_ROLES}, "
                   f"one per file (got {len(role_list)} for {len(files)} files)"
        )

    job_id = str(uuid.uuid4())[:8]
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    view_inputs = []
    for i, (f, role) in enumerate(zip(files, role_list)):
        if not f.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"File {i+1} must be an image")
        path = job_dir / f"upload_{i+1}_{role}_{f.filename}"
        with open(path, "wb") as out:
            out.write(await f.read())
        view_inputs.append((role, str(path)))

    result = run_pipeline_multi_view(
        view_inputs=view_inputs,
        output_dir=str(job_dir),
        expected_spacing_mm=paper_spacing,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    parts_info = [{
        "name": p.name,
        "category": p.category,
        "filename": p.stl_path.name,
        "print_time_min": p.print_time_estimate_min,
        "params": p.params,
    } for p in result.parts]

    return {
        "success": True,
        "job_id": job_id,
        "calibration": {
            "pixels_per_mm": float(result.calibration.pixels_per_mm),
            "confidence": float(result.calibration.confidence),
            "line_count": int(result.calibration.line_count),
        },
        "views": [asdict(v) for v in (result.views or [])],
        "axis_consistency": result.axis_consistency or {},
        "parts": parts_info,
        "download_url": f"/api/download/{job_id}",
        "num_parts": len(result.parts),
    }


@app.get("/api/download/{job_id}")
async def download_zip(job_id: str):
    """
    Download the generated ZIP file.
    """
    job_dir = UPLOAD_DIR / job_id
    zip_path = job_dir / "printable_parts.zip"
    
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="ZIP file not found")
    
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"printable_parts_{job_id}.zip"
    )


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/templates")
async def list_templates():
    """List available parametric templates."""
    from src.cadgen.templates import TEMPLATES
    
    return {
        "templates": list(TEMPLATES.keys()),
        "count": len(TEMPLATES),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
