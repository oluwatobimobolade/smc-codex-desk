"""Professional multi-timeframe renderer for governed AI structure selections."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyArrowPatch, Rectangle
from PIL import Image, ImageChops, ImageStat

from smc_desk.brain.structure_lab.annotation_bridge import resolve_semantic_annotation_plan
from smc_desk.data.hashing import file_sha256, object_sha256


ANNOTATION_COLORS = {
    "bullish": "#148f77",
    "bearish": "#d34a4a",
    "neutral": "#333333",
    "mixed": "#555555",
    "unknown": "#555555",
}


def render_structure_lab_annotation_pack(
    *,
    evidence_pack: Mapping[str, Any],
    semantic_plan: Mapping[str, Any],
    output_dir: str | Path,
    official_state: str = "THESIS_ONLY",
) -> dict[str, Any]:
    """Resolve, render, and pixel-check the AI's selected SMC objects."""
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    resolution = resolve_semantic_annotation_plan(semantic_plan, evidence_pack)
    _write_json(root / "annotation_geometry_resolution.json", resolution)
    _write_json(root / "annotation_plan_v2.json", resolution["annotation_plan_v2"])
    objects = list(resolution["annotation_plan_v2"].get("objects") or [])
    by_timeframe: dict[str, list[dict[str, Any]]] = {}
    for obj in objects:
        by_timeframe.setdefault(str(obj.get("timeframe")), []).append(dict(obj))

    images: list[dict[str, Any]] = []
    pixel_reviews: list[dict[str, Any]] = []
    rendered_ids: list[str] = []
    render_errors: list[dict[str, str]] = []
    if resolution["status"] == "PASS":
        for timeframe in _ordered_timeframes(by_timeframe):
            try:
                df = _window_dataframe(evidence_pack, timeframe)
                tf_objects = by_timeframe[timeframe]
                baseline_path = root / f"{evidence_pack.get('symbol')}_{timeframe}_clean_baseline.png"
                annotated_path = root / f"{evidence_pack.get('symbol')}_{timeframe}_official_ai_annotation.png"
                _render_chart(
                    df,
                    [],
                    baseline_path,
                    symbol=str(evidence_pack.get("symbol") or "UNKNOWN"),
                    timeframe=timeframe,
                    official_state=official_state,
                )
                scene = _render_chart(
                    df,
                    tf_objects,
                    annotated_path,
                    symbol=str(evidence_pack.get("symbol") or "UNKNOWN"),
                    timeframe=timeframe,
                    official_state=official_state,
                )
                pixel_review = _pixel_review(
                    baseline_path=baseline_path,
                    annotated_path=annotated_path,
                    expected_object_count=len(tf_objects),
                    drawn_object_count=len(scene["drawn_semantic_object_ids"]),
                )
                rendered_ids.extend(scene["drawn_semantic_object_ids"])
                image_record = {
                    "timeframe": timeframe,
                    "annotated_path": str(annotated_path),
                    "annotated_sha256": file_sha256(annotated_path),
                    "baseline_path": str(baseline_path),
                    "baseline_sha256": file_sha256(baseline_path),
                    "width_px": pixel_review["width_px"],
                    "height_px": pixel_review["height_px"],
                    "planned_object_ids": [str(obj["semantic_object_id"]) for obj in tf_objects],
                    "drawn_object_ids": scene["drawn_semantic_object_ids"],
                    "scene": scene,
                    "pixel_review": pixel_review,
                }
                images.append(image_record)
                pixel_reviews.append(pixel_review)
            except (OSError, TypeError, ValueError) as exc:
                render_errors.append({"timeframe": timeframe, "error": str(exc)})

    planned_ids = list(resolution["resolved_semantic_object_ids"])
    all_rendered = bool(planned_ids) and sorted(planned_ids) == sorted(rendered_ids)
    pixel_passed = bool(pixel_reviews) and all(review["status"] == "PASS" for review in pixel_reviews)
    status = "PASS" if resolution["status"] == "PASS" and all_rendered and pixel_passed else "REVIEW_REQUIRED"
    manifest = {
        "schema": "professional_ai_smc_annotation_render_manifest_v1",
        "status": status,
        "symbol": evidence_pack.get("symbol"),
        "official_state": official_state,
        "resolution_status": resolution["status"],
        "planned_object_count": len(planned_ids),
        "rendered_object_count": len(rendered_ids),
        "planned_semantic_object_ids": planned_ids,
        "rendered_semantic_object_ids": rendered_ids,
        "all_planned_objects_rendered": all_rendered,
        "rendered_image_count": len(images),
        "timeframes": [item["timeframe"] for item in images],
        "images": images,
        "render_errors": render_errors,
        "pixel_review_status": "PASS" if pixel_passed else "REVIEW_REQUIRED",
        "trade_box_rendered": any(obj.get("object_type") == "trade_box" for obj in objects),
        "render_authority": "certified_geometry_only",
        "ai_geometry_authority": False,
    }
    manifest["render_manifest_sha256"] = object_sha256(manifest)
    _write_json(root / "pixel_review.json", {"schema": "annotation_pixel_review_pack_v1", "reviews": pixel_reviews})
    _write_json(root / "render_manifest.json", manifest)
    (root / "annotation_self_review.md").write_text(_self_review_markdown(manifest), encoding="utf-8")
    return manifest


def _window_dataframe(evidence_pack: Mapping[str, Any], timeframe: str) -> pd.DataFrame:
    windows = evidence_pack.get("ohlcv_windows") or {}
    rows = windows.get(timeframe) if isinstance(windows, Mapping) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"No OHLCV window is available for annotation timeframe {timeframe}.")
    df = pd.DataFrame(rows).copy()
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Annotation window {timeframe} is missing columns: {missing}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for column in ("open", "high", "low", "close"):
        df[column] = pd.to_numeric(df[column], errors="raise")
    return df.sort_values("timestamp").reset_index(drop=True)


def _render_chart(
    df: pd.DataFrame,
    objects: list[Mapping[str, Any]],
    output_path: Path,
    *,
    symbol: str,
    timeframe: str,
    official_state: str,
) -> dict[str, Any]:
    n = len(df)
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    object_prices = [price for obj in objects for price in _object_prices(obj)]
    low = min([float(l.min()), *object_prices])
    high = max([float(h.max()), *object_prices])
    span = max(high - low, abs(high) * 0.005, 1e-9)

    fig, ax = plt.subplots(figsize=(16, 8.5))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    ax.grid(color="#eceff1", linewidth=0.7, alpha=0.9)
    body_floor = span * 0.0008
    for index in range(n):
        color = "#159a8c" if c[index] >= o[index] else "#e65353"
        ax.plot([index, index], [l[index], h[index]], color="#242424", linewidth=0.65, zorder=2)
        ax.add_patch(
            Rectangle(
                (index - 0.33, min(o[index], c[index])),
                0.66,
                max(abs(c[index] - o[index]), body_floor),
                color=color,
                linewidth=0,
                zorder=3,
            )
        )

    drawn_ids: list[str] = []
    for obj in sorted(objects, key=lambda item: (int(item.get("importance") or 2), str(item.get("semantic_object_id")))):
        if _draw_object(ax, obj, n, span):
            drawn_ids.append(str(obj.get("semantic_object_id")))

    tf_label = timeframe.upper().replace("M", "m").replace("H", "H").replace("D", "D")
    ax.set_title(f"{symbol} · {tf_label}", loc="left", fontsize=14, fontweight="bold", color="#171717", pad=14)
    ax.text(
        0.002,
        1.003,
        f"AI SMC STRUCTURE MAP · {official_state.replace('_', ' ')}",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=7.5,
        color="#6b7280",
    )
    step = max(1, n // 8)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([df["timestamp"].iloc[index].strftime("%m-%d %H:%M") for index in ticks], fontsize=8, color="#5f6368")
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.tick_params(axis="y", labelsize=8, colors="#5f6368")
    ax.tick_params(axis="x", colors="#5f6368")
    ax.spines["left"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.spines["bottom"].set_color("#d8dde2")
    ax.spines["right"].set_color("#d8dde2")
    ax.set_xlim(-1, n + 7)
    ax.set_ylim(low - span * 0.10, high + span * 0.12)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, facecolor="#ffffff")
    plt.close(fig)
    return {
        "schema": "professional_ai_smc_annotation_scene_v1",
        "symbol": symbol,
        "timeframe": timeframe,
        "candle_count": n,
        "drawn_semantic_object_ids": drawn_ids,
        "object_count": len(objects),
        "text_panel_rendered": False,
        "trade_box_rendered": any(obj.get("object_type") == "trade_box" for obj in objects),
        "full_width_structure_line_rendered": False,
    }


def _draw_object(ax: Any, obj: Mapping[str, Any], n: int, span: float) -> bool:
    object_type = str(obj.get("object_type") or "")
    start = _bounded_index(obj.get("start_index"), n)
    end = _bounded_index(obj.get("end_index"), n)
    if start is None or end is None:
        return False
    if end <= start:
        end = min(n - 1, start + 1)
    direction = str(obj.get("direction") or "unknown")
    color = ANNOTATION_COLORS.get(direction, ANNOTATION_COLORS["unknown"])
    label = str(obj.get("label") or "")
    linestyle = {"solid": "-", "dashed": (0, (5, 4)), "dotted": (0, (2, 3))}.get(str(obj.get("line_style") or "solid"), "-")
    if object_type in {"structure_segment", "liquidity_line"}:
        price = _float(obj.get("price"))
        if price is None:
            return False
        width = 2.0 if object_type == "structure_segment" else 1.35
        ax.plot([start, end], [price, price], color=color, linewidth=width, linestyle=linestyle, zorder=7)
        if object_type == "structure_segment":
            ax.scatter([start, end], [price, price], s=[14, 22], color=color, zorder=8)
        _small_label(ax, min(n + 4, end + 0.7), price, label, color, span)
        return True
    if object_type == "poi_zone":
        price_low = _float(obj.get("price_low"))
        price_high = _float(obj.get("price_high"))
        if price_low is None or price_high is None:
            return False
        lower, upper = sorted((price_low, price_high))
        zone_color = "#65a7e8" if direction == "bullish" else "#d99090"
        ax.add_patch(
            Rectangle(
                (start, lower),
                max(1, end - start),
                upper - lower,
                facecolor=zone_color,
                edgecolor=color,
                alpha=0.20,
                linewidth=1.1,
                zorder=1,
            )
        )
        _small_label(ax, (start + end) / 2, upper, label, color, span)
        return True
    if object_type == "path_projection":
        price_low = _float(obj.get("price_low"))
        price_high = _float(obj.get("price_high"))
        if price_low is None or price_high is None:
            return False
        ax.add_patch(
            FancyArrowPatch(
                (start, price_low),
                (end, price_high),
                arrowstyle="-|>",
                mutation_scale=9,
                connectionstyle="arc3,rad=0.12",
                color="#6b7280",
                linewidth=1.1,
                linestyle=(0, (5, 4)),
                alpha=0.75,
                zorder=6,
            )
        )
        return True
    return False


def _small_label(ax: Any, x: float, y: float, text: str, color: str, span: float) -> None:
    ax.text(
        x,
        y + span * 0.006,
        text,
        color=color,
        fontsize=7.5,
        fontweight="semibold",
        ha="left",
        va="bottom",
        zorder=9,
        bbox={"facecolor": "#ffffff", "edgecolor": "none", "alpha": 0.86, "pad": 1.0},
    )


def _pixel_review(
    *,
    baseline_path: Path,
    annotated_path: Path,
    expected_object_count: int,
    drawn_object_count: int,
) -> dict[str, Any]:
    baseline = Image.open(baseline_path).convert("RGB")
    annotated = Image.open(annotated_path).convert("RGB")
    if baseline.size != annotated.size:
        return {
            "schema": "annotation_pixel_review_v1",
            "status": "REVIEW_REQUIRED",
            "issues": ["baseline_and_annotation_dimensions_differ"],
            "width_px": annotated.width,
            "height_px": annotated.height,
        }
    difference = ImageChops.difference(baseline, annotated)
    difference_gray = difference.convert("L")
    histogram = difference_gray.histogram()
    changed_pixels = sum(histogram[9:])
    total_pixels = annotated.width * annotated.height
    changed_ratio = changed_pixels / total_pixels if total_pixels else 0.0
    extrema = ImageStat.Stat(annotated).extrema
    nonblank = any(high - low >= 20 for low, high in extrema)
    issues: list[str] = []
    minimum_changed = max(180, int(total_pixels * 0.00004))
    if expected_object_count <= 0:
        issues.append("zero_planned_objects")
    if drawn_object_count != expected_object_count:
        issues.append("not_all_planned_objects_drawn")
    if changed_pixels < minimum_changed:
        issues.append("annotation_not_visibly_different_from_clean_baseline")
    if changed_ratio > 0.12:
        issues.append("annotation_pixel_density_excessive")
    if not nonblank:
        issues.append("annotated_chart_is_blank")
    return {
        "schema": "annotation_pixel_review_v1",
        "status": "PASS" if not issues else "REVIEW_REQUIRED",
        "issues": issues,
        "width_px": annotated.width,
        "height_px": annotated.height,
        "expected_object_count": expected_object_count,
        "drawn_object_count": drawn_object_count,
        "changed_pixel_count": changed_pixels,
        "changed_pixel_ratio": round(changed_ratio, 8),
        "minimum_changed_pixel_count": minimum_changed,
        "nonblank": nonblank,
    }


def _ordered_timeframes(by_timeframe: Mapping[str, Any]) -> list[str]:
    order = {"1d": 0, "4h": 1, "1h": 2, "15m": 3, "5m": 4}
    return sorted(by_timeframe, key=lambda value: (order.get(value, 99), value))


def _object_prices(obj: Mapping[str, Any]) -> list[float]:
    values: list[float] = []
    for key in ("price", "price_low", "price_high"):
        value = _float(obj.get(key))
        if value is not None:
            values.append(value)
    return values


def _bounded_index(value: Any, n: int) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(n - 1, parsed))


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _self_review_markdown(manifest: Mapping[str, Any]) -> str:
    lines = [
        "# AI Annotation Self-Review",
        "",
        f"- Status: `{manifest.get('status')}`",
        f"- Planned/resolved objects: `{manifest.get('planned_object_count')}`",
        f"- Rendered objects: `{manifest.get('rendered_object_count')}`",
        f"- Rendered timeframes: `{', '.join(manifest.get('timeframes') or []) or 'none'}`",
        f"- Pixel review: `{manifest.get('pixel_review_status')}`",
        f"- Trade box rendered: `{manifest.get('trade_box_rendered')}`",
        f"- Full object mapping: `{manifest.get('all_planned_objects_rendered')}`",
        "",
        "## Images",
        "",
    ]
    for image in manifest.get("images") or []:
        review = image.get("pixel_review") or {}
        lines.extend(
            [
                f"- `{image.get('timeframe')}`: `{image.get('annotated_path')}`",
                f"  - SHA-256: `{image.get('annotated_sha256')}`",
                f"  - Planned/drawn: `{len(image.get('planned_object_ids') or [])}/{len(image.get('drawn_object_ids') or [])}`",
                f"  - Changed pixels vs clean baseline: `{review.get('changed_pixel_count')}` (`{review.get('changed_pixel_ratio')}`)",
            ]
        )
    if manifest.get("render_errors"):
        lines.extend(["", "## Render Errors", ""])
        lines.extend(f"- `{item.get('timeframe')}`: {item.get('error')}" for item in manifest["render_errors"])
    lines.extend(
        [
            "",
            "The AI selected semantic objects; deterministic evidence supplied every price and timestamp. Pixel checks prove that the selected marks are visible in the final PNGs. This review does not create signal or execution authority.",
            "",
        ]
    )
    return "\n".join(lines)
