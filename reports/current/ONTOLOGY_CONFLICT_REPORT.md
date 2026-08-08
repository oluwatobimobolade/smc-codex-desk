# Ontology Conflict Report

Status: initial WP-0001 finding, not a completed ontology audit.

## Confirmed Conflict

`specs/PERCEPTION_ONTOLOGY_V2.yaml` currently contains both perception
definitions and strategy/risk parameters.

Perception-like fields:

- `equal_level_tolerance_bps`
- `swing_scales`
- `fvg`
- `break_confirmation`
- `structure_break_min_bps`
- `liquidity_sweep_lookback`

Strategy/risk-like fields that should move to a strategy profile:

- `poi_proximity_atr`
- `htf_poi_watch_distance_atr`
- `require_fresh_poi`
- `risk_reward_floor`
- `structural_stop_margin_bps`
- `stop_buffer_atr_mult`
- `min_poi_width_bps`
- `allowed_poi_kinds` in `RuleConfig`

## Why This Matters

PerceptionEngineV2 should detect and describe market structure without knowing
entry, stop, target, reward, or risk policy. Strategy profiles should consume
perception objects and define executable sequences.

## Current Constraint

`smc_desk/rules.py` and the legacy engine currently share one `RuleConfig`.
Splitting this immediately could break existing tests and tooling. The next
work package should introduce a separate strategy profile while keeping a
compatibility adapter until the legacy engine is retired from primary authority.
