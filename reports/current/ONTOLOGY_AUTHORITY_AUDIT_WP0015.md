# Ontology Authority Audit

Status: `split_contract_ready_code_migration_pending`

## Monolith

- Runtime source: `/Users/tobimobolade/smc-codex-desk/specs/PERCEPTION_ONTOLOGY_V2.yaml`
- Mixed authority terms: `confirmation_lookback, htf_approach_lookback_bars, htf_poi_watch_distance_atr, max_zone_age_bars, min_poi_width_bps, poi_proximity_atr, require_fresh_poi, risk_reward_floor, stop_buffer_atr_mult, structural_stop_margin_bps`

## Detector Split

- Path: `/Users/tobimobolade/smc-codex-desk/specs/PERCEPTION_DETECTOR_CONFIG_V2.yaml`
- Clean for detector authority: `True`

## Strategy Split

- Path: `/Users/tobimobolade/smc-codex-desk/specs/STRATEGY_EXECUTION_CONFIG_V1.yaml`
- Strategy terms present: `capital_risk, confirmation_lookback, htf_approach_lookback_bars, htf_poi_watch_distance_atr, max_zone_age_bars, min_poi_width_bps, poi_proximity_atr, require_fresh_poi, risk_reward_floor, stop_buffer_atr_mult, structural_stop_margin_bps`

## Boundary

- Runtime migration is still pending.
- No market edge, paper execution, or live execution authority is created by this split.
