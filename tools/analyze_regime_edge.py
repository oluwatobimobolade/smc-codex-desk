#!/usr/bin/env python3
"""E2 — the regime fork: is the SMC edge regime-conditional or regime-fragile?

Runs on the EXISTING enriched research CSVs (no re-harvest): every triggered
setup already carries ADX, ATR%, HTF-alignment, exact-cost inputs and realized R.
We classify each setup's regime (smc_desk/regime.py), then ask two questions:

  1. EXPECTANCY BY REGIME (gross + after realistic costs): does the edge
     concentrate in the trend-aligned regime and vanish in chop?
  2. STABILITY (the wall): split the timeline into calendar buckets and check
     whether the favorable-regime edge is positive in MOST buckets — the
     walk-forward test that has been failing on the ungated population.

If the favorable regime is after-cost positive AND positive in >=3 of N
calendar buckets on >=3 pairs -> the edge is conditional and GATING is the key
(GATE 1 of the plan). If even the gated edge is unstable -> regime-fragile.

Exact costs: r_cost = r_multiple + (entry_price/risk_per_r)*(cost_bps - target_bps)/10000
(identical convention to tools/train_ml_model.py).

Usage:
  python3 tools/analyze_regime_edge.py --research backtests/research/*_4yr_enriched.csv \
      --target-cost-bps 10 --output-dir backtests/regime/run1
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


def _exact_cost_r(df: pd.DataFrame, target_bps: float, fallback_haircut: float = 0.10) -> np.ndarray:
    r = pd.to_numeric(df["r_multiple"], errors="coerce").values.astype(float)
    if {"entry_price", "risk_per_r", "cost_bps"}.issubset(df.columns):
        ep = pd.to_numeric(df["entry_price"], errors="coerce").values
        rk = pd.to_numeric(df["risk_per_r"], errors="coerce").values
        cb = pd.to_numeric(df["cost_bps"], errors="coerce").values
        with np.errstate(divide="ignore", invalid="ignore"):
            adj = (ep / rk) * (cb - target_bps) / 10000.0
        adj = np.where(np.isfinite(adj) & (rk > 0), adj, -fallback_haircut)
        return r + adj
    return r - fallback_haircut


def _row(label, e):
    return f"| {label} | {e['n']} | {e['win_rate']} | {e['avg_r']} | {e['total_r']} | {e['profit_factor']} |"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--research", nargs="+", required=True)
    p.add_argument("--target-cost-bps", type=float, default=10.0)
    p.add_argument("--buckets", type=int, default=6, help="Calendar buckets for the stability test.")
    p.add_argument("--adx-trend-min", type=float, default=25.0)
    p.add_argument("--adx-chop-max", type=float, default=18.0)
    p.add_argument("--output-dir", default="backtests/regime/run")
    args = p.parse_args()

    cfg = rg.RegimeConfig(adx_trend_min=args.adx_trend_min, adx_chop_max=args.adx_chop_max)

    paths = []
    for pat in args.research:
        paths += [Path(x) for x in sorted(Path().glob(pat))] if any(c in pat for c in "*?[") else [Path(pat)]
    df = pd.concat([pd.read_csv(x) for x in paths], ignore_index=True)
    df = df[_tf(df["triggered"]) == 1.0].copy()
    df["r_multiple"] = pd.to_numeric(df["r_multiple"], errors="coerce")
    df = df.dropna(subset=["r_multiple"]).reset_index(drop=True)
    df["t"] = pd.to_datetime(df["decision_time"], utc=True, errors="coerce")
    df = df.dropna(subset=["t"]).sort_values("t").reset_index(drop=True)

    # self-normalized ATR percentile rank, per symbol (reproducible across markets)
    df["atr_pct_rank"] = df.groupby("symbol")["atr_pct"].rank(pct=True)
    df["htf_aligned_b"] = _tf(df["htf_aligned"]) == 1.0
    df["regime"] = [rg.classify(a, h, cfg) for a, h in zip(df["adx_at_decision"], df["htf_aligned_b"])]
    df["volband"] = [rg.vol_band(x, cfg) for x in df["atr_pct_rank"]]

    r_net = _exact_cost_r(df, args.target_cost_bps)
    r_gross = df["r_multiple"].values.astype(float)
    fav = (df["regime"] == rg.TREND_ALIGNED).values

    L = ["# E2 — Regime Fork: is the SMC edge conditional or fragile?", ""]
    L.append(f"Triggered trades: {len(df)}  ·  symbols: {sorted(df['symbol'].unique())}")
    L.append(f"Costs: gross = logged {df['cost_bps'].iloc[0]:g}bps ; net = {args.target_cost_bps:g}bps (exact).  "
             f"Regime cfg: ADX trend>= {cfg.adx_trend_min:g}, chop<= {cfg.adx_chop_max:g}.")
    L.append("")

    # ---- 1. Expectancy by regime ----
    L += ["## 1. Expectancy by regime", "",
          "### Gross (logged cost)", "", "| regime | n | win% | avg R | total R | PF |", "|---|--:|--:|--:|--:|--:|"]
    for reg in [rg.TREND_ALIGNED, rg.TREND_COUNTER, rg.TRANSITIONAL, rg.CHOP]:
        m = (df["regime"] == reg).values
        if m.sum():
            L.append(_row(reg, expectancy(r_gross[m])))
    L += ["", f"### After {args.target_cost_bps:g}bps (exact) — the number that matters", "",
          "| regime | n | win% | avg R | total R | PF |", "|---|--:|--:|--:|--:|--:|"]
    for reg in [rg.TREND_ALIGNED, rg.TREND_COUNTER, rg.TRANSITIONAL, rg.CHOP]:
        m = (df["regime"] == reg).values
        if m.sum():
            L.append(_row(reg, expectancy(r_net[m])))
    L += ["", _row("ALL (no gate)", expectancy(r_net)), ""]

    # ---- 2. Favorable regime x volatility ----
    L += ["## 2. Favorable regime (trend_aligned) x volatility band — after cost", "",
          "| vol band | n | win% | avg R | total R | PF |", "|---|--:|--:|--:|--:|--:|"]
    for vb in [rg.VOL_LOW, rg.VOL_MID, rg.VOL_HIGH]:
        m = fav & (df["volband"] == vb).values
        if m.sum():
            L.append(_row(vb, expectancy(r_net[m])))
    L.append("")

    # ---- 3. Favorable regime per symbol (reproducibility) ----
    L += ["## 3. Favorable regime, per symbol (after cost) — is it carried by one pair?", "",
          "| symbol | n | win% | avg R | PF |", "|---|--:|--:|--:|--:|"]
    pos_syms = 0
    for s in sorted(df["symbol"].unique()):
        m = fav & (df["symbol"] == s).values
        if m.sum():
            e = expectancy(r_net[m])
            if e["avg_r"] is not None and e["avg_r"] > 0:
                pos_syms += 1
            L.append(f"| {s} | {e['n']} | {e['win_rate']} | {e['avg_r']} | {e['profit_factor']} |")
    L.append("")

    # ---- 4. Stability: calendar-bucket walk-forward (the wall) ----
    def bucket_positivity(mask):
        idx = np.where(mask)[0]
        if len(idx) < args.buckets * 5:
            return None, []
        chunks = np.array_split(idx, args.buckets)
        out = []
        for ch in chunks:
            e = expectancy(r_net[ch])
            out.append((e["n"], e["avg_r"]))
        pos = sum(1 for _, a in out if a is not None and a > 0)
        return pos, out

    L += ["## 4. Stability across calendar buckets (after cost) — THE test", ""]
    for label, mask in [("ALL trades (no gate)", np.ones(len(df), bool)),
                        ("Favorable regime (trend_aligned)", fav)]:
        pos, out = bucket_positivity(mask)
        if pos is None:
            L.append(f"- **{label}:** too few trades for {args.buckets} buckets.")
            continue
        seq = "  ".join(f"{a if a is not None else 'na'}" for _, a in out)
        L.append(f"- **{label}:** {pos}/{len(out)} buckets positive.  avg R by bucket: {seq}")
    L.append("")

    # ---- 5. 3:1 lens: planned RR in favorable regime ----
    prr = pd.to_numeric(df.loc[fav, "planned_rr"], errors="coerce").dropna()
    if len(prr):
        share3 = float((prr >= 3.0).mean())
        L += ["## 5. 3:1 lens (favorable regime)", "",
              f"- planned R:R — median {prr.median():.2f}, mean {prr.mean():.2f}; "
              f"share with planned R:R >= 3.0: {share3:.1%}",
              f"- (north star is 3:1 @ 65-70%; favorable-regime win% above is the honest current read)", ""]

    # ---- Verdict ----
    e_fav = expectancy(r_net[fav])
    e_all = expectancy(r_net)
    fav_pos, _ = bucket_positivity(fav)
    after_cost_positive = e_fav["avg_r"] is not None and e_fav["avg_r"] > 0
    stable = fav_pos is not None and fav_pos >= max(3, (args.buckets // 2) + 1)
    reproducible = pos_syms >= 3
    L += ["## Verdict", ""]
    L.append(f"- Favorable regime after cost: avg R = {e_fav['avg_r']}, PF = {e_fav['profit_factor']} "
             f"(vs ungated avg R = {e_all['avg_r']}, PF = {e_all['profit_factor']}).")
    L.append(f"- Stability: favorable regime positive in {fav_pos}/{args.buckets} calendar buckets.")
    L.append(f"- Reproducibility: positive on {pos_syms} of {df['symbol'].nunique()} pairs.")
    if after_cost_positive and stable and reproducible:
        L.append("- **GATE 1 status: PASS direction** — edge is regime-CONDITIONAL; gating works. Proceed to Phase 2 (liquidity-targeted exits + selection within the gate).")
    elif after_cost_positive and (stable or reproducible):
        L.append("- **GATE 1 status: PARTIAL** — gating lifts the edge but not yet stable+reproducible; tighten the favorable definition / add liquidity-targeted exits next.")
    else:
        L.append("- **GATE 1 status: NOT YET** — the gate alone does not produce a stable after-cost edge; either the favorable regime needs a better definition or the edge is regime-fragile (escalate per plan).")
    L.append("")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "regime_report.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nWrote {out/'regime_report.md'}")


if __name__ == "__main__":
    main()
