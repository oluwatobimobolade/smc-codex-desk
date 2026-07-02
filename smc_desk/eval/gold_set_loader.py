"""Gold chart case loader for AI SMC evaluation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoldChartCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    symbol: str
    decision_time: str
    chart_images: dict[str, str]
    ohlcv_snapshot: dict[str, Any] = Field(default_factory=dict)
    human_smc_labels: dict[str, Any]
    expected_setup_grade: str | None = None
    expected_state: str
    expected_direction: Literal["bullish", "bearish", "neutral", "mixed"]
    expected_poi: dict[str, Any] | None = None
    expected_invalidation: dict[str, Any] | None = None
    expected_target: dict[str, Any] | None = None
    outcome_after_x_candles: dict[str, Any] | None = None
    adjudication_status: Literal["adjudicated", "pending", "rejected"] = "adjudicated"

    @model_validator(mode="after")
    def _requires_human_labels(self) -> "GoldChartCase":
        if not self.human_smc_labels:
            raise ValueError("Gold chart case requires human_smc_labels.")
        if self.adjudication_status != "adjudicated":
            raise ValueError("Gold chart case must be adjudicated before evaluation.")
        for timeframe in ("1d", "4h", "1h", "15m"):
            if timeframe not in self.chart_images:
                raise ValueError(f"Gold chart case missing {timeframe} chart image.")
        return self


def load_gold_chart_cases(path: str | Path, *, minimum_cases: int = 1) -> list[GoldChartCase]:
    root = Path(path).expanduser().resolve()
    if root.is_file():
        files = [root]
    else:
        files = sorted(root.glob("*.json"))
    cases: list[GoldChartCase] = []
    for file_path in files:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            cases.extend(GoldChartCase.model_validate(item) for item in payload)
        else:
            cases.append(GoldChartCase.model_validate(payload))
    if len(cases) < minimum_cases:
        raise ValueError(f"Gold set has {len(cases)} adjudicated cases; minimum required is {minimum_cases}.")
    return cases
