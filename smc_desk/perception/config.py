"""Detector-only runtime configuration for PerceptionEngineV2.

This is the canonical perception configuration surface.  It deliberately
cannot express entry, target, stop, risk, or trade-promotion settings.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


SPECS_ROOT = Path(__file__).resolve().parents[2] / "specs"
DEFAULT_DETECTOR_CONFIG_PATH = SPECS_ROOT / "PERCEPTION_DETECTOR_CONFIG_V2.yaml"


class SwingScales(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    local: int = Field(ge=1)
    internal: int = Field(ge=2)
    external: int = Field(ge=2)


class FVGDetectorRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    minimum_gap_bps: float = Field(gt=0)
    displacement_factor: float = Field(gt=0)


class BreakConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    wick_cross_creates_candidate: bool
    body_close_confirms: bool
    displacement_required: bool


class PerceptionRuntimeConfig(BaseModel):
    """Flattened detector parameters consumed by PerceptionEngineV2."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    runtime_config_source: str = "perception_detector_config_v2"
    detector_config_id: str
    ontology_version: str
    swing_scales: SwingScales
    break_confirmation: BreakConfirmation
    fvg: FVGDetectorRuntimeConfig
    equal_level_tolerance_bps: float = Field(ge=0)
    equal_level_min_touches: int = Field(ge=2)
    displacement_body_factor: float = Field(gt=0)
    structure_break_min_bps: float = Field(ge=0)
    ob_lookback: int = Field(ge=3)
    ob_min_body_factor: float = Field(gt=0)
    liquidity_sweep_lookback: int = Field(ge=10)
    lookback_bars: int = Field(ge=50)
    atr_lookback: int = Field(ge=2)

    @model_validator(mode="after")
    def _no_strategy_fields(self) -> "PerceptionRuntimeConfig":
        forbidden = {
            "risk_reward_floor",
            "structural_stop_margin_bps",
            "stop_buffer_atr_mult",
            "require_fresh_poi",
            "allowed_poi_kinds",
            "capital_risk",
        }
        leaked = forbidden.intersection(self.model_fields_set)
        if leaked:
            raise ValueError(f"Strategy fields leaked into perception config: {sorted(leaked)}")
        return self


def load_perception_config(
    path: str | Path | None = None,
) -> PerceptionRuntimeConfig:
    config_path = Path(path) if path is not None else DEFAULT_DETECTOR_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Perception config at {config_path} must be an object.")
    if payload.get("config_id") != "PERCEPTION_DETECTOR_CONFIG_V2":
        raise ValueError(
            "PerceptionEngineV2 accepts only PERCEPTION_DETECTOR_CONFIG_V2; "
            "strategy or monolithic rule files are forbidden."
        )
    _assert_forbidden_keys_absent(payload)
    return PerceptionRuntimeConfig(
        detector_config_id=str(payload["config_id"]),
        ontology_version=str(payload["ontology_version"]),
        swing_scales=payload["structural_scales"]["swing_scales"],
        break_confirmation=payload["structure_breaks"]["break_confirmation"],
        fvg={
            "minimum_gap_bps": payload["fair_value_gaps"]["minimum_gap_bps"],
            "displacement_factor": payload["fair_value_gaps"]["displacement_factor"],
        },
        equal_level_tolerance_bps=payload["geometry_and_tolerances"]["equal_level_tolerance_bps"],
        equal_level_min_touches=payload["geometry_and_tolerances"]["equal_level_min_touches"],
        displacement_body_factor=payload["structure_breaks"]["displacement_body_factor"],
        structure_break_min_bps=payload["structure_breaks"]["structure_break_min_bps"],
        ob_lookback=payload["order_blocks"]["ob_lookback"],
        ob_min_body_factor=payload["order_blocks"]["ob_min_body_factor"],
        liquidity_sweep_lookback=payload["sweeps"]["liquidity_sweep_lookback"],
        lookback_bars=payload["detector_limits"]["lookback_bars"],
        atr_lookback=payload["detector_limits"]["atr_lookback"],
    )


def detector_config_metadata(path: str | Path | None = None) -> dict[str, Any]:
    config = load_perception_config(path)
    return {
        "config_id": config.detector_config_id,
        "ontology_version": config.ontology_version,
        "runtime_config_source": config.runtime_config_source,
        "strategy_fields_present": False,
    }


def _assert_forbidden_keys_absent(payload: dict[str, Any]) -> None:
    forbidden = set(payload.get("forbidden_in_this_file", [])) | {
        "risk_reward_floor",
        "structural_stop_margin_bps",
        "stop_buffer_atr_mult",
        "require_fresh_poi",
        "allowed_poi_kinds",
        "capital_risk",
    }

    def walk(value: Any, path: str = "") -> list[str]:
        found: list[str] = []
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key in forbidden and key != "forbidden_in_this_file":
                    found.append(child_path)
                found.extend(walk(child, child_path))
        elif isinstance(value, list) and path != "forbidden_in_this_file":
            for index, child in enumerate(value):
                found.extend(walk(child, f"{path}[{index}]"))
        return found

    leaked = walk(payload)
    if leaked:
        raise ValueError(f"Strategy authority leaked into detector config: {leaked}")
