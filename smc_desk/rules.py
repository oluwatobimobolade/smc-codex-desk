from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "strategies" / "smc" / "default_rules.json"


class RuleConfig(BaseModel):
    pivot_window: int = Field(default=3, ge=2)
    internal_pivot_window: int | None = Field(default=None, ge=2)
    swing_pivot_window: int | None = Field(default=None, ge=2)
    equal_level_tolerance_pct: float = Field(default=0.0015, gt=0)
    equal_level_min_touches: int = Field(default=2, ge=2)
    fvg_min_gap_pct: float = Field(default=0.0005, gt=0)
    fvg_min_displacement_factor: float = Field(default=1.05, gt=0)
    displacement_body_factor: float = Field(default=1.3, gt=0)
    structure_break_min_pct: float = Field(default=0.0004, gt=0)
    ob_lookback: int = Field(default=8, ge=3)
    ob_min_body_factor: float = Field(default=0.75, gt=0)
    liquidity_sweep_lookback: int = Field(default=80, ge=10)
    confirmation_lookback: int = Field(default=24, ge=3)
    max_zone_age_bars: int = Field(default=160, ge=10)
    poi_proximity_atr: float = Field(default=2.0, gt=0)
    htf_poi_watch_distance_atr: float = Field(default=1.5, gt=0)
    htf_approach_lookback_bars: int = Field(default=4, ge=1)
    lookback_bars: int = Field(default=250, ge=50)
    risk_reward_floor: float = Field(default=3.0, gt=0.5)
    atr_lookback: int = Field(default=14, ge=2)
    structural_stop_margin_pct: float = Field(default=0.001, ge=0)
    stop_buffer_atr_mult: float = Field(default=0.75, ge=0)
    min_poi_width_pct: float = Field(default=0.0, ge=0)
    require_fresh_poi: bool = True
    allowed_poi_kinds: list[str] | None = None
    vision_authority_mode: str = Field(default="observe_only")



def load_rule_config(path: str | None = None) -> RuleConfig:
    rules_path = Path(path) if path else DEFAULT_RULES_PATH
    with rules_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return RuleConfig(**payload)
