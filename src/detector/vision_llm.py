"""
Vision LLM integration for interpreting photos and suggesting parameters.

Uses HuggingFace Inference API or local models to:
1. Identify what the object IS (not just detect it)
2. Understand its FUNCTION (hook, holder, bracket, etc.)
3. Suggest parametric template and dimensions
4. Recommend assembly strategy (single print vs multi-part)
"""

import base64
import json
import requests
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VisionInterpretation:
    """Result of vision LLM analysis."""
    object_description: str
    suggested_category: str
    suggested_template: str
    estimated_dimensions_mm: Dict[str, float]
    assembly_strategy: str  # "single" or "multi_part"
    num_parts: int
    notes: str
    confidence: float


SYSTEM_PROMPT = """You are an expert 3D printing analyst. You analyze photos of functional household objects 
(hooks, brackets, holders, clips, knobs, baskets, spacers, replacement parts) and help recreate them as 
3D-printable parametric models.

Given a photo of an object on college-ruled paper (lines 7.1mm apart), analyze the object and provide:

1. What the object IS and what it's used for
2. Which parametric template best matches it
3. Estimated dimensions in millimeters
4. Whether it should be printed as one piece or split into multiple parts

Available templates:
- hook: Wall hooks, S-hooks, garage hooks (params: height, width, depth, thickness, mount_hole_dia)
- bracket: L-brackets, shelf brackets (params: length, width, height, thickness, hole_pattern)
- holder: Cylindrical holders, cups, tool holders (params: inner_dia, height, wall_thickness, base_dia)
- clip: Cable clips, panel clips (params: width, depth, gap, thickness, flex_length)
- knob: Replacement knobs, dials (params: diameter, height, shaft_dia, shaft_depth)
- basket: Small bins, organizers (params: length, width, height, wall_thickness, hole_pattern)
- spacer: Washers, spacers (params: outer_dia, inner_dia, thickness)

For assembly strategy:
- "single" if the object fits in one print (< 200mm in any dimension)
- "multi_part" if it needs to be split (large objects, complex geometry)
  - If multi_part, suggest how many parts and how they connect

Use the paper lines as scale reference. Each line gap = 7.1mm.

Respond ONLY with valid JSON in this format:
{
    "object_description": "Brief description of what the object is",
    "suggested_category": "hook|bracket|holder|clip|knob|basket|spacer",
    "suggested_template": "template_name",
    "estimated_dimensions_mm": {"param1": value1, "param2": value2, ...},
    "assembly_strategy": "single|multi_part",
    "num_parts": 1,
    "notes": "Any special considerations for printing",
    "confidence": 0.85
}"""


def encode_image_base64(image_path: str) -> str:
    """Encode image to base64 string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_with_vision_llm(
    image_path: str,
    api_key: Optional[str] = None,
    model: str = "mistralai/Pixtral-12B-2409"
) -> Optional[VisionInterpretation]:
    """
    Analyze image with vision LLM via HuggingFace Inference API.
    
    Args:
        image_path: Path to image file
        api_key: HuggingFace API key (or set HF_TOKEN env var)
        model: Vision model to use
    
    Returns:
        VisionInterpretation or None if failed
    """
    import os
    api_key = api_key or os.environ.get("HF_TOKEN")
    
    if not api_key:
        print("Warning: No HF_TOKEN set, using fallback analysis")
        return None
    
    image_b64 = encode_image_base64(image_path)
    
    # Determine MIME type
    suffix = Path(image_path).suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime_type = mime_map.get(suffix, "image/jpeg")
    
    # HuggingFace Inference API
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": [
            {
                "role": "system",
                "content": [{"type": "text", "text": SYSTEM_PROMPT}]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}
                    },
                    {
                        "type": "text",
                        "text": "Analyze this object on college-ruled paper. What is it, what are its dimensions, and how should I 3D print it?"
                    }
                ]
            }
        ],
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        
        # Parse the response
        if isinstance(result, list):
            text = result[0].get("generated_text", "")
        elif isinstance(result, dict):
            text = result.get("generated_text", str(result))
        else:
            text = str(result)
        
        # Extract JSON from response
        # Look for JSON block in the response
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = text[json_start:json_end]
            data = json.loads(json_str)
            
            return VisionInterpretation(
                object_description=data.get("object_description", "Unknown object"),
                suggested_category=data.get("suggested_category", "unknown"),
                suggested_template=data.get("suggested_template", "hook"),
                estimated_dimensions_mm=data.get("estimated_dimensions_mm", {}),
                assembly_strategy=data.get("assembly_strategy", "single"),
                num_parts=data.get("num_parts", 1),
                notes=data.get("notes", ""),
                confidence=data.get("confidence", 0.5)
            )
        
        return None
        
    except Exception as e:
        print(f"Vision LLM analysis failed: {e}")
        return None


def fallback_analysis(
    image_path: str,
    detected_category: str,
    dimensions_mm: Dict[str, float]
) -> VisionInterpretation:
    """
    Fallback analysis when vision LLM is unavailable.
    Uses detected category and computed dimensions.
    """
    return VisionInterpretation(
        object_description=f"Detected {detected_category} from photo",
        suggested_category=detected_category,
        suggested_template=detected_category,
        estimated_dimensions_mm=dimensions_mm,
        assembly_strategy="single",
        num_parts=1,
        notes="Analysis based on object detection only. Dimensions estimated from bounding box.",
        confidence=0.6
    )
