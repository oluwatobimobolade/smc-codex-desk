# WP-SMC-10 Current Implementation Map

Canonical-path code surface touched by this WP. Verified by direct read +
the deep multi-agent trace (2026-07-14).

## Displacement (WP-SMC-10/1)

- `smc_desk/perception/displacement.py:42` `score_break_displacement(structure_break, *, fvgs=None, atr=None) -> DisplacementProfile`
  - Reads `evidence.candle_body_ratio`, `evidence.body_close_penetration`, `evidence.broken_price`, `payload["direction"]`, `payload["price_low/high"]`, `confirmed_at`.
  - Returns `DisplacementProfile(displacement_score, break_quality∈{weak,moderate,strong}, valid_for_bias_flip, body_to_range_ratio, body_to_atr_ratio, close_beyond_structure_bps, fvg_created_after_break, impulse_candle_count, wick_rejection_ratio)`.
- `smc_desk/perception/engine_v2.py` `_enrich_breaks_with_displacement(breaks, fvgs)`: called after FVG detection (step 3, line ~123) when `canonical_displacement_scoring_enabled()`. Writes `brk.evidence.displacement_strength` + `brk.metadata['displacement']` (full profile). Skips unconfirmed/probe breaks; swallows scorer errors (falls back to legacy 0.0).
- `smc_desk/perception/structure.py:203` still emits `0.0` at candidate creation (correct -- displacement is scored at confirmation, not candidate creation). Enrichment overwrites it for confirmed breaks.
- `smc_desk/perception/structure_hierarchy.py:121` still calls `score_break_displacement` for the MTF hierarchy path (orphaned from canonical engine_v2 but still used by orchestrator evidence pack). Unchanged.

## Protected Point (WP-SMC-10/2)

- `smc_desk/perception/structure.py:_confirm_break` (was lines 251-301; now ~30 lines longer): threads `candles, swings, current_time` in. When `causal_protected_point_enabled()`:
  - Calls `_run_causal_protected_point_selection(brk, swings, candles, current_time)`.
  - Adapter builds programme-schema mappings: swings → `{object_id, timeframe, pivot_type, pivot_price, price_low/high, lifecycle:STRUCTURAL, pivot_time, confirmed_at}`; candles → `{timestamp, close}`; break → `{object_id, timeframe, direction, confirming_candle_time, impulse_candle_ids:[], origin_cluster_candle_ids}`.
  - Calls `protected_point.select(accepted_break, candidate_pool, active_range=None, timeframe_candles, decision_time)`.
  - Normalises `ProtectedPointSelection` to a mapping via `_protected_point_selection_to_mapping`.
  - If not abstained, `_match_candidate_to_swing(selected, swings, direction)` matches `pivot_price` to a swing within 5bps of matching direction; overrides `track.protected_low/high` only on match.
  - Always records `brk.metadata['protected_point_selection']` (selected, runner_up, abstained, rationale, graph_relationships, applied_override, fallback_reason).
  - On exception: records abstained + `causal_selection_error:<ExcType>`; legacy assignment kept.
- `smc_desk/structure/protected_point.py:308` `select(...)`: pre-existing causal-necessity algorithm. Generates >=4 candidates (opposing pivot, origin-cluster extreme, HTF origin, nested LTF pivot), scores causal necessity, abstains on ties or promotion-rule failures.

## OB-Origin Gate (WP-SMC-10/3)

- `smc_desk/perception/order_blocks.py:detect` between `departure_ids` (line ~59) and `origin_fvg` (line ~60): calls `_admit_origin_cluster(brk, departure_ids)`. If `admitted is False`, `continue` (OB not emitted).
- `_admit_origin_cluster(brk, departure_ids)`:
  - Flag OFF → `{admitted: True, gate: disabled}`.
  - Flag ON + no `brk.metadata['displacement']` → `admitted: False, reason: no_displacement_profile_on_break`.
  - Flag ON + no departure → `admitted: False, reason: no_departure_trace`.
  - Flag ON + score < 0.45 OR bps < 4.0 → `admitted: False, reason: departure_lacks_displacement`.
  - Flag ON + score >= 0.45 AND bps >= 4.0 → `admitted: True, reason: departure_produced_displacement_into_accepted_break`.
- Admission record attached to every emitted OB as `metadata['causal_origin_admission']`.

## Flags

- `smc_desk/perception/causal_repair_flags.py`: three functions read env at call time, default `"1"` post-cutover:
  - `canonical_displacement_scoring_enabled()` ← `SMC_CANONICAL_DISPLACEMENT_SCORING`
  - `causal_protected_point_enabled()` ← `SMC_CAUSAL_PROTECTED_POINT`
  - `causal_ob_origin_gate_enabled()` ← `SMC_CAUSAL_OB_ORIGIN_GATE`

## Downstream consumers (unchanged but now fed correct data)

- `smc_desk/perception/causal_poi_authority.py:677` `_pairwise_key` reads `linked_break_displacement_strength` -- now a real score instead of 0.0.
- `smc_desk/perception/causal_poi_authority.py:807-815` `_lifecycle_eligible` gates on `VALID_ACTIVE_SETUP_POI` + `active_setup`, set by `poi_lifecycle.classify_poi_scope` using containment in `protected_high/low` -- now the causally-correct bounds.
- `smc_desk/brain/annotation_candidate_composer.py:_authority_active_poi` packages `primary_causal_poi` -- now the causal OB, not the nearest red candle.