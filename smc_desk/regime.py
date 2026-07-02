"""Regime classification for SMC setups.

Implements the Master Research Plan's central empirical fork (E2): is the SMC
edge **regime-conditional** (real in trend/aligned markets, gone in chop -> we can
gate it) or **regime-fragile** (the favorable regime itself drifts unpredictably ->
no fixed gate works)? The answer decides whether consistency is even reachable.

Regime is defined from **market-agnostic, normalized** inputs so the *same*
definition applies to BTC, gold, or EURUSD (the reproducibility requirement in
the charter):
  - ``adx``           trend strength, 0-100, already scale-free.
  - ``htf_aligned``   does the setup direction agree with the multi-timeframe bias.
  - ``atr_pct_rank``  where current volatility sits in THIS market's own recent
                      distribution (0..1), so it self-normalizes across instruments.

No look-ahead: every input is computed from data at/<= the decision bar. In live
use, ``atr_pct_rank`` must come from a *trailing* window, never the full history.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass

# Regime labels
TREND_ALIGNED = "trend_aligned"     # strong trend AND setup agrees with HTF bias  (thesis: best)
TREND_COUNTER = "trend_counter"     # strong trend but setup fights HTF bias        (thesis: worst)
CHOP = "chop"                       # no trend / ranging                            (thesis: noise)
TRANSITIONAL = "transitional"       # in-between trend strength

# Volatility bands (from atr_pct_rank)
VOL_LOW = "low"
VOL_MID = "mid"
VOL_HIGH = "high"


@dataclass(frozen=True)
class RegimeConfig:
    adx_trend_min: float = 25.0     # ADX at/above this = trending
    adx_chop_max: float = 18.0      # ADX at/below this = choppy/ranging
    vol_high_rank: float = 0.80     # atr_pct_rank at/above this = high volatility
    vol_low_rank: float = 0.20      # atr_pct_rank at/below this = low volatility


def classify(adx: float | None, htf_aligned: bool, cfg: RegimeConfig = RegimeConfig()) -> str:
    """Return the trend/alignment regime label for one decision bar."""
    if adx is None or adx != adx:  # None or NaN
        return TRANSITIONAL
    if adx >= cfg.adx_trend_min:
        return TREND_ALIGNED if htf_aligned else TREND_COUNTER
    if adx <= cfg.adx_chop_max:
        return CHOP
    return TRANSITIONAL


def vol_band(atr_pct_rank: float | None, cfg: RegimeConfig = RegimeConfig()) -> str:
    """Return the volatility band from the self-normalized ATR percentile rank."""
    if atr_pct_rank is None or atr_pct_rank != atr_pct_rank:
        return VOL_MID
    if atr_pct_rank >= cfg.vol_high_rank:
        return VOL_HIGH
    if atr_pct_rank <= cfg.vol_low_rank:
        return VOL_LOW
    return VOL_MID


def is_favorable(regime: str) -> bool:
    """The thesis 'good' regime: strong trend, setup aligned with HTF bias."""
    return regime == TREND_ALIGNED


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ATR (Average True Range) for volatility normalization."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ADX (Average Directional Index) for trend strength."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    return adx


def compute_regime_series(df: pd.DataFrame, period: int = 14, lookback: int = 500) -> pd.DataFrame:
    """
    Compute rolling ATR, ADX, and their rolling percentile ranks.
    atr_pct_rank is computed using a rolling rank over `lookback` periods.
    """
    if df.empty:
        return pd.DataFrame(columns=["atr", "adx", "atr_pct_rank", "adx_pct_rank"])

    atr = compute_atr(df, period=period)
    adx = compute_adx(df, period=period)

    # Pandas rolling.rank(pct=True) calculates the percentile rank in [0, 1]
    atr_pct_rank = atr.rolling(window=lookback, min_periods=period).rank(pct=True)
    adx_pct_rank = adx.rolling(window=lookback, min_periods=period).rank(pct=True)

    return pd.DataFrame({
        "atr": atr,
        "adx": adx,
        "atr_pct_rank": atr_pct_rank,
        "adx_pct_rank": adx_pct_rank
    })
