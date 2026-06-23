#!/usr/bin/env python3
"""Drift discovery — does ANY feature subset isolate forward directional drift?

E2 + the exit diagnostic proved the average triggered setup is ~driftless: only
~7.8% ever reach +3R, ~18% reach +2R. For 3:1 @ 65% to be reachable at all, some
*subset* of entries must have a much higher MFE reach-rate. This scans every
available feature and ranks buckets by how far they lift P(MFE>=2R)/P(MFE>=3R)
above the base — i.e. where (if anywhere) forward drift concentrates.

This is HYPOTHESIS GENERATION only (many comparisons -> some lift is chance). A
candidate must later survive the charter's walk-forward + locked-holdout before
belief. We look for large, economically sensible lifts with adequate n.

Usage:
  python3 tools/discover_drift.py --research backtests/research/*_4yr_enriched.csv \
      --target-cost-bps 10 --min-n 150 --output-dir backtests/regime/drift1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _tf(s):
    return s.astype(str).str.strip().str.lower().map({"true": 1.0, "false": 0.0}).fillna(0.0)


NUMERIC = ["displacement_score", "sweep_depth_atr", "atr_pct", "adx_at_decision",
           "premium_discount_ratio", "poi_width_pct", "poi_score", "confluence_score",
           "structure_event_density", "planned_rr", "htf_agreement_ratio", "poi_age_bars",
           "sweep_recency_bars", "body_ratio_at_decision", "range_pct_at_decision",
           # Phase 2 liquidity-significance features
           "liquidity_significance", "swept_touch_count", "swept_htf_confluence", "swept_round_prox"]
BOOLS = ["swept_is_equal_cluster",
         "htf_aligned", "is_killzone", "chk_directional_bias", "chk_fresh_or_partial_poi",
         "chk_premium_discount_aligned", "chk_liquidity_sweep", "chk_displacement_break",
         "chk_sweep_before_break", "chk_price_at_or_near_poi", "chk_stop_has_volatility_buffer",
         "chk_risk_reward_floor"]
CATEG = ["session", "poi_kind", "poi_status", "break_strength", "setup_grade", "htf_alignment"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--research", nargs="+", required=True)
    p.add_argument("--target-cost-bps", type=float, default=10.0)
    p.add_argument("--min-n", type=int, default=150)
    p.add_argument("--output-dir", default="backtests/regime/drift")
    args = p.parse_args()

    paths = []
    for pat in args.research:
        paths += [Path(x) for x in sorted(Path().glob(pat))] if any(c in pat for c in "*?[") else [Path(pat)]
    df = pd.concat([pd.read_csv(x) for x in paths], ignore_index=True)
    df = df[_tf(df["triggered"]) == 1.0].copy()
    for c in ("r_multiple", "mfe_r", "mae_r"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["mfe_r", "mae_r", "r_multiple"]).reset_index(drop=True)

    mfe = df["mfe_r"].values.astype(float)
    realized = df["r_multiple"].values.astype(float)
    # net realized R at target bps
    if {"entry_price", "risk_per_r", "cost_bps"}.issubset(df.columns):
        ep = pd.to_numeric(df["entry_price"], errors="coerce").values
        rk = pd.to_numeric(df["risk_per_r"], errors="coerce").values
        cb = pd.to_numeric(df["cost_bps"], errors="coerce").values
        with np.errstate(divide="ignore", invalid="ignore"):
            adj = (ep / rk) * (cb - args.target_cost_bps) / 10000.0
        net = realized + np.where(np.isfinite(adj) & (rk > 0), adj, -0.10)
    else:
        net = realized - 0.10

    base2, base3 = float(np.mean(mfe >= 2)), float(np.mean(mfe >= 3))
    base_net = float(np.mean(net))

    rows = []  # (label, n, p2, p3, net_avg)
    def add(label, mask):
        n = int(mask.sum())
        if n < args.min_n:
            return
        rows.append((label, n, float(np.mean(mfe[mask] >= 2)), float(np.mean(mfe[mask] >= 3)), float(np.mean(net[mask]))))

    for col in NUMERIC:
        if col not in df.columns:
            continue
        v = pd.to_numeric(df[col], errors="coerce")
        try:
            q = pd.qcut(v, 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
        except ValueError:
            continue
        for lvl in q.cat.categories:
            m = (q == lvl).values
            lo, hi = v[m].min(), v[m].max()
            add(f"{col} {lvl} [{lo:.3g}..{hi:.3g}]", m)
    for col in BOOLS:
        if col not in df.columns:
            continue
        b = _tf(df[col]) == 1.0
        add(f"{col}=True", b.values)
        add(f"{col}=False", (~b).values)
    for col in CATEG:
        if col not in df.columns:
            continue
        for lvl in df[col].astype(str).unique():
            add(f"{col}={lvl}", (df[col].astype(str) == lvl).values)

    L = ["# Drift discovery — where (if anywhere) does forward drift concentrate?", ""]
    L.append(f"Triggered trades: {len(df)}  ·  min bucket n: {args.min_n}  ·  net cost: {args.target_cost_bps:g}bps")
    L.append(f"**Base rates:** P(MFE>=2R) = {base2:.1%}, P(MFE>=3R) = {base3:.1%}, net avg R = {base_net:+.3f}")
    L.append("")
    L.append("Target to make 3:1@65% even plausible: a sizeable bucket with P(MFE>=3R) far above "
             f"{base3:.1%} (ideally toward ~50%+). Hypothesis-generation only — survives nothing until walk-forward + holdout.")
    L.append("")

    # Rank by P(MFE>=3R) lift
    L += ["## Top buckets by P(MFE>=3R) — the 3:1 reach-rate", "",
          "| bucket | n | P(MFE>=2) | P(MFE>=3) | net avgR |", "|---|--:|--:|--:|--:|"]
    for label, n, p2, p3, na in sorted(rows, key=lambda x: x[3], reverse=True)[:18]:
        L.append(f"| {label} | {n} | {p2:.1%} | {p3:.1%} | {na:+.3f} |")
    L.append("")
    # Rank by net avg R
    L += ["## Top buckets by net avg R (after cost)", "",
          "| bucket | n | P(MFE>=2) | P(MFE>=3) | net avgR |", "|---|--:|--:|--:|--:|"]
    for label, n, p2, p3, na in sorted(rows, key=lambda x: x[4], reverse=True)[:18]:
        L.append(f"| {label} | {n} | {p2:.1%} | {p3:.1%} | {na:+.3f} |")
    L.append("")

    best3 = max(rows, key=lambda x: x[3]) if rows else None
    bestnet = max(rows, key=lambda x: x[4]) if rows else None
    L += ["## Read", ""]
    if best3:
        L.append(f"- Highest 3R reach-rate bucket: **{best3[0]}** -> P(MFE>=3R) {best3[3]:.1%} (base {base3:.1%}), n={best3[1]}, net {best3[4]:+.3f}R.")
    if bestnet:
        L.append(f"- Highest after-cost bucket: **{bestnet[0]}** -> net {bestnet[4]:+.3f}R, n={bestnet[1]}, P(MFE>=3R) {bestnet[3]:.1%}.")
    if best3 and best3[3] < 2 * base3:
        L.append("- **No existing feature lifts the 3R reach-rate dramatically. Drift is not hiding in the current feature set "
                 "-> we need NEW entry signals (liquidity significance, full sweep->displacement->CHoCH trigger) via a harvester change, "
                 "OR the honest-ceiling clause applies: 3:1@65% is not supported by these entries.**")
    else:
        L.append("- **A subset shows materially higher 3R reach-rate -> candidate entry filter. Must survive walk-forward + locked holdout before belief.**")
    L.append("")

    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "drift_report.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nWrote {out/'drift_report.md'}")


if __name__ == "__main__":
    main()
