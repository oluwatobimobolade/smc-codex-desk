#!/usr/bin/env python3
"""E1-diagnostic — exit efficiency: are we cutting winners, or do entries lack edge?

The regime fork (E2) showed even the best regime is ~breakeven GROSS while mean
planned R:R is ~2.7. That contradiction has exactly two explanations:
  (A) ENTRIES lack forward edge  -> no exit policy can save it.
  (B) EXITS are mismanaged       -> winners are cut far below their potential.
The logged max-favorable / max-adverse excursions (mfe_r, mae_r) distinguish them
without any re-simulation, on data already on disk.

Two honest bounds on a fixed-target-T policy (stop at -1R), since mfe/mae don't
record their time order:
  - UPPER bound (optimistic): trade reaches +T iff mfe_r >= T            -> reach-rate.
  - LOWER bound (pessimistic): win(+T) iff mfe_r >= T AND mae_r > -1.0;
    loss(-1) iff mae_r <= -1.0; else exit at realized R (timeout).
The truth lies between. If even the UPPER bound at T>=2 is weak, entries lack edge
(explanation A). If the LOWER bound at some T is after-cost positive, there is real
exit headroom worth a proper re-simulation (explanation B -> Phase-1 E1).

Usage:
  python3 tools/analyze_exit_efficiency.py --research backtests/research/*_4yr_enriched.csv \
      --target-cost-bps 10 --output-dir backtests/regime/exit1
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

from smc_desk import regime as rg
from smc_desk.ml_model import expectancy


def _tf(s):
    return s.astype(str).str.strip().str.lower().map({"true": 1.0, "false": 0.0}).fillna(0.0)


def _cost_per_r(df: pd.DataFrame, target_bps: float, fallback: float = 0.10) -> np.ndarray:
    """Per-trade cost in R units at target bps (positive number to subtract)."""
    if {"entry_price", "risk_per_r", "cost_bps"}.issubset(df.columns):
        ep = pd.to_numeric(df["entry_price"], errors="coerce").values
        rk = pd.to_numeric(df["risk_per_r"], errors="coerce").values
        with np.errstate(divide="ignore", invalid="ignore"):
            c = (ep / rk) * (target_bps) / 10000.0   # cost to OPEN+CLOSE at target bps, in R
        return np.where(np.isfinite(c) & (rk > 0), c, fallback)
    return np.full(len(df), fallback)


def fixed_target_bounds(mfe, mae, realized, cost_r, T):
    """Return (upper_avgR, lower_avgR, lower_win) for a fixed +T / -1 policy, net of cost."""
    reach = mfe >= T
    upper = np.where(reach, T, np.maximum(realized, -1.0)) - cost_r       # optimistic: every reach is a win
    hit_stop = mae <= -1.0
    lower_win = reach & (~hit_stop)
    lower = np.where(hit_stop, -1.0, np.where(lower_win, T, np.maximum(realized, -1.0))) - cost_r
    return float(np.mean(upper)), float(np.mean(lower)), float(np.mean(lower_win))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--research", nargs="+", required=True)
    p.add_argument("--target-cost-bps", type=float, default=10.0)
    p.add_argument("--output-dir", default="backtests/regime/exit")
    args = p.parse_args()

    paths = []
    for pat in args.research:
        paths += [Path(x) for x in sorted(Path().glob(pat))] if any(c in pat for c in "*?[") else [Path(pat)]
    df = pd.concat([pd.read_csv(x) for x in paths], ignore_index=True)
    df = df[_tf(df["triggered"]) == 1.0].copy()
    for c in ("r_multiple", "mfe_r", "mae_r"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["r_multiple", "mfe_r", "mae_r"]).reset_index(drop=True)
    df["htf_aligned_b"] = _tf(df["htf_aligned"]) == 1.0
    df["regime"] = [rg.classify(a, h) for a, h in zip(df["adx_at_decision"], df["htf_aligned_b"])]

    realized = df["r_multiple"].values.astype(float)
    mfe = df["mfe_r"].values.astype(float)
    mae = df["mae_r"].values.astype(float)
    cost_r = _cost_per_r(df, args.target_cost_bps)
    fav = (df["regime"] == rg.TREND_ALIGNED).values

    L = ["# E1-diagnostic — Exit efficiency: cutting winners, or no entry edge?", ""]
    L.append(f"Triggered trades: {len(df)}  ·  net cost target: {args.target_cost_bps:g}bps (exact).")
    L.append("")

    def block(name, m):
        n = int(m.sum())
        if n == 0:
            return [f"### {name}: no trades", ""]
        rz, mf, ma = realized[m], mfe[m], mae[m]
        win = rz > 0
        cap = rz[win] / np.clip(mf[win], 1e-9, None) if win.sum() else np.array([0.0])
        out = [f"### {name}  (n={n})", "",
               f"- realized R: mean {rz.mean():+.3f}, win% {win.mean():.1%}",
               f"- MFE (max favorable, R): mean {mf.mean():.2f}, median {np.median(mf):.2f}",
               f"- MAE (max adverse, R): mean {ma.mean():.2f}, median {np.median(ma):.2f}",
               f"- reach-rate  P(MFE>=1) {np.mean(mf>=1):.1%} · P(>=1.5) {np.mean(mf>=1.5):.1%} · "
               f"P(>=2) {np.mean(mf>=2):.1%} · P(>=3) {np.mean(mf>=3):.1%}",
               f"- capture ratio on winners (realized/MFE): mean {cap.mean():.2f}, median {float(np.median(cap)):.2f}",
               ""]
        out += ["| fixed target T | UPPER avgR (optimistic) | LOWER avgR (pessimistic) | LOWER win% |",
                "|--:|--:|--:|--:|"]
        for T in (1.0, 1.5, 2.0, 2.5, 3.0):
            u, lo, lw = fixed_target_bounds(mf, ma, rz, cost_r[m], T)
            out.append(f"| {T:g} | {u:+.3f} | {lo:+.3f} | {lw:.1%} |")
        out.append("")
        return out

    L += ["## All triggered trades", ""] + block("All", np.ones(len(df), bool))
    L += ["## Favorable regime only (trend_aligned)", ""] + block("trend_aligned", fav)

    # Verdict logic: is there exit headroom?
    u2, lo2, _ = fixed_target_bounds(mfe, mae, realized, cost_r, 2.0)
    u3, lo3, _ = fixed_target_bounds(mfe, mae, realized, cost_r, 3.0)
    reach2 = float(np.mean(mfe >= 2.0)); reach3 = float(np.mean(mfe >= 3.0))
    L += ["## Verdict — which explanation does the data support?", ""]
    L.append(f"- Optimistic ceiling: P(MFE>=2R) = {reach2:.1%}, P(MFE>=3R) = {reach3:.1%}.")
    L.append(f"- Fixed-T=2 after cost: between {lo2:+.3f}R (pessimistic) and {u2:+.3f}R (optimistic).")
    L.append(f"- Fixed-T=3 after cost: between {lo3:+.3f}R (pessimistic) and {u3:+.3f}R (optimistic).")
    if u2 <= 0.0:
        L.append("- **Explanation A (no entry edge): even the OPTIMISTIC fixed-target ceiling is <= 0 after cost. "
                 "Exit tweaks cannot save it; the entry signal itself lacks forward edge. Pivot to entry quality "
                 "(liquidity significance, sweep->displacement->CHoCH trigger), not exits.**")
    elif lo2 > 0.0 or lo3 > 0.0:
        L.append("- **Explanation B (exit headroom is real): even the PESSIMISTIC bound is positive at some T. "
                 "A proper liquidity-targeted / fixed-T exit re-simulation (E1) is worth the re-run.**")
    else:
        L.append("- **Mixed: optimistic bound positive, pessimistic negative. Entries have *some* forward push but "
                 "ordering matters -> a proper path-aware exit re-simulation (E1) is needed to resolve it.**")
    L.append("")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "exit_report.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nWrote {out/'exit_report.md'}")


if __name__ == "__main__":
    main()
