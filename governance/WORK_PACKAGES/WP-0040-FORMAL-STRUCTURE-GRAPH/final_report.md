# WP-0040 Formal Structure Graph Repair — Final Report

## Status: COMPLETE / PASS

**Date:** 2026-07-05  
**Tests:** 695 passed, 1 skipped (15 new WP-0040 tests, all green)  
**Governance:** PASS

---

## What Was Built

A deterministic formal MTF structure graph that is the single authoritative source for every AI thesis, chart annotation, POI claim, and trade state.

### New Files

| File | Purpose |
|------|---------|
| `smc_desk/perception/formal_structure_graph.py` | Core graph builder — deterministic, no AI, no randomness, no API |
| `smc_desk/rendering/structure_map_renderer.py` | Sparse visual map — gray parent range, thick external BOS, dashed internal, no trade box |
| `tests/test_wp0040_formal_structure_graph.py` | 15 tests covering all invariants, validator integration, graph structure |

### Modified Files

| File | Change |
|------|--------|
| `smc_desk/brain/smc_evidence_pack_builder.py` | Builds graph from candidates + active range. Structure narrative defers to graph via `prefer_formal_graph_override`. |
| `smc_desk/brain/ai_smc_consistency_validator.py` | Added `_check_formal_structure_graph()` — invariant failures force hard downgrade, parent-child conflict blocks TRADE_PLAN_READY, requires mixed bias. |
| `smc_desk/colleague/orchestrator_v3.py` | Writes `16_formal_structure_graph/structure_graph.json` and `structure_map.png`. Report includes graph invariant status, parent-child context, thesis sentence, promotion blocks. |
| `smc_desk/perception/structure_narrative.py` | Added `prefer_formal_graph_override()` — when graph is present, narrative's parent-child context delegates to graph. |
| `smc_desk/brain/prompt_system/prompt_builder.py` | Non-negotiable: "The formal_structure_graph is the single authoritative source. Read it before candles or OHLC summaries." |

---

## Graph Schema (`formal_mtf_structure_graph_v1`)

```
schema: formal_mtf_structure_graph_v1
symbol: BTCUSDT
decision_time: ...
timeframes:
  1d: {external_bias, internal_state, protected_high/low, latest BOS/CHoCH, wick_probes, OB/FVG counts}
  4h: ...
  1h: ...
  15m: ...
parent_child_context:
  status: PARENT_CHILD_CONFLICT | ALIGNED | INCOMPLETE_ALIGNMENT | INSUFFICIENT_CONTEXT
  parent_timeframe, parent_bias, child_timeframe, child_bias, child_type
  is_child_body_closed_beyond_parent_protected: bool
  required_final_bias, required_trade_state
  thesis_sentence: str
active_range: {status, timeframe, direction, high, low, equilibrium, price_location, source}
invariants:
  status: PASS | REVIEW_REQUIRED | FATAL_STRUCTURE_VIOLATION
  checks: [7 invariant checks]
  violations: [list of failing codes]
authority_contract:
  signal_allowed, trade_promotion_blocked
  graph_is_authoritative: true, overrides_blocked: true
  invariant_failure_codes: [...]
```

## Invariants Checked

1. **internal_child_cannot_flip_parent** — internal/child breaks are pullback, not parent flips
2. **child_body_close_required_for_parent_break** — only body-close beyond parent protected level can flip parent bias
3. **wick_probes_are_not_breaks** — wick-only breaks are probes/sweeps, not confirmed BOS/CHoCH
4. **active_range_from_swing_structure** — range must come from swing structure, not OHLC summary extremes
5. **ohcl_summary_not_range_source** — OHLC summary extremes forbidden as range source
6. **parent_child_conflict_blocks_trade_ready** — conflict blocks TRADE_PLAN_READY

## Validator Integration

The `_check_formal_structure_graph` function in the validator:

- **FATAL_STRUCTURE_VIOLATION** → `formal_graph_invariant_violation` hard issue → full downgrade
- **REVIEW_REQUIRED** → `formal_graph_invariant_violation` hard issue → strips trade plan
- **trade_promotion_blocked + TRADE_PLAN_READY** → `formal_graph_trade_promotion_blocked`
- **has_conflict + direction ≠ mixed** → `formal_graph_requires_mixed_bias`
- **has_conflict + state ∉ {THESIS_ONLY, REVIEW_REQUIRED}** → `formal_graph_requires_thesis_only`

## Smoke Test (BTCUSDT)

Ran full `chat_ai_brain` pipeline on live Binance USD-M data:
- **structure_graph.json** generated with PARENT_CHILD_CONFLICT (1d bearish, 4h bullish)
- **structure_map.png** rendered — sparse visual proof (99KB)
- **Invariants:** REVIEW_REQUIRED (wick_probes_are_not_breaks in fresh data)
- **Validator correctly downgraded** old 07-03 decision that didn't match current 07-04 market state

## Test Coverage

- **15 new WP-0040 tests**: graph builder (parent-child conflict, aligned, wick probes, OHLC summary rejection, timeframe structure, internal states, serialization), validator integration (accepts THESIS_ONLY on conflict, rejects clean bullish, rejects TRADE_PLAN_READY, accepts aligned), 12h parent support, authority contract
- **All existing tests preserved**: WP-0034 through WP-0039, validator, renderer, orchestrator, POI — 695 passed, 1 skipped

## Authority Contract

- No live/paper execution, capital risk 0
- Graph is authoritative, overrides blocked
- Trade promotion blocked when invariants fail or parent-child conflict exists
- Signal allowed only when invariants PASS
- Execution always disabled
