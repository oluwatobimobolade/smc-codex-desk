"""Visual proof checks for TradingView screenshots.

The visual layer is audit evidence only, but it must still prove that a chart
loaded. A file on disk is not the same thing as a visible market chart.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageStat


def evaluate_tradingview_screenshot(
    *,
    screenshot_path: str | Path,
    symbol: str,
    timeframe: str,
    package_root: str | Path | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    path = _resolve_path(screenshot_path, package_root=package_root)
    report: dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "screenshot_path": str(screenshot_path),
        "image_exists": path.exists(),
        "image_opened": False,
        "width": None,
        "height": None,
        "visual_variance": 0.0,
        "chart_area_variance": 0.0,
        "candles_visible": False,
        "blank_or_loading": True,
        "loading_spinner_absent": False,
        "symbol_verified": _symbol_verified(symbol, screenshot_path, metadata),
        "timeframe_verified": _timeframe_verified(timeframe, screenshot_path, metadata),
        "price_axis_visible": False,
        "visual_status": "VISUAL_CONTEXT_UNVERIFIED",
        "review_required": True,
        "reason": "Screenshot file missing",
    }
    if not path.exists():
        return report
    try:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            report["image_opened"] = True
            report["width"] = width
            report["height"] = height
            if width < 300 or height < 180:
                report["reason"] = "Screenshot dimensions are too small for chart proof"
                return report
            gray = rgb.convert("L")
            full_var = float(sum(ImageStat.Stat(gray).var) / max(1, len(ImageStat.Stat(gray).var)))
            # Ignore the outer browser chrome as much as possible and inspect the
            # central chart panel where candles should live.
            crop = gray.crop((int(width * 0.08), int(height * 0.12), int(width * 0.88), int(height * 0.88)))
            crop_stat = ImageStat.Stat(crop)
            chart_var = float(sum(crop_stat.var) / max(1, len(crop_stat.var)))
            report["visual_variance"] = round(full_var, 4)
            report["chart_area_variance"] = round(chart_var, 4)
            report["blank_or_loading"] = chart_var < 8.0 or full_var < 6.0
            report["loading_spinner_absent"] = not report["blank_or_loading"]
            report["candles_visible"] = chart_var >= 18.0 and full_var >= 10.0
            # Price axis is usually on the right; it should not be uniform if the
            # panel has loaded. This is intentionally heuristic and conservative.
            axis_crop = gray.crop((int(width * 0.86), int(height * 0.16), int(width * 0.98), int(height * 0.86)))
            axis_var = float(sum(ImageStat.Stat(axis_crop).var) / max(1, len(ImageStat.Stat(axis_crop).var)))
            report["price_axis_visible"] = axis_var >= 5.0
    except Exception as exc:
        report["reason"] = f"Image could not be opened: {type(exc).__name__}: {exc}"
        return report

    required_ok = all(
        bool(report[key])
        for key in (
            "image_exists",
            "image_opened",
            "candles_visible",
            "loading_spinner_absent",
            "symbol_verified",
            "timeframe_verified",
            "price_axis_visible",
        )
    )
    if required_ok:
        report["visual_status"] = "VISUAL_CONTEXT_VERIFIED"
        report["review_required"] = False
        report["reason"] = "Screenshot opened and chart candles/axis context are visible."
    else:
        missing = [
            key for key in (
                "candles_visible",
                "loading_spinner_absent",
                "symbol_verified",
                "timeframe_verified",
                "price_axis_visible",
            )
            if not report[key]
        ]
        report["reason"] = "Screenshot exists but chart context is unverified: " + ", ".join(missing)
    return report


def summarize_visual_proof(
    screenshot_reports: Mapping[str, Mapping[str, Any]],
    *,
    required_timeframes: set[str] | None = None,
) -> dict[str, Any]:
    required = required_timeframes or {"15m", "1h", "4h", "1d"}
    present = {str(report.get("timeframe")) for report in screenshot_reports.values()}
    missing = sorted(required - present)
    unverified = [
        label for label, report in screenshot_reports.items()
        if report.get("visual_status") != "VISUAL_CONTEXT_VERIFIED"
    ]
    if missing or unverified:
        status = "VISUAL_CONTEXT_UNVERIFIED"
        reason = "One or more required TradingView chart screenshots are missing or unverified."
    else:
        status = "VISUAL_AUDIT_AVAILABLE"
        reason = "Required TradingView screenshots are present and chart context is visually verified."
    return {
        "status": status,
        "reason": reason,
        "required_timeframes": sorted(required),
        "missing_timeframes": missing,
        "unverified_screenshots": unverified,
        "review_required": status != "VISUAL_AUDIT_AVAILABLE",
    }


def _resolve_path(value: str | Path, *, package_root: str | Path | None) -> Path:
    path = Path(str(value)).expanduser()
    if path.exists() or path.is_absolute() or package_root is None:
        return path
    return Path(package_root) / path


def _symbol_verified(symbol: str, path: str | Path, metadata: Mapping[str, Any]) -> bool:
    expected = symbol.upper().replace(".P", "")
    meta_symbol = str(metadata.get("symbol") or metadata.get("ticker") or "").upper().replace(".P", "")
    if meta_symbol:
        return expected in meta_symbol or meta_symbol in expected
    return expected in str(path).upper().replace(".P", "")


def _timeframe_verified(timeframe: str, path: str | Path, metadata: Mapping[str, Any]) -> bool:
    aliases = {
        "15": "15m",
        "15m": "15m",
        "1H": "1h",
        "1h": "1h",
        "60": "1h",
        "4H": "4h",
        "4h": "4h",
        "240": "4h",
        "1D": "1d",
        "1d": "1d",
        "D": "1d",
    }
    expected = aliases.get(str(timeframe), str(timeframe))
    meta_tf = aliases.get(str(metadata.get("timeframe") or metadata.get("interval") or ""), "")
    if meta_tf:
        return meta_tf == expected
    return expected.lower() in str(path).lower()
