#!/usr/bin/env python3
"""Calibrate (train) from the research dataset.

This is the honest, interpretable "training" step. It reads the research rows
(features -> realized R) and measures, on *triggered* setups only:

* overall expectancy (win rate, avg R, profit factor);
* expectancy by confluence band  -> does the score actually rank setups?
* expectancy by HTF alignment / session / setup grade;
* a per-component ablation: avg R when each checklist item is TRUE vs FALSE
  -> which SMC ingredients carry expectancy, and which are dead weight;
* learned component weights from that ablation, written to JSON.

No black box: every number traces to a bucket of real simulated trades. With a
small/overlapping sample the numbers are noisy on purpose — the point is the
machine that learns, and the honesty about confidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from pathlib import Path
from typing import Any

CHECKLIST_KEYS = [
    "directional_bias", "fresh_or_partial_poi", "premium_discount_aligned",
    "liquidity_sweep", "displacement_break", "sweep_before_break",
    "price_at_or_near_poi", "stop_has_volatility_buffer", "risk_reward_floor",
]


def load_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for r in csv.DictReader(handle):
                rows.append(r)
    return rows


def _f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _tf(v: Any) -> bool:
    return str(v).strip().lower() == "true"


def dedupe_overlaps(triggered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one trade per (symbol, entry_index) so overlapping decision steps
    that all fill at the same candle are not double-counted."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for r in sorted(triggered, key=lambda x: (x.get("symbol", ""), x.get("entry_index", ""))):
        key = (r.get("symbol", ""), str(r.get("entry_index")))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def expectancy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rs = [_f(r["r_multiple"]) for r in rows if _f(r["r_multiple"]) is not None]
    if not rs:
        return {"n": 0, "win_rate": None, "avg_r": None, "total_r": 0.0, "profit_factor": None}
    wins = [r for r in rs if r > 0.05]
    losses = [r for r in rs if r < -0.05]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "n": len(rs),
        "win_rate": round(len(wins) / len(rs), 3),
        "avg_r": round(sum(rs) / len(rs), 4),
        "total_r": round(sum(rs), 3),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
    }


def by_bucket(rows: list[dict[str, Any]], key_fn) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        buckets.setdefault(key_fn(r), []).append(r)
    return {k: expectancy(v) for k, v in sorted(buckets.items())}


def rr_floor_sweep(triggered: list[dict[str, Any]], thresholds=(1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0)) -> list[dict[str, Any]]:
    """Cumulative expectancy of trades whose planned R:R >= threshold.

    This is the direct test of 'raise the R:R floor': as the floor rises, the
    sample shrinks but (hopefully) average R climbs. The sweet spot is the
    highest floor that still keeps a usable sample with rising expectancy.
    """
    out = []
    for t in thresholds:
        sub = [r for r in triggered if (_f(r.get("planned_rr")) or 0.0) >= t]
        e = expectancy(sub)
        e["floor"] = t
        out.append(e)
    return out


def rr_band(r: dict[str, Any]) -> str:
    v = _f(r.get("planned_rr")) or 0.0
    if v < 2:
        return "rr<2"
    if v < 3:
        return "rr2-3"
    if v < 4:
        return "rr3-4"
    if v < 6:
        return "rr4-6"
    return "rr6+"


def confluence_band(r: dict[str, Any]) -> str:
    c = _f(r["confluence_score"]) or 0.0
    if c < 0.5:
        return "0.00-0.49"
    if c < 0.625:
        return "0.50-0.62"
    if c < 0.75:
        return "0.63-0.74"
    if c < 0.875:
        return "0.75-0.87"
    return "0.88-1.00"


def main() -> None:
    p = argparse.ArgumentParser(description="Calibrate SMC component weights from the research dataset.")
    p.add_argument("--research", nargs="+", required=True, help="One or more research CSV paths.")
    p.add_argument("--output-dir", default="backtests/calibration")
    p.add_argument("--dedupe", choices=["on", "off"], default="on")
    args = p.parse_args()

    rows = load_rows([Path(x) for x in args.research])
    triggered = [r for r in rows if _tf(r["triggered"])]
    if args.dedupe == "on":
        triggered = dedupe_overlaps(triggered)

    overall = expectancy(triggered)

    # Per-component ablation: avg R with the check TRUE vs FALSE.
    ablation: dict[str, Any] = {}
    weights: dict[str, float] = {}
    for key in CHECKLIST_KEYS:
        col = f"chk_{key}"
        on = [r for r in triggered if _tf(r.get(col))]
        off = [r for r in triggered if not _tf(r.get(col))]
        e_on, e_off = expectancy(on), expectancy(off)
        lift = None
        if e_on["avg_r"] is not None and e_off["avg_r"] is not None:
            lift = round(e_on["avg_r"] - e_off["avg_r"], 4)
        ablation[key] = {"true": e_on, "false": e_off, "lift_avg_r": lift}
        weights[key] = max(0.0, lift) if lift is not None else 0.0

    total_w = sum(weights.values())
    norm_weights = {k: round(v / total_w, 3) for k, v in weights.items()} if total_w > 0 else {k: round(1 / len(weights), 3) for k in weights}

    report = {
        "samples": {"total_setups": len(rows), "triggered": len(triggered), "deduped": args.dedupe},
        "overall_expectancy": overall,
        "rr_floor_sweep": rr_floor_sweep(triggered),
        "by_rr_band": by_bucket(triggered, rr_band),
        "by_confluence_band": by_bucket(triggered, confluence_band),
        "by_htf_aligned": by_bucket(triggered, lambda r: f"htf_aligned={r.get('htf_aligned')}"),
        "by_setup_grade": by_bucket(triggered, lambda r: f"grade_{r.get('setup_grade')}"),
        "by_session": by_bucket(triggered, lambda r: r.get("session", "?")),
        "by_direction": by_bucket(triggered, lambda r: r.get("direction", "?")),
        "component_ablation": ablation,
        "learned_weights": norm_weights,
        "note": "Triggered, optionally deduped by entry candle. Small/overlapping samples are noisy; read lifts as directional, not precise.",
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "calibration.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "learned_weights.json").write_text(json.dumps(norm_weights, indent=2), encoding="utf-8")
    (out_dir / "calibration_report.md").write_text(render_md(report), encoding="utf-8")
    print(render_md(report))
    print(f"\nWrote {out_dir/'calibration.json'}, {out_dir/'learned_weights.json'}, {out_dir/'calibration_report.md'}")


def _exp_row(label: str, e: dict[str, Any]) -> str:
    return f"| {label} | {e['n']} | {e['win_rate']} | {e['avg_r']} | {e['total_r']} | {e['profit_factor']} |"


def render_md(report: dict[str, Any]) -> str:
    s = report["samples"]
    o = report["overall_expectancy"]
    lines = [
        "# SMC Calibration Report",
        "",
        f"Total setups sampled: **{s['total_setups']}**  ·  triggered (entered): **{s['triggered']}**  ·  dedupe: {s['deduped']}",
        "",
        f"## Overall expectancy (triggered)",
        f"- n={o['n']}  ·  win rate **{o['win_rate']}**  ·  avg R **{o['avg_r']}**  ·  total R {o['total_r']}  ·  profit factor {o['profit_factor']}",
        "",
        "## R:R floor sweep (take only setups with planned R:R >= floor)",
        "| floor | n | win% | avg R | total R | PF |",
        "|--:|--:|--:|--:|--:|--:|",
    ]
    for e in report["rr_floor_sweep"]:
        lines.append(f"| >={e['floor']:g} | {e['n']} | {e['win_rate']} | {e['avg_r']} | {e['total_r']} | {e['profit_factor']} |")
    lines += [
        "",
        "## Expectancy by confluence band",
        "| band | n | win% | avg R | total R | PF |",
        "|---|--:|--:|--:|--:|--:|",
    ]
    lines += [_exp_row(k, v) for k, v in report["by_confluence_band"].items()]
    lines += ["", "## By HTF alignment", "| bucket | n | win% | avg R | total R | PF |", "|---|--:|--:|--:|--:|--:|"]
    lines += [_exp_row(k, v) for k, v in report["by_htf_aligned"].items()]
    lines += ["", "## By session", "| session | n | win% | avg R | total R | PF |", "|---|--:|--:|--:|--:|--:|"]
    lines += [_exp_row(k, v) for k, v in report["by_session"].items()]
    lines += ["", "## Component ablation (avg R: check TRUE vs FALSE)",
              "| component | n(T) | avgR(T) | n(F) | avgR(F) | lift |", "|---|--:|--:|--:|--:|--:|"]
    for k, v in report["component_ablation"].items():
        t, f = v["true"], v["false"]
        lines.append(f"| {k} | {t['n']} | {t['avg_r']} | {f['n']} | {f['avg_r']} | {v['lift_avg_r']} |")
    lines += ["", "## Learned weights (normalized positive lift)"]
    for k, w in sorted(report["learned_weights"].items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {w}")
    lines += ["", f"> {report['note']}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
