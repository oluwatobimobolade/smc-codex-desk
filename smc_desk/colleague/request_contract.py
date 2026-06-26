from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = ROOT / "data" / "ohlcv" / "binance_futures"
DEFAULT_ANALYSIS_RUNS_ROOT = ROOT / "analysis_runs"
DEFAULT_CHART_BARS = {"15m": 220, "1h": 240, "4h": 180, "1d": 180}
TIMEFRAME_ORDER = ("15m", "1h", "4h", "1d")


def normalize_symbol(value: str) -> str:
    raw = value.strip().upper().replace("/", "").replace("-", "")
    if raw.endswith("USD") and not raw.endswith("USDT"):
        return raw[:-3] + "USDT"
    return raw


def default_ohlcv_path(symbol: str, data_root: Path = DEFAULT_DATA_ROOT, tag: str = "4year") -> Path:
    normalized = normalize_symbol(symbol)
    return data_root / normalized / f"{normalized}_15m_{tag}.csv"


class ColleagueRunRequest(BaseModel):
    """Input contract for one Market Colleague analysis package."""

    symbol: str
    source_path: str
    output_dir: str | None = None
    decision_time: str | None = None
    rules_path: str | None = None
    bias: Literal["bullish", "bearish"] | None = None
    tradingview_manifest: str | None = None
    market_truth_manifest: str | None = None
    holdout_policy: str | None = None
    allow_holdout: bool = False
    chart_bars: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_CHART_BARS))
    run_id: str | None = None
    include_legacy_comparison: bool = True
    render_charts: bool = True
    outcome_horizon_bars: int = 96
    storage_format: Literal["csv"] = "csv"

    @property
    def normalized_symbol(self) -> str:
        return normalize_symbol(self.symbol)

    @property
    def resolved_source_path(self) -> Path:
        return Path(self.source_path).expanduser().resolve()

    def resolved_output_dir(self, decision_tag: str) -> Path:
        if self.output_dir:
            return Path(self.output_dir).expanduser().resolve()
        run_id = self.run_id or f"{self.normalized_symbol}_{decision_tag}_colleague"
        return DEFAULT_ANALYSIS_RUNS_ROOT / run_id
