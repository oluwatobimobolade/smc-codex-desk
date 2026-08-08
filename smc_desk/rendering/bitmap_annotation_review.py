"""Deterministic bitmap QA for rendered SMC charts.

This does not claim human-like semantic vision. It proves that the renderer
produced a nonblank, legible-sized, visually populated chart and records that a
real AI/human semantic image review is still required when no vision provider
was used.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def review_rendered_annotation_bitmap(
    image_path: str | Path,
    *,
    scene: Mapping[str, Any],
    semantic_review_status: str = "NOT_PERFORMED_NO_VISION_PROVIDER",
) -> dict[str, Any]:
    path = Path(image_path)
    issues: list[dict[str, str]] = []
    if not path.exists():
        return _result(path, "REVIEW_REQUIRED", semantic_review_status, {}, [{"code": "bitmap_missing", "message": "Rendered chart file does not exist."}])

    with Image.open(path) as source:
        image = source.convert("RGB")
        pixels = np.asarray(image, dtype=np.uint8)
    height, width, _ = pixels.shape
    nonwhite = np.any(pixels < 245, axis=2)
    dark = np.all(pixels < 90, axis=2)
    saturation = pixels.max(axis=2).astype(np.int16) - pixels.min(axis=2).astype(np.int16)
    colored = saturation > 35
    nonwhite_ratio = float(nonwhite.mean())
    dark_ratio = float(dark.mean())
    colored_ratio = float(colored.mean())
    luminance_std = float(pixels.mean(axis=2).std())
    visible_objects = int(scene.get("visible_drawing_object_count") or 0)

    if width < 1000 or height < 500:
        issues.append({"code": "bitmap_resolution_too_small", "message": f"Chart resolution {width}x{height} is below the professional review floor."})
    if nonwhite_ratio < 0.01 or luminance_std < 5.0:
        issues.append({"code": "bitmap_effectively_blank", "message": "Rendered chart has insufficient visible candle/axis content."})
    if nonwhite_ratio > 0.72:
        issues.append({"code": "bitmap_visual_density_extreme", "message": "Rendered chart is excessively dense and likely cluttered."})
    if dark_ratio < 0.0005:
        issues.append({"code": "bitmap_missing_candle_structure", "message": "Too few dark wick/axis pixels were found to verify candle structure."})
    if visible_objects > 0 and colored_ratio < 0.0005:
        issues.append({"code": "bitmap_annotation_not_visible", "message": "The scene contains annotation objects but the bitmap has too little colored annotation evidence."})

    metrics = {
        "width": width,
        "height": height,
        "nonwhite_pixel_ratio": round(nonwhite_ratio, 6),
        "dark_pixel_ratio": round(dark_ratio, 6),
        "colored_pixel_ratio": round(colored_ratio, 6),
        "luminance_std": round(luminance_std, 4),
        "visible_drawing_object_count": visible_objects,
    }
    return _result(
        path,
        "PASS" if not issues else "REVIEW_REQUIRED",
        semantic_review_status,
        metrics,
        issues,
    )


def _result(
    path: Path,
    deterministic_status: str,
    semantic_status: str,
    metrics: Mapping[str, Any],
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema": "smc_annotation_bitmap_review_v1",
        "image_path": str(path),
        "deterministic_bitmap_status": deterministic_status,
        "semantic_image_review_status": semantic_status,
        "overall_status": (
            "REVIEW_REQUIRED"
            if deterministic_status != "PASS" or semantic_status in {"FAILED", "REVIEW_REQUIRED"}
            else "PASS_WITH_SEMANTIC_REVIEW_PENDING"
            if semantic_status == "NOT_PERFORMED_NO_VISION_PROVIDER"
            else "PASS"
        ),
        "metrics": dict(metrics),
        "issues": issues,
        "authority_contract": {
            "can_downgrade": True,
            "can_promote_trade_state": False,
            "semantic_correctness_proven_by_pixels": False,
        },
    }


__all__ = ["review_rendered_annotation_bitmap"]
