#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path("/Users/tobimobolade/smc-codex-desk")
DOWNLOADS = Path("/Users/tobimobolade/Downloads")
OUTPUTS = ROOT / "outputs" / "eurnzd_markups"

IMAGES = {
    "1D": DOWNLOADS / "EURNZD_2026-03-10_17-04-58.png",
    "4H": DOWNLOADS / "EURNZD_2026-03-10_17-05-12.png",
    "1H": DOWNLOADS / "EURNZD_2026-03-10_17-05-44.png",
    "15M": DOWNLOADS / "EURNZD_2026-03-10_17-05-59.png",
}

CROPS = {
    "1D": (0, 54, 2060, 1185),
    "4H": (0, 54, 2060, 1185),
    "1H": (0, 54, 2060, 1185),
    "15M": (0, 54, 2060, 1185),
}

WHITE = (246, 246, 244, 255)
LIGHT = (231, 233, 238, 255)
MID = (157, 161, 171, 255)
DARK = (20, 22, 28, 255)
BLUE = (41, 126, 255, 255)
BLUE_FILL = (41, 126, 255, 42)
OB_FILL = (168, 184, 210, 95)
OB_EDGE = (132, 146, 168, 180)
TEAL_FILL = (78, 184, 179, 96)
TEAL_EDGE = (61, 161, 157, 180)
YELLOW = (50, 50, 50, 255)
GREEN = (54, 170, 92, 255)


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


TITLE_FONT = get_font(44, bold=True)
SUB_FONT = get_font(22, bold=False)
LABEL_FONT = get_font(20, bold=True)
SMALL_FONT = get_font(18, bold=False)


def stylize(src: Path, timeframe: str) -> Image.Image:
    image = Image.open(src).convert("RGBA")
    crop = CROPS[timeframe]
    image = image.crop(crop)

    arr = np.array(image)
    rgb = arr[:, :, :3].astype(np.int16)
    r = rgb[:, :, 0]
    g = rgb[:, :, 1]
    b = rgb[:, :, 2]
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    sat = maxc - minc

    out = arr.copy()

    mask_bull = (g > 90) & (b > 90) & (r < 130) & (g > r + 8)
    mask_bear = (r > 120) & (g < 120) & (b < 120)
    mask_dark = (maxc < 70) & (sat < 35)
    mask_gray = (sat < 40) & (maxc >= 70) & (maxc < 185)

    tone = np.clip(248 - (maxc * 0.25), 225, 248).astype(np.uint8)
    out[mask_dark, 0] = tone[mask_dark]
    out[mask_dark, 1] = tone[mask_dark]
    out[mask_dark, 2] = tone[mask_dark]

    out[mask_gray, 0] = 155
    out[mask_gray, 1] = 158
    out[mask_gray, 2] = 165

    out[mask_bull, 0] = 41
    out[mask_bull, 1] = 126
    out[mask_bull, 2] = 255

    out[mask_bear, 0] = 18
    out[mask_bear, 1] = 20
    out[mask_bear, 2] = 24

    return Image.fromarray(out, mode="RGBA")


def add_title(draw: ImageDraw.ImageDraw, timeframe: str, bias: str) -> None:
    draw.text((110, 68), '"Smart Money', font=TITLE_FONT, fill=BLUE)
    draw.text((620, 68), 'Concept"', font=TITLE_FONT, fill=DARK)
    draw.line((118, 142, 960, 142), fill=DARK, width=4)
    draw.line((118, 142, 590, 142), fill=BLUE, width=4)
    draw.text((110, 172), f"EURNZD {timeframe} | {bias}", font=SUB_FONT, fill=MID)


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill: tuple[int, int, int, int] = DARK) -> None:
    draw.text(xy, text, font=LABEL_FONT, fill=fill)


def thin_line(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], fill: tuple[int, int, int, int] = MID, width: int = 3) -> None:
    draw.line((*start, *end), fill=fill, width=width)


def dashed_line(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], fill: tuple[int, int, int, int] = MID, width: int = 3, dash: int = 16, gap: int = 8) -> None:
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1.0)
    ux = dx / length
    uy = dy / length
    pos = 0.0
    while pos < length:
        end_pos = min(pos + dash, length)
        sx = int(x1 + ux * pos)
        sy = int(y1 + uy * pos)
        ex = int(x1 + ux * end_pos)
        ey = int(y1 + uy * end_pos)
        draw.line((sx, sy, ex, ey), fill=fill, width=width)
        pos += dash + gap


def arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], fill: tuple[int, int, int, int] = DARK, width: int = 4) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=fill, width=width, joint="curve")
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    dx = x2 - x1
    dy = y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1.0)
    ux = dx / length
    uy = dy / length
    left = (x2 - int(16 * ux - 9 * uy), y2 - int(16 * uy + 9 * ux))
    right = (x2 - int(16 * ux + 9 * uy), y2 - int(16 * uy - 9 * ux))
    draw.polygon([points[-1], left, right], fill=fill)


def annotate_daily() -> Image.Image:
    image = stylize(IMAGES["1D"], "1D")
    draw = ImageDraw.Draw(image, "RGBA")
    add_title(draw, "1D", "Bearish HTF")

    draw.rectangle((1460, 440, 1840, 520), fill=OB_FILL, outline=OB_EDGE, width=2)
    label(draw, (1780, 445), "OB")

    draw.rectangle((1320, 500, 1835, 565), fill=BLUE_FILL)
    label(draw, (1334, 445), "FVG")
    thin_line(draw, (1260, 590), (1630, 590), DARK, 2)
    label(draw, (1265, 567), "BOS", DARK)

    dashed_line(draw, (1500, 620), (1750, 600), MID, 2)
    label(draw, (1450, 595), "SSL", MID)
    arrow(draw, [(1715, 515), (1800, 560), (1860, 660)], DARK, 4)

    return image


def annotate_4h() -> Image.Image:
    image = stylize(IMAGES["4H"], "4H")
    draw = ImageDraw.Draw(image, "RGBA")
    add_title(draw, "4H", "Bearish / lows in draw")

    draw.rectangle((1485, 640, 1850, 720), fill=OB_FILL, outline=OB_EDGE, width=2)
    label(draw, (1790, 646), "OB")

    draw.rectangle((1460, 720, 1880, 785), fill=BLUE_FILL)
    label(draw, (1600, 690), "FVG")

    thin_line(draw, (1425, 805), (1695, 805), DARK, 2)
    label(draw, (1440, 780), "BOS", DARK)

    dashed_line(draw, (1585, 895), (1855, 895), MID, 2)
    label(draw, (1812, 872), "SSL", MID)
    arrow(draw, [(1620, 765), (1710, 810), (1800, 888)], DARK, 4)

    return image


def annotate_1h() -> Image.Image:
    image = stylize(IMAGES["1H"], "1H")
    draw = ImageDraw.Draw(image, "RGBA")
    add_title(draw, "1H", "Bearish unless reclaim")

    thin_line(draw, (1525, 700), (1840, 700), GREEN, 3)
    label(draw, (1535, 670), "CHoCH", GREEN)

    draw.rectangle((1545, 735, 1868, 815), fill=OB_FILL, outline=OB_EDGE, width=2)
    label(draw, (1600, 742), "OB")

    thin_line(draw, (1515, 830), (1735, 830), DARK, 2)
    label(draw, (1525, 806), "BOS", DARK)

    dashed_line(draw, (1610, 940), (1880, 940), MID, 2)
    label(draw, (1810, 917), "SSL", MID)
    arrow(draw, [(1715, 780), (1790, 850), (1882, 980)], DARK, 4)

    return image


def annotate_15m() -> Image.Image:
    image = stylize(IMAGES["15M"], "15M")
    draw = ImageDraw.Draw(image, "RGBA")
    add_title(draw, "15M", "Execution chart")

    draw.rectangle((1490, 690, 1875, 770), fill=OB_FILL, outline=OB_EDGE, width=2)
    label(draw, (1785, 696), "OB")

    thin_line(draw, (1515, 815), (1735, 815), DARK, 2)
    label(draw, (1525, 790), "BOS", DARK)

    dashed_line(draw, (1738, 935), (1930, 935), MID, 2)
    label(draw, (1832, 910), "SSL", MID)

    draw.rectangle((1735, 770, 1885, 941), fill=TEAL_FILL, outline=TEAL_EDGE, width=2)
    draw.rectangle((1735, 690, 1885, 770), fill=OB_FILL, outline=OB_EDGE, width=2)
    arrow(draw, [(1678, 815), (1770, 855), (1840, 945)], DARK, 4)

    return image


def save_with_margin(image: Image.Image, output_path: Path) -> None:
    card = Image.new("RGBA", (image.width + 120, image.height + 120), WHITE)
    card.alpha_composite(image, (60, 60))
    card.save(output_path)


def build_board(paths: dict[str, Path], output_path: Path) -> None:
    images = [Image.open(paths[key]).convert("RGBA") for key in ["1D", "4H", "1H", "15M"]]
    width = max(image.width for image in images)
    height = max(image.height for image in images)
    margin = 48
    board = Image.new("RGBA", (width * 2 + margin * 3, height * 2 + margin * 3 + 80), WHITE)
    draw = ImageDraw.Draw(board, "RGBA")
    draw.text((margin, 22), "Tight SMC Markup Set", font=TITLE_FONT, fill=DARK)

    positions = {
        "1D": (margin, 88),
        "4H": (width + margin * 2, 88),
        "1H": (margin, height + margin + 88),
        "15M": (width + margin * 2, height + margin + 88),
    }
    for key, image in zip(["1D", "4H", "1H", "15M"], images):
        board.alpha_composite(image, positions[key])

    board.save(output_path)


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    rendered = {
        "1D": annotate_daily(),
        "4H": annotate_4h(),
        "1H": annotate_1h(),
        "15M": annotate_15m(),
    }
    paths = {
        "1D": OUTPUTS / "eurnzd_1d_annotated.png",
        "4H": OUTPUTS / "eurnzd_4h_annotated.png",
        "1H": OUTPUTS / "eurnzd_1h_annotated.png",
        "15M": OUTPUTS / "eurnzd_15m_annotated.png",
    }

    for key, image in rendered.items():
        save_with_margin(image, paths[key])
    build_board(paths, OUTPUTS / "eurnzd_markup_board.png")


if __name__ == "__main__":
    main()
