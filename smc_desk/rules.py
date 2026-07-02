from __future__ import annotations

from copy import deepcopy
import yaml
from pathlib import Path

from pydantic import BaseModel, Field, ConfigDict


SPECS_ROOT = Path(__file__).resolve().parent.parent / "specs"
LEGACY_MONOLITH_RULES_PATH = SPECS_ROOT / "PERCEPTION_ONTOLOGY_V2.yaml"
DEFAULT_DETECTOR_CONFIG_PATH = SPECS_ROOT / "PERCEPTION_DETECTOR_CONFIG_V2.yaml"
DEFAULT_STRATEGY_CONFIG_PATH = SPECS_ROOT / "STRATEGY_EXECUTION_CONFIG_V1.yaml"
DEFAULT_RULES_PATH = DEFAULT_DETECTOR_CONFIG_PATH
RUNTIME_CONFIG_SOURCE = "split_detector_strategy_configs"


class DetectorGeometryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equal_level_tolerance_bps: float = Field(gt=0)
    equal_level_min_touches: int = Field(ge=2)


class DetectorStructureBreaksConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    break_confirmation: dict
    structure_break_min_bps: float = Field(ge=0)
    displacement_body_factor: float = Field(gt=0)


class PerceptionDetectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_id: str
    status: str
    authority: str
    source_monolith: str
    ontology_version: str
    geometry_and_tolerances: DetectorGeometryConfig
    structural_scales: dict
    fair_value_gaps: dict
    structure_breaks: DetectorStructureBreaksConfig
    order_blocks: dict
    sweeps: dict
    detector_limits: dict
    forbidden_in_this_file: list[str] = Field(default_factory=list)


class StrategyExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_id: str
    status: str
    authority: str
    source_monolith: str
    strategy_profile: str
    decision_policy: str
    sequence_context: dict
    poi_and_approach: dict
    risk_management: dict
    authority_modes: dict
    promotion_policy: dict


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Rule config file not found at {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Rule config at {path} must be a mapping/object.")
    return data


def _load_split_configs(
    detector_path: Path = DEFAULT_DETECTOR_CONFIG_PATH,
    strategy_path: Path = DEFAULT_STRATEGY_CONFIG_PATH,
) -> tuple[PerceptionDetectorConfig, StrategyExecutionConfig]:
    detector = PerceptionDetectorConfig.model_validate(_load_yaml(detector_path))
    strategy = StrategyExecutionConfig.model_validate(_load_yaml(strategy_path))
    return detector, strategy


def _runtime_defaults_from_split(
    detector_path: Path = DEFAULT_DETECTOR_CONFIG_PATH,
    strategy_path: Path = DEFAULT_STRATEGY_CONFIG_PATH,
) -> dict:
    detector, strategy = _load_split_configs(detector_path, strategy_path)
    structure_breaks = detector.structure_breaks
    risk = strategy.risk_management
    return {
        "runtime_config_source": RUNTIME_CONFIG_SOURCE,
        "detector_config_id": detector.config_id,
        "strategy_config_id": strategy.config_id,
        "ontology_version": detector.ontology_version,
        "equal_level_tolerance_bps": detector.geometry_and_tolerances.equal_level_tolerance_bps,
        "equal_level_min_touches": detector.geometry_and_tolerances.equal_level_min_touches,
        "swing_scales": detector.structural_scales["swing_scales"],
        "fvg": {
            "minimum_gap_bps": detector.fair_value_gaps["minimum_gap_bps"],
            "displacement_factor": detector.fair_value_gaps["displacement_factor"],
        },
        "break_confirmation": structure_breaks.break_confirmation,
        "structure_break_min_bps": structure_breaks.structure_break_min_bps,
        "displacement_body_factor": structure_breaks.displacement_body_factor,
        "ob_lookback": detector.order_blocks["ob_lookback"],
        "ob_min_body_factor": detector.order_blocks["ob_min_body_factor"],
        "liquidity_sweep_lookback": detector.sweeps["liquidity_sweep_lookback"],
        "lookback_bars": detector.detector_limits["lookback_bars"],
        "atr_lookback": detector.detector_limits["atr_lookback"],
        "confirmation_lookback": strategy.sequence_context["confirmation_lookback"],
        "max_zone_age_bars": strategy.sequence_context["max_zone_age_bars"],
        "poi_proximity_atr": strategy.poi_and_approach["poi_proximity_atr"],
        "htf_poi_watch_distance_atr": strategy.poi_and_approach["htf_poi_watch_distance_atr"],
        "htf_approach_lookback_bars": strategy.poi_and_approach["htf_approach_lookback_bars"],
        "min_poi_width_bps": strategy.poi_and_approach["min_poi_width_bps"],
        "require_fresh_poi": strategy.poi_and_approach["require_fresh_poi"],
        "risk_reward_floor": risk["risk_reward_floor"],
        "structural_stop_margin_bps": risk["structural_stop_margin_bps"],
        "stop_buffer_atr_mult": risk["stop_buffer_atr_mult"],
        "vision_authority_mode": strategy.authority_modes["vision_authority_mode"],
    }


def _load_defaults() -> dict:
    return _runtime_defaults_from_split()


_DEFAULTS = _load_defaults()


def _req(key: str, container: dict | None = None):
    """Get a required value from the loaded ontology defaults. Raises KeyError if missing."""
    source = container if container is not None else _DEFAULTS
    if key not in source:
        raise KeyError(f"Required ontology key '{key}' missing from PERCEPTION_ONTOLOGY_V2.yaml")
    return source[key]


def _ratio_to_bps(value: float) -> float:
    """Convert a legacy ratio value, e.g. 0.0015, to basis points."""
    return float(value) * 10000.0


def _percent_to_bps(value: float) -> float:
    """Convert a legacy percent value, e.g. 0.25 for 0.25%, to basis points."""
    return float(value) * 100.0


class SwingScales(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local: int = Field(default_factory=lambda: _req("local", _DEFAULTS.get("swing_scales", {})), ge=1)
    internal: int = Field(default_factory=lambda: _req("internal", _DEFAULTS.get("swing_scales", {})), ge=2)
    external: int = Field(default_factory=lambda: _req("external", _DEFAULTS.get("swing_scales", {})), ge=2)


class FVGConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_gap_bps: float = Field(default_factory=lambda: _req("minimum_gap_bps", _DEFAULTS.get("fvg", {})), gt=0)
    displacement_factor: float = Field(default_factory=lambda: _req("displacement_factor", _DEFAULTS.get("fvg", {})), gt=0)


class BreakConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wick_cross_creates_candidate: bool = Field(default_factory=lambda: _req("wick_cross_creates_candidate", _DEFAULTS.get("break_confirmation", {})))
    body_close_confirms: bool = Field(default_factory=lambda: _req("body_close_confirms", _DEFAULTS.get("break_confirmation", {})))
    displacement_required: bool = Field(default_factory=lambda: _req("displacement_required", _DEFAULTS.get("break_confirmation", {})))


class RuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime_config_source: str = Field(default_factory=lambda: _req("runtime_config_source"))
    detector_config_id: str | None = Field(default_factory=lambda: _DEFAULTS.get("detector_config_id"))
    strategy_config_id: str | None = Field(default_factory=lambda: _DEFAULTS.get("strategy_config_id"))
    ontology_version: str = Field(default_factory=lambda: _req("ontology_version"))
    swing_scales: SwingScales = Field(default_factory=lambda: SwingScales(**_DEFAULTS["swing_scales"]))
    break_confirmation: BreakConfirmation = Field(default_factory=lambda: BreakConfirmation(**_DEFAULTS["break_confirmation"]))
    fvg: FVGConfig = Field(default_factory=lambda: FVGConfig(**_DEFAULTS["fvg"]))

    equal_level_tolerance_bps: float = Field(default_factory=lambda: _req("equal_level_tolerance_bps"), ge=0)
    equal_level_min_touches: int = Field(default_factory=lambda: _req("equal_level_min_touches"), ge=2)
    displacement_body_factor: float = Field(default_factory=lambda: _req("displacement_body_factor"), gt=0)
    structure_break_min_bps: float = Field(default_factory=lambda: _req("structure_break_min_bps"), ge=0)
    ob_lookback: int = Field(default_factory=lambda: _req("ob_lookback"), ge=3)
    ob_min_body_factor: float = Field(default_factory=lambda: _req("ob_min_body_factor"), gt=0)
    liquidity_sweep_lookback: int = Field(default_factory=lambda: _req("liquidity_sweep_lookback"), ge=10)
    confirmation_lookback: int = Field(default_factory=lambda: _req("confirmation_lookback"), ge=3)
    max_zone_age_bars: int = Field(default_factory=lambda: _req("max_zone_age_bars"), ge=10)
    poi_proximity_atr: float = Field(default_factory=lambda: _req("poi_proximity_atr"), gt=0)
    htf_poi_watch_distance_atr: float = Field(default_factory=lambda: _req("htf_poi_watch_distance_atr"), gt=0)
    htf_approach_lookback_bars: int = Field(default_factory=lambda: _req("htf_approach_lookback_bars"), ge=1)
    lookback_bars: int = Field(default_factory=lambda: _req("lookback_bars"), ge=50)
    risk_reward_floor: float = Field(default_factory=lambda: _req("risk_reward_floor"), gt=0.5)
    atr_lookback: int = Field(default_factory=lambda: _req("atr_lookback"), ge=2)
    structural_stop_margin_bps: float = Field(default_factory=lambda: _req("structural_stop_margin_bps"), ge=0)
    stop_buffer_atr_mult: float = Field(default_factory=lambda: _req("stop_buffer_atr_mult"), ge=0)
    min_poi_width_bps: float = Field(default_factory=lambda: _req("min_poi_width_bps"), ge=0)
    require_fresh_poi: bool = Field(default_factory=lambda: _req("require_fresh_poi"))
    allowed_poi_kinds: list[str] | None = None
    vision_authority_mode: str = Field(default_factory=lambda: _req("vision_authority_mode"))
    daily_session_profile: str = Field(default="exchange_daily_utc")


def _canonicalize_legacy_payload(payload: dict) -> dict:
    """Translate pre-ontology strategy JSON files into the strict V2 rule schema.

    Direct ``RuleConfig(...)`` construction remains strict and rejects legacy keys.
    This adapter exists only for persisted strategy files that older research tools
    still pass through ``load_rule_config``.
    """
    legacy_keys = {
        "pivot_window",
        "internal_pivot_window",
        "swing_pivot_window",
        "equal_level_tolerance_pct",
        "fvg_min_gap_pct",
        "fvg_min_displacement_factor",
        "structure_break_min_pct",
        "structural_stop_margin_pct",
        "min_poi_width_pct",
    }
    if not legacy_keys.intersection(payload):
        canonical = deepcopy(_DEFAULTS)
        canonical_fields = set(RuleConfig.model_fields)
        nested_fields = {"swing_scales", "break_confirmation", "fvg"}
        unknown = []
        for key, value in payload.items():
            if key in nested_fields and isinstance(value, dict):
                canonical.setdefault(key, {}).update(value)
            elif key in canonical_fields:
                canonical[key] = value
            else:
                unknown.append(key)
        if unknown:
            unknown_str = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown rule config field(s): {unknown_str}")
        canonical["runtime_config_source"] = "compatibility_rule_file"
        return canonical

    canonical = deepcopy(_DEFAULTS)
    canonical_fields = set(RuleConfig.model_fields)
    nested_fields = {"swing_scales", "break_confirmation", "fvg"}
    ignored_legacy_aliases = set()
    unknown: list[str] = []

    for key, value in payload.items():
        if key == "pivot_window":
            canonical.setdefault("swing_scales", {})["local"] = value
        elif key == "internal_pivot_window":
            canonical.setdefault("swing_scales", {})["internal"] = value
        elif key == "swing_pivot_window":
            canonical.setdefault("swing_scales", {})["external"] = value
        elif key == "equal_level_tolerance_pct":
            canonical["equal_level_tolerance_bps"] = _ratio_to_bps(value)
        elif key == "fvg_min_gap_pct":
            canonical.setdefault("fvg", {})["minimum_gap_bps"] = _ratio_to_bps(value)
        elif key == "fvg_min_displacement_factor":
            canonical.setdefault("fvg", {})["displacement_factor"] = value
        elif key == "structure_break_min_pct":
            canonical["structure_break_min_bps"] = _ratio_to_bps(value)
        elif key == "structural_stop_margin_pct":
            canonical["structural_stop_margin_bps"] = _ratio_to_bps(value)
        elif key == "min_poi_width_pct":
            canonical["min_poi_width_bps"] = _percent_to_bps(value)
        elif key in nested_fields and isinstance(value, dict):
            canonical.setdefault(key, {}).update(value)
        elif key in canonical_fields:
            canonical[key] = value
        elif key in ignored_legacy_aliases:
            continue
        else:
            unknown.append(key)

    if unknown:
        unknown_str = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown rule config field(s) in legacy payload: {unknown_str}")

    canonical["runtime_config_source"] = "legacy_strategy_rule_file_adapter"
    return canonical


def _canonicalize_detector_split_payload(payload: dict) -> dict:
    strategy = _load_yaml(DEFAULT_STRATEGY_CONFIG_PATH)
    temp_detector = DEFAULT_DETECTOR_CONFIG_PATH
    detector = PerceptionDetectorConfig.model_validate(payload)
    strategy_model = StrategyExecutionConfig.model_validate(strategy)
    canonical = _runtime_defaults_from_split()
    canonical.update(
        _runtime_defaults_from_split(
            detector_path=temp_detector,
            strategy_path=DEFAULT_STRATEGY_CONFIG_PATH,
        )
    )
    canonical["detector_config_id"] = detector.config_id
    canonical["strategy_config_id"] = strategy_model.config_id
    canonical["runtime_config_source"] = "detector_split_file_plus_default_strategy"
    canonical["ontology_version"] = detector.ontology_version
    canonical["equal_level_tolerance_bps"] = detector.geometry_and_tolerances.equal_level_tolerance_bps
    canonical["equal_level_min_touches"] = detector.geometry_and_tolerances.equal_level_min_touches
    canonical["swing_scales"] = detector.structural_scales["swing_scales"]
    canonical["fvg"] = {
        "minimum_gap_bps": detector.fair_value_gaps["minimum_gap_bps"],
        "displacement_factor": detector.fair_value_gaps["displacement_factor"],
    }
    canonical["break_confirmation"] = detector.structure_breaks.break_confirmation
    canonical["structure_break_min_bps"] = detector.structure_breaks.structure_break_min_bps
    canonical["displacement_body_factor"] = detector.structure_breaks.displacement_body_factor
    canonical["ob_lookback"] = detector.order_blocks["ob_lookback"]
    canonical["ob_min_body_factor"] = detector.order_blocks["ob_min_body_factor"]
    canonical["liquidity_sweep_lookback"] = detector.sweeps["liquidity_sweep_lookback"]
    canonical["lookback_bars"] = detector.detector_limits["lookback_bars"]
    canonical["atr_lookback"] = detector.detector_limits["atr_lookback"]
    return canonical


def _canonicalize_strategy_split_payload(payload: dict) -> dict:
    detector, strategy = _load_split_configs(DEFAULT_DETECTOR_CONFIG_PATH, DEFAULT_STRATEGY_CONFIG_PATH)
    strategy_model = StrategyExecutionConfig.model_validate(payload)
    canonical = _runtime_defaults_from_split()
    canonical["detector_config_id"] = detector.config_id
    canonical["strategy_config_id"] = strategy_model.config_id
    canonical["runtime_config_source"] = "strategy_split_file_plus_default_detector"
    canonical["confirmation_lookback"] = strategy_model.sequence_context["confirmation_lookback"]
    canonical["max_zone_age_bars"] = strategy_model.sequence_context["max_zone_age_bars"]
    canonical["poi_proximity_atr"] = strategy_model.poi_and_approach["poi_proximity_atr"]
    canonical["htf_poi_watch_distance_atr"] = strategy_model.poi_and_approach["htf_poi_watch_distance_atr"]
    canonical["htf_approach_lookback_bars"] = strategy_model.poi_and_approach["htf_approach_lookback_bars"]
    canonical["min_poi_width_bps"] = strategy_model.poi_and_approach["min_poi_width_bps"]
    canonical["require_fresh_poi"] = strategy_model.poi_and_approach["require_fresh_poi"]
    canonical["risk_reward_floor"] = strategy_model.risk_management["risk_reward_floor"]
    canonical["structural_stop_margin_bps"] = strategy_model.risk_management["structural_stop_margin_bps"]
    canonical["stop_buffer_atr_mult"] = strategy_model.risk_management["stop_buffer_atr_mult"]
    canonical["vision_authority_mode"] = strategy_model.authority_modes["vision_authority_mode"]
    return canonical


def load_rule_config(path: str | None = None) -> RuleConfig:
    if path is None:
        return RuleConfig(**deepcopy(_DEFAULTS))
    rules_path = Path(path)
    payload = _load_yaml(rules_path)
    config_id = payload.get("config_id")
    if config_id == "PERCEPTION_DETECTOR_CONFIG_V2":
        return RuleConfig(**_canonicalize_detector_split_payload(payload))
    if config_id == "STRATEGY_EXECUTION_CONFIG_V1":
        return RuleConfig(**_canonicalize_strategy_split_payload(payload))
    return RuleConfig(**_canonicalize_legacy_payload(payload))


# Rule Origin & Scope Classification Metadata
RULE_CLASSIFICATIONS: dict[str, dict[str, str | bool]] = {
    "swing_scales": {
        "origin": "system_approximation",
        "scope": "detector_candidates",
        "not_smc_doctrine": True,
        "description": "Candle pivot window sizes used as candidate detectors."
    },
    "break_confirmation": {
        "origin": "SMC_doctrine",
        "scope": "structure_breaks",
        "not_smc_doctrine": False,
        "description": "Rules for body-close structure break confirmation."
    },
    "fvg": {
        "origin": "quality_filter",
        "scope": "fair_value_gaps",
        "not_smc_doctrine": True,
        "description": "Filter for tradable FVG significance vs raw candle gap imbalance."
    },
    "equal_level_tolerance_bps": {
        "origin": "system_approximation",
        "scope": "liquidity_levels",
        "not_smc_doctrine": True
    },
    "equal_level_min_touches": {
        "origin": "system_approximation",
        "scope": "liquidity_levels",
        "not_smc_doctrine": True
    },
    "displacement_body_factor": {
        "origin": "SMC_doctrine",
        "scope": "displacement_quality",
        "not_smc_doctrine": False
    },
    "structure_break_min_bps": {
        "origin": "quality_filter",
        "scope": "structure_breaks",
        "not_smc_doctrine": True
    },
    "ob_lookback": {
        "origin": "system_approximation",
        "scope": "order_blocks",
        "not_smc_doctrine": True
    },
    "ob_min_body_factor": {
        "origin": "quality_filter",
        "scope": "order_blocks",
        "not_smc_doctrine": True
    },
    "liquidity_sweep_lookback": {
        "origin": "system_approximation",
        "scope": "sweeps",
        "not_smc_doctrine": True
    },
    "confirmation_lookback": {
        "origin": "quality_filter",
        "scope": "sequence_context",
        "not_smc_doctrine": True
    },
    "max_zone_age_bars": {
        "origin": "quality_filter",
        "scope": "sequence_context",
        "not_smc_doctrine": True
    },
    "poi_proximity_atr": {
        "origin": "quality_filter",
        "scope": "poi_and_approach",
        "not_smc_doctrine": True
    },
    "htf_poi_watch_distance_atr": {
        "origin": "quality_filter",
        "scope": "poi_and_approach",
        "not_smc_doctrine": True
    },
    "htf_approach_lookback_bars": {
        "origin": "system_approximation",
        "scope": "poi_and_approach",
        "not_smc_doctrine": True
    },
    "lookback_bars": {
        "origin": "system_approximation",
        "scope": "detector_limits",
        "not_smc_doctrine": True
    },
    "risk_reward_floor": {
        "origin": "user_preference",
        "scope": "trade_plan_validation",
        "not_smc_doctrine": True,
        "description": "Minimum RR target requested for execution; not structural validity."
    },
    "atr_lookback": {
        "origin": "system_approximation",
        "scope": "detector_limits",
        "not_smc_doctrine": True
    },
    "structural_stop_margin_bps": {
        "origin": "user_preference",
        "scope": "trade_plan_validation",
        "not_smc_doctrine": True
    },
    "stop_buffer_atr_mult": {
        "origin": "user_preference",
        "scope": "trade_plan_validation",
        "not_smc_doctrine": True
    },
    "min_poi_width_bps": {
        "origin": "quality_filter",
        "scope": "poi_and_approach",
        "not_smc_doctrine": True
    },
    "require_fresh_poi": {
        "origin": "user_preference",
        "scope": "poi_and_approach",
        "not_smc_doctrine": True
    },
    "vision_authority_mode": {
        "origin": "user_preference",
        "scope": "authority_modes",
        "not_smc_doctrine": True
    },
    "daily_session_profile": {
        "origin": "data_provider_constraint",
        "scope": "timeframe_reconstruction",
        "not_smc_doctrine": True,
        "description": "Explicit daily candle session profile (e.g. UTC, NY Close)."
    }
}


def get_rule_metadata(field_name: str) -> dict[str, Any]:
    """Retrieve classification metadata for a given RuleConfig parameter."""
    return RULE_CLASSIFICATIONS.get(field_name, {
        "origin": "unknown",
        "scope": "unknown",
        "not_smc_doctrine": True
    })

