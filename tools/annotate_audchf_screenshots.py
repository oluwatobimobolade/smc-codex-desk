#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path("/Users/tobimobolade/smc-codex-desk")
DOWNLOADS = Path("/Users/tobimobolade/Downloads")
OUTPUTS = ROOT / "outputs" / "audchf_markups"
BASE_SIZE = (2244, 1634)

IMAGES = {
    "1D": DOWNLOADS / "AUDCHF_2026-03-11_17-31-25.png",
    "4H": DOWNLOADS / "AUDCHF_2026-03-11_17-31-35.png",
    "1H": DOWNLOADS / "AUDCHF_2026-03-11_17-31-43.png",
    "15M": DOWNLOADS / "AUDCHF_2026-03-11_17-31-54.png",
}

COLORS = {
    "white": (245, 247, 250, 255),
    "soft": (184, 191, 204, 255),
    "shadow": (8, 10, 16, 148),
    "panel": (15, 18, 25, 192),
    "panel_edge": (110, 118, 136, 150),
    "bull": (32, 168, 136, 255),
    "bull_fill": (32, 168, 136, 52),
    "bear": (208, 88, 92, 255),
    "bear_fill": (208, 88, 92, 40),
    "amber": (222, 178, 68, 255),
    "amber_fill": (222, 178, 68, 40),
    "violet": (138, 126, 252, 255),
    "violet_fill": (138, 126, 252, 48),
    "blue": (82, 190, 255, 255),
    "blue_fill": (82, 190, 255, 50),
    "green": (68, 210, 128, 255),
    "green_fill": (68, 210, 128, 44),
    "red": (236, 96, 100, 255),
    "red_fill": (236, 96, 100, 42),
}


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


FONT_BADGE = get_font(26, bold=True)
FONT_LABEL = get_font(22, bold=True)
FONT_SMALL = get_font(18, bold=False)


def scale(image: Image.Image, value: tuple[int, int] | tuple[int, int, int, int]) -> tuple[int, ...]:
    sx = image.width / BASE_SIZE[0]
    sy = image.height / BASE_SIZE[1]
    if len(value) == 2:
        x, y = value
        return (int(round(x * sx)), int(round(y * sy)))
    x1, y1, x2, y2 = value
    return (
        int(round(x1 * sx)),
        int(round(y1 * sy)),
        int(round(x2 * sx)),
        int(round(y2 * sy)),
    )


def scale_points(image: Image.Image, points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [scale(image, point) for point in points]


def rgba(name: str, alpha: int | None = None) -> tuple[int, int, int, int]:
    color = COLORS[name]
    if alpha is None:
        return color
    return (color[0], color[1], color[2], alpha)


def text_size(font: ImageFont.ImageFont, text: str) -> tuple[int, int]:
    box = font.getbbox(text)
    return box[2] - box[0], box[3] - box[1]


def draw_tag(draw: ImageDraw.ImageDraw, anchor: tuple[int, int], text: str, fg: tuple[int, int, int, int], bg: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    width, height = text_size(FONT_LABEL, text)
    x, y = anchor
    box = (x, y, x + width + 22, y + height + 16)
    shadow = (box[0] + 2, box[1] + 3, box[2] + 2, box[3] + 3)
    draw.rounded_rectangle(shadow, radius=12, fill=rgba("shadow", 90))
    draw.rounded_rectangle(box, radius=12, fill=bg, outline=rgba("panel_edge", 160), width=2)
    draw.text((x + 11, y + 6), text, font=FONT_LABEL, fill=fg)
    return box


def draw_badge(draw: ImageDraw.ImageDraw, image: Image.Image, anchor: tuple[int, int], text: str, accent: str) -> None:
    x, y = scale(image, anchor)
    width, height = text_size(FONT_BADGE, text)
    box = (x, y, x + width + 28, y + height + 18)
    draw.rounded_rectangle((box[0] + 2, box[1] + 3, box[2] + 2, box[3] + 3), radius=16, fill=rgba("shadow", 108))
    draw.rounded_rectangle(box, radius=16, fill=rgba("panel", 214), outline=rgba(accent, 220), width=2)
    draw.text((x + 14, y + 7), text, font=FONT_BADGE, fill=rgba("white"))


def draw_line_with_shadow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], color: tuple[int, int, int, int], width: int) -> None:
    shadow_points = [(x + 2, y + 2) for x, y in points]
    draw.line(shadow_points, fill=rgba("shadow", 96), width=width + 2, joint="curve")
    draw.line(points, fill=color, width=width, joint="curve")


def draw_dashed_line(draw: ImageDraw.ImageDraw, p1: tuple[int, int], p2: tuple[int, int], color: tuple[int, int, int, int], width: int, dash: int = 20, gap: int = 10) -> None:
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy) or 1.0
    ux = dx / length
    uy = dy / length
    start = 0.0
    while start < length:
        end = min(start + dash, length)
        sx = int(round(x1 + ux * start))
        sy = int(round(y1 + uy * start))
        ex = int(round(x1 + ux * end))
        ey = int(round(y1 + uy * end))
        draw.line((sx + 2, sy + 2, ex + 2, ey + 2), fill=rgba("shadow", 90), width=width + 1)
        draw.line((sx, sy, ex, ey), fill=color, width=width)
        start += dash + gap


def draw_arrow(draw: ImageDraw.ImageDraw, image: Image.Image, points: list[tuple[int, int]], color_name: str = "white", width: int = 5) -> None:
    scaled = scale_points(image, points)
    draw_line_with_shadow(draw, scaled, rgba(color_name), width)
    x1, y1 = scaled[-2]
    x2, y2 = scaled[-1]
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy) or 1.0
    ux = dx / length
    uy = dy / length
    wing = max(12, width * 3)
    left = (int(round(x2 - wing * ux + wing * 0.55 * uy)), int(round(y2 - wing * uy - wing * 0.55 * ux)))
    right = (int(round(x2 - wing * ux - wing * 0.55 * uy)), int(round(y2 - wing * uy + wing * 0.55 * ux)))
    draw.polygon([(x2, y2), left, right], fill=rgba(color_name))


def draw_zone(draw: ImageDraw.ImageDraw, image: Image.Image, box: tuple[int, int, int, int], label: str, outline_name: str, fill_name: str, label_anchor: tuple[int, int]) -> dict[str, object]:
    rect = scale(image, box)
    draw.rounded_rectangle(rect, radius=10, fill=rgba(fill_name), outline=rgba(outline_name, 220), width=3)
    label_box = scale(image, label_anchor)
    draw_tag(draw, label_box, label, rgba("white"), rgba("panel", 210))
    return {
        "type": "zone",
        "label": label,
        "box": list(box),
        "style": {"outline": outline_name, "fill": fill_name},
    }


def draw_level(draw: ImageDraw.ImageDraw, image: Image.Image, p1: tuple[int, int], p2: tuple[int, int], label: str, color_name: str, label_anchor: tuple[int, int], dashed: bool = False) -> dict[str, object]:
    a = scale(image, p1)
    b = scale(image, p2)
    if dashed:
        draw_dashed_line(draw, a, b, rgba(color_name), width=3)
    else:
        draw_line_with_shadow(draw, [a, b], rgba(color_name), width=4)
    draw_tag(draw, scale(image, label_anchor), label, rgba("white"), rgba("panel", 205))
    return {
        "type": "level",
        "label": label,
        "points": [list(p1), list(p2)],
        "style": {"color": color_name, "dashed": dashed},
    }


def build_configs() -> dict[str, dict[str, object]]:
    return {
        "1D": {
            "filename": IMAGES["1D"].name,
            "inferred_symbol": "AUDCHF",
            "inferred_timeframe": "1D",
            "bias": "bullish",
            "confidence": "medium",
            "range_high": {"price": 0.5596, "confidence": "medium"},
            "range_low": {"price": 0.5142, "confidence": "medium"},
            "liquidity_levels": [
                {"label": "BSL", "price": 0.5596, "confidence": "medium", "note": "Recent daily highs and round-number 0.5600 pool."}
            ],
            "structure_points": [
                {"label": "HTF higher low", "price": 0.5253, "confidence": "medium"},
                {"label": "Current expansion leg", "price": 0.5581, "confidence": "high"},
            ],
            "bos_points": [
                {"label": "Daily BOS", "price": 0.5502, "confidence": "medium"}
            ],
            "choch_points": [],
            "sweeps": [],
            "fvgs": [
                {"label": "Daily FVG", "price_low": 0.5507, "price_high": 0.5535, "confidence": "low"}
            ],
            "order_blocks": [
                {"label": "Bullish OB", "price_low": 0.5460, "price_high": 0.5492, "confidence": "medium"}
            ],
            "entry": {
                "type": "wait_for_retrace",
                "price_zone": [0.5507, 0.5492],
                "confidence": "medium",
                "note": "Daily chart is in premium and pushing into external buy-side liquidity, so no chase at current candle."
            },
            "stop_loss": {"price": 0.5455, "confidence": "medium"},
            "take_profits": [
                {"label": "TP1", "price": 0.5596, "confidence": "medium"},
                {"label": "TP2", "price": 0.5605, "confidence": "low"},
            ],
            "reasons": [
                "Visible higher highs and higher lows since the October base.",
                "Price has already displaced through the prior February swing high.",
                "The cleanest daily continuation case is a retrace into imbalance and the last bullish demand origin."
            ],
            "uncertainties": [
                "Daily FVG boundaries are approximate because only the screenshot is available.",
                "The visible chart suggests continuation, but the market is already near external liquidity."
            ],
            "drawings": [
                {"kind": "badge", "text": "Bullish HTF", "anchor": (74, 112), "accent": "bull"},
                {"kind": "level", "p1": (1955, 182), "p2": (2170, 182), "label": "BSL", "label_anchor": (1968, 138), "color": "amber", "dashed": True},
                {"kind": "level", "p1": (1842, 432), "p2": (2060, 432), "label": "BOS", "label_anchor": (1856, 388), "color": "bull", "dashed": False},
                {"kind": "zone", "box": (1860, 438, 2006, 576), "label": "Bullish OB", "outline": "blue", "fill": "blue_fill", "label_anchor": (1845, 592)},
                {"kind": "zone", "box": (1950, 332, 2088, 426), "label": "FVG", "outline": "violet", "fill": "violet_fill", "label_anchor": (1926, 284)},
                {"kind": "arrow", "points": [(1944, 522), (2040, 372), (2142, 188)], "color": "white"},
            ],
        },
        "4H": {
            "filename": IMAGES["4H"].name,
            "inferred_symbol": "AUDCHF",
            "inferred_timeframe": "4H",
            "bias": "bullish",
            "confidence": "medium",
            "range_high": {"price": 0.5596, "confidence": "medium"},
            "range_low": {"price": 0.5442, "confidence": "medium"},
            "liquidity_levels": [
                {"label": "BSL", "price": 0.5596, "confidence": "medium", "note": "Current external highs."}
            ],
            "structure_points": [
                {"label": "4H protected low", "price": 0.5445, "confidence": "medium"},
                {"label": "Higher high expansion", "price": 0.5581, "confidence": "high"},
            ],
            "bos_points": [
                {"label": "4H BOS", "price": 0.5542, "confidence": "high"}
            ],
            "choch_points": [],
            "sweeps": [],
            "fvgs": [
                {"label": "4H FVG", "price_low": 0.5501, "price_high": 0.5514, "confidence": "medium"}
            ],
            "order_blocks": [
                {"label": "Bullish OB", "price_low": 0.5464, "price_high": 0.5482, "confidence": "medium"}
            ],
            "entry": {
                "type": "buy_retrace",
                "price_zone": [0.5514, 0.5482],
                "confidence": "medium",
                "note": "Continuation bias stays valid while 4H pullbacks respect the last displacement leg."
            },
            "stop_loss": {"price": 0.5442, "confidence": "medium"},
            "take_profits": [
                {"label": "TP1", "price": 0.5596, "confidence": "medium"}
            ],
            "reasons": [
                "The rally has produced a clean continuation BOS through the prior March swing high.",
                "The nearest inefficiency sits under current price and offers the only sensible continuation refill area.",
            ],
            "uncertainties": [
                "A precise liquidity-sweep label is not clean enough on the screenshot, so it was omitted."
            ],
            "drawings": [
                {"kind": "badge", "text": "Bullish continuation", "anchor": (74, 112), "accent": "bull"},
                {"kind": "level", "p1": (1984, 188), "p2": (2172, 188), "label": "BSL", "label_anchor": (1994, 144), "color": "amber", "dashed": True},
                {"kind": "level", "p1": (1732, 402), "p2": (2050, 402), "label": "BOS", "label_anchor": (1746, 356), "color": "bull", "dashed": False},
                {"kind": "zone", "box": (1880, 660, 1996, 794), "label": "Bullish OB", "outline": "blue", "fill": "blue_fill", "label_anchor": (1836, 804)},
                {"kind": "zone", "box": (1964, 498, 2070, 590), "label": "FVG", "outline": "violet", "fill": "violet_fill", "label_anchor": (1938, 450)},
                {"kind": "arrow", "points": [(1934, 734), (2032, 540), (2140, 190)], "color": "white"},
            ],
        },
        "1H": {
            "filename": IMAGES["1H"].name,
            "inferred_symbol": "AUDCHF",
            "inferred_timeframe": "1H",
            "bias": "bullish",
            "confidence": "medium",
            "range_high": {"price": 0.5592, "confidence": "medium"},
            "range_low": {"price": 0.5444, "confidence": "high"},
            "liquidity_levels": [
                {"label": "BSL", "price": 0.5592, "confidence": "medium", "note": "Current 1H highs."}
            ],
            "structure_points": [
                {"label": "March 8 swing low", "price": 0.5444, "confidence": "high"},
                {"label": "Current protected pullback", "price": 0.5562, "confidence": "medium"},
            ],
            "bos_points": [
                {"label": "1H BOS", "price": 0.5552, "confidence": "high"}
            ],
            "choch_points": [
                {"label": "1H CHoCH", "price": 0.5518, "confidence": "medium"}
            ],
            "sweeps": [],
            "fvgs": [
                {"label": "1H FVG", "price_low": 0.5538, "price_high": 0.5551, "confidence": "medium"}
            ],
            "order_blocks": [
                {"label": "Bullish OB", "price_low": 0.5522, "price_high": 0.5537, "confidence": "medium"}
            ],
            "entry": {
                "type": "buy_retrace",
                "price_zone": [0.5551, 0.5537],
                "confidence": "medium",
                "note": "Only valid if the retrace stays above the recent 1H break."
            },
            "stop_loss": {"price": 0.5520, "confidence": "medium"},
            "take_profits": [
                {"label": "TP1", "price": 0.5592, "confidence": "medium"},
                {"label": "TP2", "price": 0.5600, "confidence": "low"},
            ],
            "reasons": [
                "The down move into March 8 is fully reversed and price has displaced through the last meaningful intraday high.",
                "The 1H pullback zone is cleaner than buying the top of the current candle."
            ],
            "uncertainties": [
                "The exact order-block candle on 1H is inferred from the visible last bearish cluster before the latest push."
            ],
            "drawings": [
                {"kind": "badge", "text": "Bullish intraday", "anchor": (74, 112), "accent": "bull"},
                {"kind": "level", "p1": (1650, 638), "p2": (1810, 638), "label": "CHoCH", "label_anchor": (1608, 590), "color": "soft", "dashed": False},
                {"kind": "level", "p1": (1890, 452), "p2": (2068, 452), "label": "BOS", "label_anchor": (1850, 366), "color": "bull", "dashed": False},
                {"kind": "zone", "box": (1880, 570, 1988, 694), "label": "Bullish OB", "outline": "blue", "fill": "blue_fill", "label_anchor": (1838, 704)},
                {"kind": "zone", "box": (1940, 468, 2058, 560), "label": "FVG", "outline": "violet", "fill": "violet_fill", "label_anchor": (1920, 422)},
                {"kind": "level", "p1": (2000, 186), "p2": (2174, 186), "label": "BSL", "label_anchor": (2010, 140), "color": "amber", "dashed": True},
                {"kind": "arrow", "points": [(1936, 622), (2038, 470), (2140, 188)], "color": "white"},
            ],
        },
        "15M": {
            "filename": IMAGES["15M"].name,
            "inferred_symbol": "AUDCHF",
            "inferred_timeframe": "15m",
            "bias": "bullish",
            "confidence": "medium",
            "range_high": {"price": 0.5592, "confidence": "high"},
            "range_low": {"price": 0.5573, "confidence": "medium"},
            "liquidity_levels": [
                {"label": "Local BSL", "price": 0.5592, "confidence": "high", "note": "Intraday buy-side target above the recent high."}
            ],
            "structure_points": [
                {"label": "M15 breakout base", "price": 0.5578, "confidence": "medium"},
                {"label": "Current retrace", "price": 0.5582, "confidence": "high"},
            ],
            "bos_points": [
                {"label": "M15 BOS", "price": 0.5579, "confidence": "high"}
            ],
            "choch_points": [],
            "sweeps": [],
            "fvgs": [
                {"label": "M15 FVG", "price_low": 0.5578, "price_high": 0.5580, "confidence": "medium"}
            ],
            "order_blocks": [
                {"label": "Bullish OB", "price_low": 0.5575, "price_high": 0.5578, "confidence": "medium"}
            ],
            "entry": {
                "type": "limit_buy_retrace",
                "price_zone": [0.5578, 0.5580],
                "confidence": "medium",
                "note": "Use the retrace into the fresh M15 imbalance rather than chasing the breakout candle."
            },
            "stop_loss": {"price": 0.5573, "confidence": "medium"},
            "take_profits": [
                {"label": "TP1", "price": 0.5590, "confidence": "high"},
                {"label": "TP2", "price": 0.5600, "confidence": "medium"},
            ],
            "reasons": [
                "The lower-timeframe structure keeps stair-stepping higher after the breakout.",
                "A pullback into the 15m OB and adjacent FVG is the cleanest visible execution idea on the screenshot."
            ],
            "uncertainties": [
                "If price trades straight through 0.5573, the screenshot-based continuation thesis is invalid."
            ],
            "drawings": [
                {"kind": "badge", "text": "Buy retrace", "anchor": (74, 112), "accent": "blue"},
                {"kind": "level", "p1": (1812, 302), "p2": (1970, 302), "label": "BOS", "label_anchor": (1830, 248), "color": "bull", "dashed": False},
                {"kind": "zone", "box": (1970, 310, 2110, 365), "label": "Bullish OB", "outline": "blue", "fill": "blue_fill", "label_anchor": (1888, 372)},
                {"kind": "zone", "box": (2000, 284, 2124, 332), "label": "FVG", "outline": "violet", "fill": "violet_fill", "label_anchor": (1940, 236)},
                {"kind": "level", "p1": (1958, 308), "p2": (2170, 308), "label": "Entry", "label_anchor": (1882, 292), "color": "blue", "dashed": False},
                {"kind": "level", "p1": (1958, 358), "p2": (2170, 358), "label": "SL", "label_anchor": (1898, 342), "color": "red", "dashed": False},
                {"kind": "level", "p1": (1990, 222), "p2": (2170, 222), "label": "TP1", "label_anchor": (1928, 206), "color": "green", "dashed": False},
                {"kind": "level", "p1": (2012, 154), "p2": (2170, 154), "label": "TP2", "label_anchor": (1944, 138), "color": "green", "dashed": True},
                {"kind": "arrow", "points": [(2010, 318), (2070, 262), (2140, 166)], "color": "white"},
            ],
        },
    }


def annotate_timeframe(timeframe: str, config: dict[str, object]) -> dict[str, object]:
    image = Image.open(IMAGES[timeframe]).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    metadata_drawings: list[dict[str, object]] = []

    for drawing in config["drawings"]:
        kind = drawing["kind"]
        if kind == "badge":
            draw_badge(draw, image, drawing["anchor"], drawing["text"], drawing["accent"])
            metadata_drawings.append(
                {
                    "type": "badge",
                    "label": drawing["text"],
                    "anchor": list(drawing["anchor"]),
                    "style": {"accent": drawing["accent"]},
                }
            )
        elif kind == "zone":
            metadata_drawings.append(
                draw_zone(
                    draw,
                    image,
                    drawing["box"],
                    drawing["label"],
                    drawing["outline"],
                    drawing["fill"],
                    drawing["label_anchor"],
                )
            )
        elif kind == "level":
            metadata_drawings.append(
                draw_level(
                    draw,
                    image,
                    drawing["p1"],
                    drawing["p2"],
                    drawing["label"],
                    drawing["color"],
                    drawing["label_anchor"],
                    drawing.get("dashed", False),
                )
            )
        elif kind == "arrow":
            draw_arrow(draw, image, drawing["points"], drawing.get("color", "white"))
            metadata_drawings.append(
                {
                    "type": "arrow",
                    "label": drawing.get("label", "path"),
                    "points": [list(point) for point in drawing["points"]],
                    "style": {"color": drawing.get("color", "white")},
                }
            )

    annotated = Image.alpha_composite(image, overlay)
    output_path = OUTPUTS / f"audchf_{timeframe.lower()}_annotated.png"
    annotated.save(output_path, format="PNG", compress_level=1)

    result = {
        "image_id": timeframe,
        "filename": config["filename"],
        "source_path": str(IMAGES[timeframe]),
        "annotated_path": str(output_path),
        "inferred_symbol": config["inferred_symbol"],
        "inferred_timeframe": config["inferred_timeframe"],
        "bias": config["bias"],
        "confidence": config["confidence"],
        "range_high": config["range_high"],
        "range_low": config["range_low"],
        "liquidity_levels": config["liquidity_levels"],
        "structure_points": config["structure_points"],
        "bos_points": config["bos_points"],
        "choch_points": config["choch_points"],
        "sweeps": config["sweeps"],
        "fvgs": config["fvgs"],
        "order_blocks": config["order_blocks"],
        "entry": config["entry"],
        "stop_loss": config["stop_loss"],
        "take_profits": config["take_profits"],
        "annotations_drawn": metadata_drawings,
        "reasons": config["reasons"],
        "uncertainties": config["uncertainties"],
    }
    return result


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    configs = build_configs()
    results = [annotate_timeframe(timeframe, configs[timeframe]) for timeframe in ["1D", "4H", "1H", "15M"]]

    payload = {
        "instrument": "AUDCHF",
        "generated_at": "2026-03-11",
        "analysis_scope": "Screenshot-only SMC markup on original TradingView images.",
        "images": results,
        "rendering_log": {
            "library": "Pillow",
            "preserved_original_resolution": True,
            "overlays": [
                "semi-transparent order-block rectangles",
                "semi-transparent FVG rectangles",
                "solid and dashed structure/liquidity lines",
                "rounded label tags and bias badges",
                "white directional path arrows",
            ],
            "transparency_choices": {
                "order_blocks": "blue fill at 50 alpha",
                "fvgs": "violet fill at 48 alpha",
                "labels": "dark panels at roughly 80 percent opacity",
            },
        },
    }
    json_path = OUTPUTS / "audchf_markup_analysis.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json_path)
    for image in results:
        print(image["annotated_path"])


if __name__ == "__main__":
    main()
