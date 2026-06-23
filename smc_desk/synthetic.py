"""Synthetic SMC primitives with KNOWN ground truth, for perception-accuracy testing.

Every builder constructs an OHLCV frame containing exactly one canonical primitive,
placed deterministically, so we can measure whether the engine's detectors identify
it correctly. Moves are expressed in PERCENT of price, so the same construction works
at any scale (XRP ~0.5, BTC ~60000) — that doubles as a scale-invariance test.

Each builder returns (df, truth) where truth = {"kind", "direction"} (or kind="none"
for the chop negative control). Builders are parameterized by (base_price, seed) so
the benchmark can generate many variants and report a robust accuracy %.
"""
from __future__ import annotations

import random

import pandas as pd


def _df(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=len(rows), freq="15min")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.insert(0, "timestamp", ts)
    df["volume"] = 1000.0
    return df


def _cdl(o: float, c: float, up_w: float = 0.0, dn_w: float = 0.0) -> tuple[float, float, float, float]:
    """Candle from open/close with wick extensions as fractions of price."""
    hi = max(o, c) * (1.0 + up_w)
    lo = min(o, c) * (1.0 - dn_w)
    return (o, hi, lo, c)


def _baseline(p: float, k: int, seed: int, step_pct: float = 0.0010) -> tuple[list, float]:
    """Quiet, small-bodied candles that establish an avg body/range without big breaks."""
    r = random.Random(seed)
    rows = []
    for _ in range(k):
        o = p
        c = p * (1.0 + step_pct * r.uniform(-1.0, 1.0))
        w = p * step_pct * 0.4
        hi = max(o, c) + w * r.uniform(0.3, 1.0)
        lo = min(o, c) - w * r.uniform(0.3, 1.0)
        rows.append((o, hi, lo, c))
        p = c
    return rows, p


# ---------- Market structure ----------
def bos_bull(base_price=100.0, seed=0):
    rows, p = _baseline(base_price, 16, seed)
    peak = p * 1.012
    rows.append(_cdl(p, p * 1.004, up_w=0.0005)); p *= 1.004
    rows.append(_cdl(p, peak, up_w=0.0008)); p = peak          # swing-high candle (the protected high)
    for f in (0.998, 0.996, 0.995, 0.990):                     # pullback; LAST (biggest) down candle = the canonical order block
        rows.append(_cdl(p, peak * f, up_w=0.0004, dn_w=0.0004)); p = peak * f
    rows.append(_cdl(p, peak * 1.02, up_w=0.001, dn_w=0.001))  # displacement close ABOVE the swing high -> BOS
    p = peak * 1.02
    rows.append(_cdl(p, p * 0.998)); rows.append(_cdl(p * 0.998, p * 0.997))
    return _df(rows), {"kind": "BOS", "direction": "bullish"}


def bos_bear(base_price=100.0, seed=0):
    rows, p = _baseline(base_price, 16, seed)
    trough = p * 0.988
    rows.append(_cdl(p, p * 0.996, dn_w=0.0005)); p *= 0.996
    rows.append(_cdl(p, trough, dn_w=0.0008)); p = trough      # swing-low candle
    for f in (1.002, 1.004, 1.005, 1.010):                     # pullback; LAST (biggest) up candle = the canonical order block
        rows.append(_cdl(p, trough * f, up_w=0.0004, dn_w=0.0004)); p = trough * f
    rows.append(_cdl(p, trough * 0.98, up_w=0.001, dn_w=0.001))  # displacement close BELOW the swing low -> BOS
    p = trough * 0.98
    rows.append(_cdl(p, p * 1.002)); rows.append(_cdl(p * 1.002, p * 1.003))
    return _df(rows), {"kind": "BOS", "direction": "bearish"}


def choch_bear(base_price=100.0, seed=0):
    # Establish a bullish trend (BOS up), then break the protected low -> CHoCH bearish.
    df_bull, _ = bos_bull(base_price, seed)
    rows = list(df_bull[["open", "high", "low", "close"]].itertuples(index=False, name=None))
    p = rows[-1][3]
    lo_ref = min(r[2] for r in rows[-7:])                      # recent protected low region
    rows.append(_cdl(p, p * 1.006, up_w=0.0008)); p *= 1.006   # lower-high push up
    rows.append(_cdl(p, lo_ref * 0.985, up_w=0.001, dn_w=0.001))  # strong drop closing below protected low
    p = lo_ref * 0.985
    rows.append(_cdl(p, p * 1.002)); rows.append(_cdl(p * 1.002, p * 1.001))
    return _df(rows), {"kind": "CHoCH", "direction": "bearish"}


def choch_bull(base_price=100.0, seed=0):
    df_bear, _ = bos_bear(base_price, seed)
    rows = list(df_bear[["open", "high", "low", "close"]].itertuples(index=False, name=None))
    p = rows[-1][3]
    hi_ref = max(r[1] for r in rows[-7:])
    rows.append(_cdl(p, p * 0.994, dn_w=0.0008)); p *= 0.994   # higher-low push down
    rows.append(_cdl(p, hi_ref * 1.015, up_w=0.001, dn_w=0.001))  # strong rally closing above protected high
    p = hi_ref * 1.015
    rows.append(_cdl(p, p * 0.998)); rows.append(_cdl(p * 0.998, p * 0.999))
    return _df(rows), {"kind": "CHoCH", "direction": "bullish"}


# ---------- Imbalance (FVG) ----------
def fvg_bull(base_price=100.0, seed=0):
    rows, p = _baseline(base_price, 16, seed)
    c1_hi = p * 1.0015
    rows.append(_cdl(p, p * 1.001, up_w=0.0005))               # c1
    p2o = p * 1.001
    rows.append(_cdl(p2o, p2o * 1.018, up_w=0.0006))           # c2 impulse (big body)
    p = p2o * 1.018
    rows.append(_cdl(p * 1.001, p * 1.004, dn_w=0.0))          # c3: low stays ABOVE c1 high -> gap
    # ensure c3.low > c1.high
    o, hi, lo, c = rows[-1]
    if lo <= c1_hi:
        lo = c1_hi * 1.003
        rows[-1] = (o, hi, lo, c)
    rows.append(_cdl(c, c * 1.001)); rows.append(_cdl(c * 1.001, c * 1.0005))
    return _df(rows), {"kind": "fvg", "direction": "bullish"}


def fvg_bear(base_price=100.0, seed=0):
    rows, p = _baseline(base_price, 16, seed)
    c1_lo = p * 0.9985
    rows.append(_cdl(p, p * 0.999, dn_w=0.0005))               # c1
    p2o = p * 0.999
    rows.append(_cdl(p2o, p2o * 0.982, dn_w=0.0006))           # c2 impulse down
    p = p2o * 0.982
    rows.append(_cdl(p * 0.999, p * 0.996, up_w=0.0))          # c3: high stays BELOW c1 low -> gap
    o, hi, lo, c = rows[-1]
    if hi >= c1_lo:
        hi = c1_lo * 0.997
        rows[-1] = (o, hi, lo, c)
    rows.append(_cdl(c, c * 0.999)); rows.append(_cdl(c * 0.999, c * 0.9995))
    return _df(rows), {"kind": "fvg", "direction": "bearish"}


# ---------- Liquidity sweeps ----------
def sweep_high(base_price=100.0, seed=0):
    rows, p = _baseline(base_price, 14, seed)
    level = p * 1.010
    rows.append(_cdl(p, p * 1.004, up_w=0.0004)); p *= 1.004
    rows.append(_cdl(p, level, up_w=0.0006)); p = level        # swing high == level
    for f in (0.996, 0.993, 0.992):
        rows.append(_cdl(p, level * f, dn_w=0.0004)); p = level * f
    # sweep candle: wick ABOVE level, close back BELOW
    rows.append((level * 0.999, level * 1.003, level * 0.997, level * 0.996)); p = level * 0.996
    rows.append(_cdl(p, p * 0.999)); rows.append(_cdl(p * 0.999, p * 0.998))
    return _df(rows), {"kind": "Liquidity Sweep", "direction": "bearish"}


def sweep_low(base_price=100.0, seed=0):
    rows, p = _baseline(base_price, 14, seed)
    level = p * 0.990
    rows.append(_cdl(p, p * 0.996, dn_w=0.0004)); p *= 0.996
    rows.append(_cdl(p, level, dn_w=0.0006)); p = level
    for f in (1.004, 1.007, 1.008):
        rows.append(_cdl(p, level * f, up_w=0.0004)); p = level * f
    rows.append((level * 1.001, level * 1.003, level * 0.997, level * 1.004)); p = level * 1.004
    rows.append(_cdl(p, p * 1.001)); rows.append(_cdl(p * 1.001, p * 1.002))
    return _df(rows), {"kind": "Liquidity Sweep", "direction": "bullish"}


# ---------- Order block (rides on a BOS) ----------
def ob_bull(base_price=100.0, seed=0):
    df, _ = bos_bull(base_price, seed)
    return df, {"kind": "order_block", "direction": "bullish"}


def ob_bear(base_price=100.0, seed=0):
    df, _ = bos_bear(base_price, seed)
    return df, {"kind": "order_block", "direction": "bearish"}


# ---------- Equal highs / lows (clustered liquidity) ----------
def equal_highs(base_price=100.0, seed=0):
    rows, p = _baseline(base_price, 12, seed)
    level = p * 1.010
    rows.append(_cdl(p, p * 1.005, up_w=0.0004)); p *= 1.005
    rows.append(_cdl(p, level, up_w=0.0006)); p = level                       # peak 1
    for f in (0.995, 0.992, 0.994):
        rows.append(_cdl(p, level * f, dn_w=0.0004)); p = level * f
    rows.append(_cdl(p, level * 0.9999, up_w=0.0006)); p = level * 0.9999     # peak 2 ~ same level
    for f in (0.995, 0.992, 0.993):
        rows.append(_cdl(p, level * f, dn_w=0.0004)); p = level * f
    return _df(rows), {"kind": "Equal Highs", "direction": "bearish"}


def equal_lows(base_price=100.0, seed=0):
    rows, p = _baseline(base_price, 12, seed)
    level = p * 0.990
    rows.append(_cdl(p, p * 0.995, dn_w=0.0004)); p *= 0.995
    rows.append(_cdl(p, level, dn_w=0.0006)); p = level
    for f in (1.005, 1.008, 1.006):
        rows.append(_cdl(p, level * f, up_w=0.0004)); p = level * f
    rows.append(_cdl(p, level * 1.0001, dn_w=0.0006)); p = level * 1.0001
    for f in (1.005, 1.008, 1.007):
        rows.append(_cdl(p, level * f, up_w=0.0004)); p = level * f
    return _df(rows), {"kind": "Equal Lows", "direction": "bullish"}


# ---------- Negative control ----------
def chop(base_price=100.0, seed=0):
    rows, _ = _baseline(base_price, 40, seed, step_pct=0.0008)
    return _df(rows), {"kind": "none", "direction": "none"}


BUILDERS = {
    "BOS_bull": bos_bull, "BOS_bear": bos_bear,
    "CHoCH_bull": choch_bull, "CHoCH_bear": choch_bear,
    "FVG_bull": fvg_bull, "FVG_bear": fvg_bear,
    "Sweep_high": sweep_high, "Sweep_low": sweep_low,
    "OB_bull": ob_bull, "OB_bear": ob_bear,
    "EqualHighs": equal_highs, "EqualLows": equal_lows,
    "Chop": chop,
}
