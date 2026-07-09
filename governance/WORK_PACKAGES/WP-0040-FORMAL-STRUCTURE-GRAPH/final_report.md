# WP-0040 Formal Structure Graph Repair - Final Report

## Status: COMPLETE / PASS / AUDITED

**Original completion date:** 2026-07-05
**Audit repair date:** 2026-07-07
**Final validation:** 735 passed, 1 skipped
**Focused WP-0040 validation:** 20 passed
**Live smoke:** BTCUSDT + SUIUSDT observe-only full-system smoke passed
**Governance:** PASS

---

## What Exists

WP-0040 added a deterministic Formal MTF Structure Graph that every AI thesis,
chart annotation, POI claim, and trade/watch state must obey before any
interpretation layer can speak.

The graph is local-first and observe-only:

- no external LLM API;
- no broker or execution API;
- no paper/live execution authority;
- no hidden probabilistic promotion;
- one exported graph object per run: `formal_mtf_structure_graph_v1`.

## Core Files

| File | Purpose |
|------|---------|
| `smc_desk/perception/formal_structure_graph.py` | Core deterministic graph builder and graph-to-validator adapters. |
| `smc_desk/rendering/structure_map_renderer.py` | Sparse visual proof map with protected range, certified structure lines, invariant status, and no trade box. |
| `tests/test_wp0040_formal_structure_graph.py` | 20 focused tests for graph invariants, parent-child logic, validator integration, and renderer output. |
| `smc_desk/brain/smc_evidence_pack_builder.py` | Builds the graph and places it in the evidence pack before AI interpretation. |
| `smc_desk/perception/structure_narrative.py` | Makes the narrative defer to the formal graph when present. |
| `smc_desk/brain/ai_smc_consistency_validator.py` | Hard-downgrades AI decisions that contradict graph authority. |
| `smc_desk/colleague/orchestrator_v3.py` | Writes `16_formal_structure_graph/structure_graph.json` and `structure_map.png` into each analysis run. |
| `smc_desk/brain/prompt_system/critic_prompt.py` | Graph challenger: reads the graph first and can only downgrade, never promote. |

## Schema Contract

The graph object contains:

- `schema`, `symbol`, `decision_time`;
- per-timeframe nodes with external bias, internal state, protected high/low,
  latest confirmed BOS/CHoCH, wick probes, OB/FVG counts, sweeps, liquidity,
  and inducement counts;
- `parent_child_context`;
- `active_range`;
- `invariants`;
- `authority_contract`.

The authority contract is intentionally strict:

```json
{
  "signal_allowed": false,
  "execution": "disabled",
  "capital_risk": 0,
  "graph_is_authoritative": true,
  "overrides_blocked": true,
  "invariant_passed": true,
  "invariant_status": "PASS",
  "trade_promotion_blocked": true,
  "invariant_failure_codes": []
}
```

Important distinction:

- `invariant_passed=true` means the graph is internally healthy.
- `signal_allowed=false` always, because the formal graph is evidence authority,
  not an execution engine.
- `trade_promotion_blocked=true` when invariant status is not `PASS` or when a
  parent-child conflict exists.

## Invariants

1. `internal_child_cannot_flip_parent` - internal/child breaks cannot flip parent
   structure.
2. `child_body_close_required_for_parent_break` - only a child body close beyond
   the parent protected high/low can become a parent-break candidate.
3. `wick_probes_are_not_breaks` - wick probes are segregated from confirmed
   breaks and are informational unless incorrectly promoted.
4. `active_range_from_swing_structure` - active range must come from confirmed
   protected swing structure.
5. `ohcl_summary_not_range_source` - OHLC summary extremes cannot define active
   range authority.
6. `parent_child_conflict_blocks_trade_ready` - conflict blocks
   `TRADE_PLAN_READY` and requires thesis/watch/review behavior.

## 2026-07-07 Audit Repairs

The audit found and fixed four important correctness issues:

1. The graph authority contract previously allowed `signal_allowed=true` when
   invariants passed. This contradicted the observe-only roadmap. It is now
   always `false`, with `invariant_passed` added for graph health.
2. Child-vs-parent breaking logic now uses the child break's reconstructed body
   close price, not only the broken level price. A parent flip candidate requires
   body close beyond the parent protected level.
3. Stale child breaks older than the current parent external break no longer
   influence parent-child alignment.
4. Wick probes are treated as normal market evidence when they remain segregated
   from confirmed breaks; they no longer force invariant failure by existing.

The audit also repaired the sparse structure-map header layout. The renderer now
uses reserved figure-level header space, wraps the mixed-context sentence, and no
longer collides title/thesis/invariant text.

## Validator Behavior

The consistency validator now enforces:

- graph invariant failure -> hard downgrade and trade fields stripped;
- `trade_promotion_blocked` + `TRADE_PLAN_READY` -> hard issue;
- parent-child conflict + non-mixed direction -> hard issue;
- parent-child conflict + promoted state -> hard issue;
- graph challenger can downgrade only, never promote.

## Visual Proof

Each orchestrator run writes:

- `16_formal_structure_graph/structure_graph.json`;
- `16_formal_structure_graph/structure_map.png`.

The structure map is intentionally sparse. It shows certified graph structure,
not a detector firehose, and it never draws entry/SL/TP boxes in thesis/watch or
review states.

## Validation

Commands run on 2026-07-07:

```bash
.venv/bin/python -m pytest tests/test_wp0040_formal_structure_graph.py -q
.venv/bin/python -m pytest tests/test_ai_smc_trade_ready_cases.py tests/test_wp0037_acceptance_gauntlet.py -q
git diff --check
.venv/bin/python -m compileall smc_desk tools tests
.venv/bin/python -m pytest -q
.venv/bin/python tools/run_live_ai_smc_full_system.py --symbols BTCUSDT SUIUSDT --output-root analysis_runs
```

Results:

- WP-0040 focused suite: `20 passed`.
- Renderer/orchestrator affected suite: `12 passed`.
- `git diff --check`: clean.
- `compileall`: passed.
- Full suite: `735 passed, 1 skipped`.
- Live smoke: BTCUSDT and SUIUSDT both
  `LOCAL_DETERMINISTIC_WORKFLOW:VALIDATED`, `THESIS_ONLY`, no hard issues,
  no LLM API call, no paper/live execution.

Smoke run directory:

`analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260707_094402/`

BTCUSDT graph:

- parent-child context: `PARENT_CHILD_CONFLICT`;
- invariants: `PASS`;
- `signal_allowed=false`;
- `trade_promotion_blocked=true`.

SUIUSDT graph:

- parent-child context: `PARENT_CHILD_CONFLICT`;
- invariants: `PASS`;
- `signal_allowed=false`;
- `trade_promotion_blocked=true`.

## Final Truth

WP-0040 is now correctly positioned as the formal deterministic authority layer.
It can certify structure health, force mixed/review states, and block false trade
promotion. It does not prove market edge and does not authorize execution.
