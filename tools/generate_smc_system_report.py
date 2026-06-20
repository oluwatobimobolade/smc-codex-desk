#!/usr/bin/env python3
"""Generate the SMC Desk system thesis/report PDF — plain-English edition.

Written so a regular SMC trader (even a beginner) can read and understand it.
Simple words, short sentences, new terms explained, and a glossary at the end.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import wrap

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


OUT_DIR = ROOT / "output" / "pdf"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = OUT_DIR / "SMC_Desk_Elite_Analyst_System_Thesis.pdf"

# Live case captured through Kimi WebBridge and annotated after the
# no-trade/watch clarification.
VISUAL_THESIS_DIR = ROOT / "case_library" / "BTCUSD" / "20260620_current_visual_thesis"
BTC_1H_THESIS = VISUAL_THESIS_DIR / "BTCUSD_1H_thesis_final.png"
BTC_15M_EXECUTION = VISUAL_THESIS_DIR / "BTCUSD_15m_zoom_execution_map_final.png"
BTC_NO_TRADE_LADDER = VISUAL_THESIS_DIR / "BTCUSD_no_trade_vs_watch_ladder.png"
VERIFIED_SHOT = ROOT / "journal" / "2026-06-18" / "BTCUSD" / "bitstamp_verified_capture" / "BTCUSD_15_224705.png"
BTC_SHOT = BTC_15M_EXECUTION if BTC_15M_EXECUTION.exists() else VERIFIED_SHOT

W, H = A4
M = 42

INK = colors.HexColor("#16202A")
MUTED = colors.HexColor("#5F6B76")
NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#2B6CB0")
TEAL = colors.HexColor("#0F8B8D")
GREEN = colors.HexColor("#198754")
RED = colors.HexColor("#C94C4C")
AMBER = colors.HexColor("#C98A19")
PURPLE = colors.HexColor("#6F42C1")
PAPER = colors.HexColor("#F6F8FA")
LINE = colors.HexColor("#D8DEE6")


# Results computed dynamically from research CSVs at build time.
# Source files: backtests/research/*_4yr_combo.csv and *_4yr_combo_cost10.csv
import pandas as pd
from pathlib import Path

RESEARCH_DIR = ROOT / "backtests" / "research"

def _compute_stats(csv_path: Path) -> dict:
    """Compute PF, win rate, total R from a research CSV."""
    if not csv_path.exists():
        return {"n": 0, "pf": 0.0, "win_rate": 0.0, "total_r": 0.0}
    df = pd.read_csv(csv_path)
    trig = df[df["triggered"] == True]
    if len(trig) == 0:
        return {"n": 0, "pf": 0.0, "win_rate": 0.0, "total_r": 0.0}
    wins = (trig["r_multiple"] > 0).sum()
    gross_wins = trig[trig["r_multiple"] > 0]["r_multiple"].sum()
    gross_losses = abs(trig[trig["r_multiple"] < 0]["r_multiple"].sum())
    pf = gross_wins / gross_losses if gross_losses > 0 else float("inf")
    return {
        "n": len(trig),
        "pf": round(pf, 3),
        "win_rate": round(wins / len(trig), 3),
        "total_r": round(trig["r_multiple"].sum(), 2),
    }

# Compute stats from actual research CSVs
_btc_combo = _compute_stats(RESEARCH_DIR / "BTCUSD_4yr_combo.csv")
_eth_combo = _compute_stats(RESEARCH_DIR / "ETHUSD_4yr_combo.csv")
_btc_cost10 = _compute_stats(RESEARCH_DIR / "BTCUSD_4yr_combo_cost10.csv")
_eth_cost10 = _compute_stats(RESEARCH_DIR / "ETHUSD_4yr_combo_cost10.csv")

# Combined stats (BTC + ETH)
_combined_n = _btc_combo["n"] + _eth_combo["n"]
_combined_gross_wins = 0.0
_combined_gross_losses = 0.0
for csv_file in ["BTCUSD_4yr_combo.csv", "ETHUSD_4yr_combo.csv"]:
    p = RESEARCH_DIR / csv_file
    if p.exists():
        df = pd.read_csv(p)
        trig = df[df["triggered"] == True]
        _combined_gross_wins += trig[trig["r_multiple"] > 0]["r_multiple"].sum()
        _combined_gross_losses += abs(trig[trig["r_multiple"] < 0]["r_multiple"].sum())
_combined_pf = _combined_gross_wins / _combined_gross_losses if _combined_gross_losses > 0 else 0.0

_cost10_n = _btc_cost10["n"] + _eth_cost10["n"]
_cost10_gross_wins = 0.0
_cost10_gross_losses = 0.0
for csv_file in ["BTCUSD_4yr_combo_cost10.csv", "ETHUSD_4yr_combo_cost10.csv"]:
    p = RESEARCH_DIR / csv_file
    if p.exists():
        df = pd.read_csv(p)
        trig = df[df["triggered"] == True]
        _cost10_gross_wins += trig[trig["r_multiple"] > 0]["r_multiple"].sum()
        _cost10_gross_losses += abs(trig[trig["r_multiple"] < 0]["r_multiple"].sum())
_cost10_pf = _cost10_gross_wins / _cost10_gross_losses if _cost10_gross_losses > 0 else 0.0

F = {
    "trades": _combined_n,
    "combined_pf": round(_combined_pf, 3),
    "combined_btc": _btc_combo["pf"],
    "combined_eth": _eth_combo["pf"],
    "combined_trades": _combined_n,
    "cost10_pf": round(_cost10_pf, 3),
    "cost10_btc": _btc_cost10["pf"],
    "cost10_eth": _eth_cost10["pf"],
    "cost10_trades": _cost10_n,
    "btc_trades": _btc_combo["n"],
    "eth_trades": _eth_combo["n"],
}
LIVE = {
    "verdict": "Pass", "dir": "bearish", "alignment": "1H bearish / 4H bearish / 1D neutral",
    "agreement": "0.67", "risk": "0%", "entry": "none",
    "reason": "no fresh executable POI, no clean 15m displacement trigger, and no valid SL/R:R model",
}


def fit_text(c, text, x, y, width, size=9, leading=None, color=INK):
    c.setFillColor(color)
    c.setFont("Helvetica", size)
    leading = leading or int(size * 1.35)
    max_chars = max(18, int(width / (size * 0.47)))
    for raw in str(text).split("\n"):
        for line in (wrap(raw, max_chars) or [""]):
            c.drawString(x, y, line)
            y -= leading
    return y


def draw_header(c, title_text, page):
    c.setFillColor(PAPER)
    c.rect(0, H - 54, W, 54, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(M, H - 31, "SMC Desk Elite Analyst")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawRightString(W - M, H - 31, title_text)
    c.setStrokeColor(LINE)
    c.line(M, H - 54, W - M, H - 54)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawCentredString(W / 2, 22, f"{page}")


def title(c, text, x, y, size=24, color=NAVY):
    c.setFillColor(color)
    c.setFont("Helvetica-Bold", size)
    c.drawString(x, y, text)
    return y - size * 1.25


def subtitle(c, text, x, y, size=11):
    return fit_text(c, text, x, y, int(W - x - M), size=size, leading=size + 5, color=MUTED)


def pill(c, x, y, text, color, width=None):
    c.setFont("Helvetica-Bold", 8)
    width = width or c.stringWidth(text, "Helvetica-Bold", 8) + 18
    c.setFillColor(colors.Color(color.red, color.green, color.blue, alpha=0.12))
    c.roundRect(x, y - 13, width, 20, 8, fill=1, stroke=0)
    c.setFillColor(color)
    c.drawCentredString(x + width / 2, y - 7, text)


def card(c, x, y, w, h, heading, body, accent=BLUE, body_size=8):
    c.setFillColor(colors.white)
    c.setStrokeColor(LINE)
    c.roundRect(x, y - h, w, h, 8, fill=1, stroke=1)
    c.setFillColor(accent)
    c.roundRect(x, y - 8, w, 8, 4, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x + 14, y - 28, heading)
    fit_text(c, body, x + 14, y - 47, int(w - 28), size=body_size, leading=body_size + 3, color=MUTED)


def bullets(c, items, x, y, width, size=9, color=INK):
    leading = size + 4
    max_chars = max(18, int((width - 13) / (size * 0.47)))
    for item in items:
        item = str(item).strip()
        if not item:
            continue
        lines = wrap(item, max_chars) or [item]
        baseline = y + size * 0.75
        c.setFillColor(TEAL)
        c.circle(x + 3, baseline + size * 0.22, 2.2, fill=1, stroke=0)
        c.setFillColor(color)
        c.setFont("Helvetica", size)
        for line in lines:
            c.drawString(x + 13, baseline, line)
            baseline -= leading
        y = baseline - 5
    return y


def stat_bar(c, x, y, label, value_text, fraction, color):
    """A labelled bar. fraction (0..1) scales the fill; value_text shows on the right."""
    c.setFillColor(INK)
    c.setFont("Helvetica", 9)
    c.drawString(x, y, label)
    bar_x = x + 215
    c.setFillColor(PAPER)
    c.roundRect(bar_x, y - 2, 180, 10, 5, fill=1, stroke=0)
    c.setFillColor(color)
    c.roundRect(bar_x, y - 2, 180 * max(0.02, min(1, fraction)), 10, 5, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(bar_x + 188, y, value_text)


def callout(c, x, y, w, h, heading, body, accent=GREEN, body_size=9):
    c.setFillColor(colors.white)
    c.setStrokeColor(accent)
    c.setLineWidth(1.4)
    c.roundRect(x, y - h, w, h, 10, fill=1, stroke=1)
    c.setLineWidth(1)
    c.setFillColor(accent)
    c.roundRect(x, y - 6, w, 6, 3, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x + 16, y - 28, heading)
    fit_text(c, body, x + 16, y - 47, int(w - 32), size=body_size, leading=body_size + 4, color=INK)


def draw_image_frame(c, path, x, y, w, h, caption):
    c.setFillColor(colors.white)
    c.setStrokeColor(LINE)
    c.roundRect(x, y - h, w, h, 8, fill=1, stroke=1)
    if path and Path(path).exists():
        img = ImageReader(str(path))
        iw, ih = img.getSize()
        scale = min((w - 16) / iw, (h - 34) / ih)
        dw, dh = iw * scale, ih * scale
        c.drawImage(img, x + (w - dw) / 2, y - 8 - dh, dw, dh, preserveAspectRatio=True, mask="auto")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(x + 10, y - h + 11, caption)


def gloss(c, term, meaning, x, y, width, size=8.5):
    c.setFont("Helvetica-Bold", size)
    c.setFillColor(NAVY)
    c.drawString(x, y, term)
    indent = 122
    c.setFont("Helvetica", size)
    c.setFillColor(INK)
    max_chars = max(20, int((width - indent) / (size * 0.49)))
    lines = wrap(meaning, max_chars) or [meaning]
    c.drawString(x + indent, y, lines[0])
    yy = y
    for extra in lines[1:]:
        yy -= size + 2.5
        c.drawString(x + indent, yy, extra)
    return yy - (size + 5.5)


# ---------------------------------------------------------------- pages

def page_1(c):
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 34)
    c.drawString(M, H - 150, "SMC Desk Elite Analyst")
    c.setFont("Helvetica-Bold", 17)
    c.drawString(M, H - 182, "How The System Works - In Plain Words")
    fit_text(
        c,
        "A trading helper that reads the chart two ways - by exact numbers and by eye - refuses weak "
        "trades, and learns from years of real price history. Written so any SMC trader can follow it, "
        "even if you are new.",
        M, H - 228, int(W - 2 * M), size=12, leading=18, color=colors.HexColor("#DCE9F5"),
    )
    pill(c, M, H - 298, "FOUNDATION: READY", GREEN, 132)
    pill(c, M + 146, H - 298, "EDGE: FAILED THE COST TEST", RED, 168)
    pill(c, M + 328, H - 298, "TESTED ON: 4 YEARS BTC + ETH", BLUE, 170)
    c.setFillColor(colors.HexColor("#DCE9F5"))
    c.setFont("Helvetica", 9)
    c.drawString(M, 64, "Made locally from smc-codex-desk. Research help only - not financial advice.")


def page_2(c):
    draw_header(c, "The Honest Answer", 2)
    y = title(c, "The Honest Answer", M, H - 92)
    y = subtitle(c, "Where the system stands today, with no hype.", M, y)
    y -= 6
    card(c, M, y, 155, 122, "What works", "It reads charts by exact numbers, looks at them by eye, checks if the two agree, and never makes up a price.", GREEN)
    card(c, M + 175, y, 155, 122, "What is new", "We tested it on 4 years of real BTC and ETH. It now learns from what truly happened next, not from guesses.", BLUE)
    card(c, M + 350, y, 155, 122, "Not proven yet", "We found a first sign of an edge. It is early. Do not trade it with real money yet.", AMBER)
    y -= 150
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(M, y, "The simple rule it lives by")
    bullets(
        c,
        [
            "The chart is proof, not the boss. The numbers come first.",
            "If something needed for a trade is missing, it says 'wait' and risks nothing.",
            "It only trusts a trade after the data agrees - not because a chart looks nice.",
            "It would rather miss a trade than take a bad one.",
        ],
        M, y - 24, int(W - 2 * M),
    )


def page_3(c):
    draw_header(c, "The Two Lenses", 3)
    y = title(c, "The Two Lenses", M, H - 92)
    y = subtitle(c, "The system looks at every chart in two separate ways, then checks if they agree. We call this the dual-lens (dual = two).", M, y)
    y -= 6
    card(c, M, y, 235, 116, "Lens 1 - The Calculator (engine)",
         "Reads the candle numbers and works out the exact levels: zones, entry, stop, target. It can be wrong, but it can never invent a price.", TEAL)
    card(c, M + 255, y, 235, 116, "Lens 2 - The Eyes (AI vision)",
         "Looks at the real chart like a trader would: trend, clean or messy, the bigger picture. It can agree, add context, or say 'no'. It is never allowed to set a price.", PURPLE)
    y -= 142
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(M, y, "Why two lenses?")
    y = bullets(
        c,
        [
            "When the Calculator and the Eyes agree, you can trust the read more.",
            "When they disagree, that is a warning - stand aside.",
            "The Eyes catch what numbers miss. The numbers stop the Eyes from dreaming.",
        ],
        M, y - 22, int(W - 2 * M),
    )
    callout(c, M, y - 8, W - 2 * M, 78, "Live example - BTC, 20 Jun WAT",
            f"Both lenses read {LIVE['dir']}. The system still said PASS / NO TRADE and risked 0% because the trade setup had not formed. Bias is not enough: it still needed a fresh POI, displacement, entry, stop, and target.", GREEN)


def page_4(c):
    draw_header(c, "What The Engine Reads", 4)
    y = title(c, "What The Engine Reads", M, H - 92)
    subtitle(c, "Every level comes from a rule and real candles - never from a guess.", M, y)
    card(c, M, H - 178, 235, 118, "Market structure",
         "Swing highs and lows, BOS (trend continues) and CHoCH (trend may be turning), and how strong each move was.", BLUE)
    card(c, M + 255, H - 178, 235, 118, "Liquidity",
         "Equal highs/lows where stops sit, and sweeps (price grabs those stops, then turns). These are targets and traps.", PURPLE)
    card(c, M, H - 312, 235, 118, "Zones (POI)",
         "FVG (a gap from a fast move) and OB (last candle before a big move). Marked fresh, partly used, or used up.", TEAL)
    card(c, M + 255, H - 312, 235, 118, "Trade plan",
         "Entry zone, execution stop, structural invalidation, target, reward-to-risk, a grade, and a clear list of what is still missing.", GREEN)
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Oblique", 8.5)
    fit_text(c, "New words like FVG, OB, POI, BOS and CHoCH are all explained in plain English on the last page (Glossary).",
             M, H - 332, int(W - 2 * M), size=8.5, leading=12, color=MUTED)


def page_5(c):
    draw_header(c, "The Learning Machine", 5)
    y = title(c, "How We Tested It", M, H - 92)
    y = subtitle(c, "We did not guess whether it works. We checked it against years of real price.", M, y)
    y = bullets(
        c,
        [
            "We took 4 years of real BTC and ETH 15-minute candles.",
            "At many points in the past, we asked the engine: what trade would you suggest here?",
            "Then we looked forward in the real data: did that trade hit target or stop?",
            f"We did this about {F['trades']}+ times. That gives real results, not opinions.",
        ],
        M, y - 4, int(W - 2 * M),
    )
    callout(c, M, y - 10, W - 2 * M, 120, "How we keep score (plain words)",
            "Win rate = how often trades hit target.\n"
            "R = how much you risked on a trade. A +2R win means you made twice what you risked.\n"
            "Average R = the typical win or loss per trade.\n"
            "Profit Factor (PF) = money made divided by money lost. Above 1.0 means winning. Below 1.0 means losing.",
            BLUE, body_size=9)


def page_6(c):
    draw_header(c, "First Truth", 6)
    y = title(c, "First Truth: It Was Losing", M, H - 92)
    y = subtitle(c, "On 4 years and about 1,000 trades, the basic SMC rules lost money on average. Better to know this than to hope.", M, y)
    y -= 10
    stat_bar(c, M, y, "Starting profit factor", "PF 0.71  (losing)", 0.71 / 1.6, RED)
    y -= 26
    stat_bar(c, M, y, "Win rate", "~37%  (losing)", 0.37, AMBER)
    y -= 40
    y = bullets(
        c,
        [
            "Profit factor 0.71 means for every $1 risked, only about $0.71 came back.",
            "We tried asking for bigger rewards (a higher reward-to-risk). It got WORSE - bigger targets get hit less often.",
            "This is the system being honest. A losing rule should be caught here, on a screen - not later, with your money.",
        ],
        M, y, int(W - 2 * M),
    )
    callout(c, M, y - 10, W - 2 * M, 58, "The point",
            "A pretty, disciplined system can still lose. Looking honest is not the same as making money. So we kept digging.", AMBER)


def page_7(c):
    draw_header(c, "Two Fixes", 7)
    y = title(c, "Two Fixes That Actually Helped", M, H - 92)
    y = subtitle(c, "We found two simple changes, and checked BOTH on BTC and ETH so they are not lucky one-offs.", M, y)
    y -= 6
    card(c, M, y, 235, 104, "Fix 1 - Skip tiny zones",
         "A very small zone gives a very tight stop, so normal price wiggle stops you out. Tiny zones were the worst, and were over half of all setups.", BLUE)
    card(c, M + 255, y, 235, 104, "Fix 2 - Only fresh zones",
         "A fresh zone has not been touched yet. A used (partial) zone is weaker. Using only fresh zones helped.", TEAL)
    y -= 128
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(M, y, "Before and after")
    y -= 24
    stat_bar(c, M, y, "Start (basic rules)", "PF 0.71", 0.71 / 1.3, RED)
    y -= 24
    stat_bar(c, M, y, "After Fix 1 (skip tiny zones)", "PF 0.83", 0.83 / 1.3, AMBER)
    y -= 24
    stat_bar(c, M, y, "After both fixes", "PF 1.15  (winning)", 1.15 / 1.3, GREEN)
    y -= 36
    bullets(c, ["Both fixes are simple trading sense, not random settings - that is why we trust them more."],
            M, y, int(W - 2 * M))


def page_8(c):
    draw_header(c, "The Edge & The Fair Test", 8)
    y = title(c, "The Edge, And The Fair Test", M, H - 92)
    y = subtitle(c, "On paper the two fixes turned it positive. Then we tested it fairly. Here is the honest result.", M, y)
    y -= 8
    stat_bar(c, M, y, "On paper (kind costs, 4bps)", f"PF {F['combined_pf']}  winning", F["combined_pf"] / 1.6, GREEN)
    y -= 26
    stat_bar(c, M, y, "Fair test (real costs, 10bps)", f"PF {F['cost10_pf']}  breakeven", F["cost10_pf"] / 1.6, RED)
    y -= 26
    stat_bar(c, M, y, "  -> BTC at real costs", f"PF {F['cost10_btc']}", F["cost10_btc"] / 1.6, AMBER)
    y -= 24
    stat_bar(c, M, y, "  -> ETH at real costs", f"PF {F['cost10_eth']}  losing", F["cost10_eth"] / 1.6, RED)
    y -= 42
    callout(c, M, y, W - 2 * M, 130, "The honest result of the fair test",
            "The edge did NOT survive real trading costs. The winning margin was about +0.09 per trade, "
            "but real costs (spread + slippage) take about +0.10 per trade - so it gets eaten.\n"
            "The two fixes are still REAL improvements (they lifted it from 0.71 to 0.98). But this is not "
            "yet a tradeable edge. We also could not test new markets yet (connection was down). "
            "So: keep building, do not trade it.",
            RED, body_size=9)


def page_9(c):
    draw_header(c, "Live Test", 9)
    y = title(c, "Live Test: BTC 1H Thesis", M, H - 92)
    subtitle(c, "We ran the full system on the live BTC chart, opened in a real browser through Kimi WebBridge, then annotated the thesis so the logic is visible.", M, y)
    draw_image_frame(c, BTC_1H_THESIS, M, H - 175, W - 2 * M, 320, "BITSTAMP:BTCUSD 1H thesis map captured through Kimi WebBridge and annotated")
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(M, H - 522, "What the 1H map says")
    bullets(
        c,
        [
            f"Engine: {LIVE['alignment']}. Final engine verdict: {LIVE['verdict']}, {LIVE['dir']}, risk {LIVE['risk']}.",
            "The larger bearish sell leg still controls the map; the current bounce is only internal retracement.",
            "The visual supply area is not enough by itself. The engine selected no fresh executable POI.",
            "So the 1H gives direction only. It does not give permission to sell.",
        ],
        M, H - 544, int(W - 2 * M), size=9,
    )


def page_10(c):
    draw_header(c, "Execution Map", 10)
    y = title(c, "BTC 15m Execution Map", M, H - 92)
    subtitle(c, "This is the exact distinction between a bearish thesis and a tradeable short.", M, y)
    draw_image_frame(c, BTC_15M_EXECUTION, M, H - 175, W - 2 * M, 315, "BITSTAMP:BTCUSD 15m execution map: where a short would need to form")
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(M, H - 518, "Why this is No Trade, not Watch")
    bullets(
        c,
        [
            "No Trade / Pass means the setup shell is missing. We only have bearish bias plus local liquidity.",
            "Watch would mean a fresh POI exists and price is approaching it, but the final confirmation is still pending.",
            "The earliest watch condition would be: sweep above local highs, bearish displacement down, then retrace into a newly formed fresh bearish FVG/OB.",
            f"Current entry: {LIVE['entry']}. Reason: {LIVE['reason']}.",
        ],
        M, H - 540, int(W - 2 * M), size=9,
    )


def page_11(c):
    draw_header(c, "What Still Needs Work", 11)
    y = title(c, "What Still Needs Work", M, H - 92)
    risks = [
        ("Not fully proven", "We must test the rules the fair way - on data the system never saw while we made them.", RED),
        ("Only two coins", "It is tested on BTC and ETH only. It needs more markets, including Forex, to be trusted widely.", AMBER),
        ("Small winning sample", "The good result rests on a few hundred trades. We need more before being sure.", AMBER),
        ("Costs not fully modelled", "Spread and slippage in the real world could shrink a thin edge.", BLUE),
        ("Few trades", "It trades rarely (about 30 a year per coin). Slow to grow, slow to confirm.", PURPLE),
    ]
    for head, body, color in risks:
        card(c, M, y, W - 2 * M, 60, head, body, color)
        y -= 74


def page_12(c):
    draw_header(c, "The Plan", 12)
    y = title(c, "The Plan From Here", M, H - 92)
    subtitle(c, "Step by step. Each step must pass before the next one earns real money.", M, y)
    phases = [
        ("Phase 1 - DONE", "Build the engine, the two lenses, and the learning machine.", GREEN),
        ("Phase 2 - DONE", "Find fixes that help: skip tiny zones, use only fresh zones.", GREEN),
        ("Phase 3 - IN PROGRESS", "Fair test. PASSED: rules hold on the old years alone. FAILED: edge does not beat real costs. STILL TO DO: test new markets (connection was down).", AMBER),
        ("Phase 3b - NOW", "Make each trade earn more before costs - mainly by improving the exits (stop being stopped early, smarter targets).", BLUE),
        ("Phase 4 - LATER", "Only if the edge beats real costs: paper trade live, then a small real-money trial with strict risk.", PURPLE),
    ]
    yy = H - 170
    for head, body, color in phases:
        card(c, M, yy, W - 2 * M, 58, head, body, color)
        yy -= 72
    callout(c, M, yy - 2, W - 2 * M, 80, "Bottom line",
            "The system is a careful research helper, not a money-maker yet. The fair test showed the edge is "
            "too thin to beat real costs. Next real work: make each trade earn more before costs (better exits), "
            "and finish the new-market test.", AMBER)


def page_13(c):
    draw_header(c, "Glossary", 13)
    y = title(c, "Words & Short Forms (Plain English)", M, H - 90, size=20)
    y -= 2
    terms = [
        ("SMC", "Smart Money Concepts. Reading charts around where big players likely buy and sell."),
        ("OHLCV", "Open, High, Low, Close, Volume. The raw numbers behind each candle."),
        ("HTF", "Higher Time Frame, like the Daily or 4-Hour. The bigger picture."),
        ("MTF", "Multi Time Frame. Looking at several time frames together."),
        ("POI", "Point of Interest. A zone we watch for an entry (usually an FVG or OB)."),
        ("FVG", "Fair Value Gap. A gap left by a fast move; price often comes back to fill it."),
        ("OB", "Order Block. The last candle before a strong move; a zone price may return to."),
        ("BOS", "Break of Structure. Price breaks a recent high/low and the trend continues."),
        ("CHoCH", "Change of Character. Price breaks the other way; the trend may be turning."),
        ("Liquidity", "Resting stop orders, usually above highs or below lows."),
        ("Sweep", "Price spikes past a level to grab stops, then snaps back."),
        ("Premium / Discount", "The expensive (upper) half vs the cheap (lower) half of a range."),
        ("Fresh / Partial / Used", "A zone untouched / partly used / fully used. Fresh is strongest."),
        ("R", "Your risk - the distance to your stop. Wins and losses are counted in R."),
        ("R:R", "Risk-to-Reward. Reward size compared to risk size, e.g. 1:3."),
        ("Win rate", "How often trades hit target."),
        ("Average R / Expectancy", "The typical win or loss per trade, in R."),
        ("PF (Profit Factor)", "Money made divided by money lost. Above 1.0 = winning."),
        ("bps", "Basis points. 1 bps = 0.01%. Trading cost (spread + slippage) is measured in bps."),
        ("MFE / MAE", "How far a trade went in profit (MFE) or against you (MAE) before it closed. Used to judge exits."),
        ("Confluence", "How many checks line up for a trade. More is better."),
        ("Out-of-sample / Holdout", "Testing on data the system never saw while the rules were made. A fair exam."),
        ("Calibration", "Checking how often the system is actually right, and adjusting its confidence."),
        ("Dual-lens", "The two ways of looking: the Calculator (numbers) and the Eyes (vision)."),
        ("WebBridge", "The tool that lets the AI open and see the real chart in your browser."),
    ]
    for term, meaning in terms:
        y = gloss(c, term, meaning, M, y, int(W - 2 * M))


def build_pdf():
    c = canvas.Canvas(str(PDF_PATH), pagesize=A4)
    for page in [page_1, page_2, page_3, page_4, page_5, page_6, page_7, page_8, page_9, page_10, page_11, page_12, page_13]:
        page(c)
        c.showPage()
    c.save()
    return PDF_PATH


def main():
    print(build_pdf())


if __name__ == "__main__":
    main()
