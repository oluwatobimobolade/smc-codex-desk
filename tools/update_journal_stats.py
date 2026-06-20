#!/usr/bin/env python3
"""
Update journal/stats.json from completed journal entries.

Scans journal/YYYY-MM-DD/<instrument>/<instrument>_<HHMM>_<GRADE>.md files,
looks for the Outcome section, and aggregates statistics.

Usage:
    python3 tools/update_journal_stats.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_ROOT = Path(__file__).resolve().parents[1] / "journal"
STATS_FILE = JOURNAL_ROOT / "stats.json"


def extract_outcome(text: str) -> dict | None:
    """Extract outcome fields from the markdown Outcome section."""
    section_match = re.search(
        r"## Outcome \(update after trade\)(.*?)(?=\n## |\Z)",
        text,
        re.DOTALL,
    )
    if not section_match:
        return None

    section = section_match.group(1)

    result_match = re.search(r"\*\*Result:\*\*\s*([\w\s/]+)", section)
    grade_match = re.search(r"\*\*Setup Grade:\*\*\s*(A\+|A|B|C)", text)
    pnl_match = re.search(r"\*\*P&L \(R\):\*\*\s*([-\d.]+)", section)

    if not result_match or not grade_match:
        return None

    result_raw = result_match.group(1).strip().lower()
    # Normalize common variants.
    if "no trade" in result_raw or "cancelled" in result_raw or "canceled" in result_raw:
        result = "no_trade"
    elif "win" in result_raw:
        result = "win"
    elif "loss" in result_raw:
        result = "loss"
    elif "break" in result_raw or "breakeven" in result_raw or "be" == result_raw:
        result = "breakeven"
    else:
        result = result_raw

    return {
        "result": result,
        "grade": grade_match.group(1),
        "pnl_r": float(pnl_match.group(1)) if pnl_match else 0.0,
    }


def main() -> int:
    if not STATS_FILE.exists():
        print(f"Stats file not found: {STATS_FILE}")
        return 1

    stats = json.loads(STATS_FILE.read_text(encoding="utf-8"))

    # Reset counters.
    stats["total_analyses"] = 0
    stats["total_trades"] = 0
    stats["wins"] = 0
    stats["losses"] = 0
    stats["breakeven"] = 0
    stats["total_r"] = 0.0
    stats["grade_breakdown"] = {
        "A+": {"trades": 0, "wins": 0, "losses": 0, "breakeven": 0},
        "A": {"trades": 0, "wins": 0, "losses": 0, "breakeven": 0},
        "B": {"trades": 0, "wins": 0, "losses": 0, "breakeven": 0},
        "C": {"trades": 0, "wins": 0, "losses": 0, "breakeven": 0},
    }

    for day_dir in JOURNAL_ROOT.glob("2*-*-*"):
        if not day_dir.is_dir():
            continue
        for md_file in day_dir.rglob("*.md"):
            stats["total_analyses"] += 1
            text = md_file.read_text(encoding="utf-8")
            outcome = extract_outcome(text)
            if not outcome:
                continue

            grade = outcome["grade"]
            result = outcome["result"]

            # No-trade / cancelled analyses are recorded but not counted as executed trades.
            if result == "no_trade":
                continue

            stats["total_trades"] += 1
            stats["grade_breakdown"][grade]["trades"] += 1
            if result == "win":
                stats["wins"] += 1
                stats["grade_breakdown"][grade]["wins"] += 1
            elif result == "loss":
                stats["losses"] += 1
                stats["grade_breakdown"][grade]["losses"] += 1
            else:
                stats["breakeven"] += 1
                stats["grade_breakdown"][grade]["breakeven"] += 1

            stats["total_r"] += outcome["pnl_r"]

    total_trades = stats["total_trades"]
    stats["win_rate"] = round(stats["wins"] / total_trades, 3) if total_trades > 0 else 0.0
    stats["avg_r"] = round(stats["total_r"] / total_trades, 3) if total_trades > 0 else 0.0
    stats["last_updated"] = datetime.now(timezone.utc).isoformat()

    STATS_FILE.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
