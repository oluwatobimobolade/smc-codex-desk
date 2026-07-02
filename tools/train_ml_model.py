#!/usr/bin/env python3
"""Train + honestly validate an ML setup-scorer on engine research rows.

Discipline (this is what makes it trustworthy, not the model):
- Train only on TRIGGERED setups (the ones that filled and have a real outcome).
- Label = win (realized R > 0). Forward-only; features are all decision-time.
- Time split: train < holdout_start <= holdout. Holdout touched once.
- The selection THRESHOLD is chosen on TRAIN only (max train expectancy with a
  minimum selected fraction), never on the holdout.
- Report: model-selected vs baseline expectancy on the holdout, PER SYMBOL, with
  a cost haircut, plus an expanding-window WALK-FORWARD for stability.
- Symbol is NOT a feature (we want a cross-pair edge, not pair memorization).

Usage:
  python3 tools/train_ml_model.py --research backtests/research/*_open.csv \
      --holdout-start 2025-06-20 --output-dir backtests/ml/run1
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

from smc_desk.ml_model import XGBoostClassifier, StandardScaler, expectancy, save_model

NUMERIC = ["confluence_score", "poi_score", "poi_width_pct", "planned_rr", "htf_agreement_ratio",
           # enriched continuous features (present in the 54-col harvest; absent ones are skipped)
           "poi_age_bars", "poi_competing_count", "displacement_score", "atr_pct", "adx_at_decision",
           "premium_discount_ratio", "sweep_depth_atr", "structure_event_density",
           "body_ratio_at_decision", "range_pct_at_decision", "minute_of_session",
           "dist_htf_atr", "dist_htf_r", "atr_pct_rank", "adx_pct_rank"]
BOOLS = ["htf_aligned", "is_killzone", "chk_directional_bias", "chk_fresh_or_partial_poi",
         "chk_premium_discount_aligned", "chk_liquidity_sweep", "chk_displacement_break",
         "chk_sweep_before_break", "chk_price_at_or_near_poi", "chk_stop_has_volatility_buffer",
         "chk_risk_reward_floor"]
CATEG = ["session", "direction", "poi_kind", "poi_status", "setup_grade", "htf_alignment", "break_strength", "regime_label", "vol_band_label"]
# Never features: ids, absolute prices, and forward-looking / label columns.
LEAK = {"symbol", "decision_index", "decision_time", "poi_low", "poi_high", "entry_index",
        "triggered", "outcome", "r_multiple", "mfe_r", "mae_r", "verdict"}


def _tf(s):
    return s.astype(str).str.strip().str.lower().map({"true": 1.0, "false": 0.0}).fillna(0.0)


def build_features(df: pd.DataFrame):
    num_cols = [c for c in NUMERIC if c in df.columns]
    num = df[num_cols].apply(pd.to_numeric, errors="coerce")
    num = num.fillna(num.median(numeric_only=True)).fillna(0.0)
    bo = pd.DataFrame({c: _tf(df[c]) for c in BOOLS if c in df.columns})
    cat_cols = [c for c in CATEG if c in df.columns]
    cats = pd.get_dummies(df[cat_cols].astype(str), prefix=cat_cols).astype(float)
    X = pd.concat([num, bo, cats], axis=1)
    return X.values.astype(float), list(X.columns)


def select_threshold(proba, r, min_frac=0.15):
    best = (-9.9, float(np.min(proba)))
    for q in np.linspace(0.0, 0.92, 24):
        thr = float(np.quantile(proba, q))
        sel = proba >= thr
        if sel.mean() < min_frac or sel.sum() < 12:
            continue
        e = expectancy(r[sel])
        score = e["avg_r"] if e["avg_r"] is not None else -9.9
        if score > best[0]:
            best = (score, thr)
    return best[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--research", nargs="+", required=True)
    p.add_argument("--holdout-start", default="2025-06-20")
    p.add_argument("--min-select-frac", type=float, default=0.15)
    p.add_argument("--extra-cost-r", type=float, default=0.10, help="Fallback per-trade R haircut when exact-cost columns are absent.")
    p.add_argument("--target-cost-bps", type=float, default=10.0, help="Recompute realized R at this round-trip cost (bps) using logged entry/stop.")
    p.add_argument("--n-estimators", type=int, default=150)
    p.add_argument("--max-depth", type=int, default=3)
    p.add_argument("--learning-rate", type=float, default=0.05)
    p.add_argument("--output-dir", default="backtests/ml/run")
    p.add_argument("--require-regime", help="Strictly filter for a specific regime_label (e.g. trend_aligned)")
    args = p.parse_args()

    paths = []
    for pat in args.research:
        paths += [Path(x) for x in sorted(Path().glob(pat))] if any(c in pat for c in "*?[") else [Path(pat)]
    df = pd.concat([pd.read_csv(x) for x in paths], ignore_index=True)
    df = df[_tf(df["triggered"]) == 1.0].copy()
    df["r_multiple"] = pd.to_numeric(df["r_multiple"], errors="coerce")
    df = df.dropna(subset=["r_multiple"]).reset_index(drop=True)
    df["t"] = pd.to_datetime(df["decision_time"], utc=True, errors="coerce")
    df = df.dropna(subset=["t"]).sort_values("t").reset_index(drop=True)

    if args.require_regime:
        if "regime_label" in df.columns:
            n_before = len(df)
            df = df[df["regime_label"] == args.require_regime].copy()
            print(f"Filtered to regime '{args.require_regime}': {len(df)} rows remain (from {n_before}).")
        else:
            print("WARNING: --require-regime provided but 'regime_label' not in columns. Skipping filter.")

    X, feat_names = build_features(df)
    y = (df["r_multiple"].values > 0.0).astype(float)
    r = df["r_multiple"].values.astype(float)
    # Honest after-cost R: exact recompute at target bps when the harvester logged
    # entry/stop; otherwise a flat haircut fallback. r_cost is the number that matters.
    if {"entry_price", "risk_per_r", "cost_bps"}.issubset(df.columns):
        ep = pd.to_numeric(df["entry_price"], errors="coerce").values
        rk = pd.to_numeric(df["risk_per_r"], errors="coerce").values
        cb = pd.to_numeric(df["cost_bps"], errors="coerce").values
        with np.errstate(divide="ignore", invalid="ignore"):
            adj = (ep / rk) * (cb - args.target_cost_bps) / 10000.0
        adj = np.where(np.isfinite(adj) & (rk > 0), adj, -args.extra_cost_r)
        r_cost = r + adj
        cost_label = f"after {args.target_cost_bps:g}bps (exact)"
    else:
        r_cost = r - args.extra_cost_r
        cost_label = f"after {args.extra_cost_r}R haircut"
    sym = df["symbol"].astype(str).values
    t = df["t"].values
    hold_start = pd.Timestamp(args.holdout_start, tz="UTC")
    tr = (df["t"] < hold_start).values
    ho = ~tr

    lines = ["# ML Setup-Scorer — Honest Validation Report", ""]
    lines.append(f"Rows (triggered): {len(df)}  ·  features: {len(feat_names)}  ·  symbols: {sorted(set(sym))}")
    lines.append(f"Train: {int(tr.sum())}  ·  Holdout (>= {args.holdout_start}): {int(ho.sum())}")
    lines.append(f"Base win rate train/holdout: {y[tr].mean():.3f} / {y[ho].mean() if ho.sum() else float('nan'):.3f}")
    lines.append("")

    if tr.sum() < 50 or ho.sum() < 20:
        lines.append("**Insufficient data for a trustworthy time-split (need >=50 train, >=20 holdout).**")
        out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
        (out / "ml_report.md").write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines)); return

    scaler = StandardScaler().fit(X[tr])
    Xs = scaler.transform(X)
    model = XGBoostClassifier(
        n_estimators=args.n_estimators, max_depth=args.max_depth, learning_rate=args.learning_rate
    ).fit(Xs[tr], y[tr])
    proba = model.predict_proba(Xs)
    thr = select_threshold(proba[tr], r_cost[tr], args.min_select_frac)

    # ---- Holdout: baseline (take all) vs model-selected, all AFTER COST ----
    sel_ho = ho & (proba >= thr)
    base = expectancy(r_cost[ho])
    selm = expectancy(r_cost[sel_ho])
    selm_gross = expectancy(r[sel_ho])
    lines += [f"## Holdout: baseline vs model-selected ({cost_label})", "",
              "| set | n | win% | avg R | total R | PF |", "|---|--:|--:|--:|--:|--:|",
              f"| baseline (take all) | {base['n']} | {base['win_rate']} | {base['avg_r']} | {base['total_r']} | {base['profit_factor']} |",
              f"| model-selected (p>={thr:.3f}) | {selm['n']} | {selm['win_rate']} | {selm['avg_r']} | {selm['total_r']} | {selm['profit_factor']} |",
              f"| model-selected (gross, logged cost) | {selm_gross['n']} | {selm_gross['win_rate']} | {selm_gross['avg_r']} | {selm_gross['total_r']} | {selm_gross['profit_factor']} |",
              ""]
    lines += [f"### Model-selected holdout, per symbol ({cost_label})", "", "| symbol | n | win% | avg R | PF |", "|---|--:|--:|--:|--:|"]
    for s in sorted(set(sym[sel_ho])):
        e = expectancy(r_cost[sel_ho & (sym == s)])
        lines.append(f"| {s} | {e['n']} | {e['win_rate']} | {e['avg_r']} | {e['profit_factor']} |")
    lines.append("")

    # ---- Walk-forward (expanding window), the real stability test ----
    order = np.argsort(t)
    K = 6
    n = len(order)
    start = int(n * 0.4)
    bounds = np.linspace(start, n, K + 1).astype(int)
    wf = []
    for i in range(K):
        a, b = bounds[i], bounds[i + 1]
        if b - a < 15 or a < 40:
            continue
        tr_idx = order[:a]; te_idx = order[a:b]
        sc = StandardScaler().fit(X[tr_idx]); Xss = sc.transform(X)
        m = XGBoostClassifier(
            n_estimators=args.n_estimators, max_depth=args.max_depth, learning_rate=args.learning_rate
        ).fit(Xss[tr_idx], y[tr_idx])
        pr = m.predict_proba(Xss)
        th = select_threshold(pr[tr_idx], r_cost[tr_idx], args.min_select_frac)
        sel = te_idx[pr[te_idx] >= th]
        e = expectancy(r_cost[sel])
        wf.append((e["n"], e["avg_r"]))
    pos = sum(1 for _, a in wf if a is not None and a > 0)
    avgs = [a for _, a in wf if a is not None]
    lines += ["## Walk-forward (expanding window) — out-of-sample stability", "",
              "| fold | selected n | avg R |", "|--:|--:|--:|"]
    for i, (nn, aa) in enumerate(wf, 1):
        lines.append(f"| {i} | {nn} | {aa} |")
    lines += ["", f"**Folds positive: {pos}/{len(wf)}  ·  mean OOS selected avg R: {round(float(np.mean(avgs)),4) if avgs else 'n/a'}**", ""]

    # ---- Top features ----
    importances = np.zeros(len(feat_names))
    if hasattr(model.model, "get_score"):
        scores = model.model.get_score(importance_type="gain")
        for k, v in scores.items():
            try:
                idx = int(k.replace("f", ""))
                importances[idx] = v
            except ValueError:
                pass
    idx_top = np.argsort(importances)[::-1][:12]
    lines += ["## Most influential features (XGBoost Gain)", "", "| feature | gain |", "|---|--:|"]
    for j in idx_top:
        lines.append(f"| {feat_names[j]} | {importances[j]:.3f} |")
    lines += ["", "> Honest read: the model is only worth using if **model-selected holdout avg R (after the cost haircut) beats baseline AND walk-forward is positive in most folds**. Otherwise it is fitting noise/regime and should not gate live trades."]

    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "ml_report.md").write_text("\n".join(lines), encoding="utf-8")
    save_model(out / "model.json", model, scaler, feat_names, thr,
               meta={"holdout_start": args.holdout_start, "rows": len(df), "symbols": sorted(set(sym.tolist()))})
    print("\n".join(lines))
    print(f"\nWrote {out/'ml_report.md'} and {out/'model.json'}")


if __name__ == "__main__":
    main()
