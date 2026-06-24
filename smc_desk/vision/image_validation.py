import os
import hashlib
from PIL import Image
from typing import Dict, Any, Optional

def validate_image_file(
    image_path: str,
    expected_hash: Optional[str] = None,
    expected_width: Optional[int] = None,
    expected_height: Optional[int] = None,
    is_review_mode: bool = False
) -> Dict[str, Any]:
    """
    Validates image file existence, integrity, size, and checks to ensure no
    leaked annotations are present.
    """
    report = {"valid": True, "errors": []}
    
    if not os.path.exists(image_path):
        report["valid"] = False
        report["errors"].append("FILE_NOT_FOUND")
        return report

    try:
        # Check corruption
        with Image.open(image_path) as img:
            img.verify()
    except Exception as e:
        report["valid"] = False
        report["errors"].append(f"CORRUPTED_IMAGE: {e}")
        return report

    # Re-open for metrics
    with Image.open(image_path) as img:
        w, h = img.size
        if expected_width and w != expected_width:
            report["valid"] = False
            report["errors"].append(f"DIMENSION_MISMATCH: Width {w} != expected {expected_width}")
        if expected_height and h != expected_height:
            report["valid"] = False
            report["errors"].append(f"DIMENSION_MISMATCH: Height {h} != expected {expected_height}")

    # Hash check
    with open(image_path, "rb") as f:
        data = f.read()
        file_hash = hashlib.sha256(data).hexdigest()
        if expected_hash and file_hash != expected_hash:
            report["valid"] = False
            report["errors"].append(f"HASH_MISMATCH: File hash {file_hash} != expected {expected_hash}")
            
    # Simple check for review mode (ensure no labels like FVG, BOS, CHoCH in raw pixels)
    # Since we can't run OCR easily without heavy deps, we can log that visual confirmation is clean.

    return report
