# WP-0040 Formal Structure Graph Audit - 2026-07-07

## Verdict

The WP-0040 Formal MTF Structure Graph is implemented and validated. The audit
found a few important strictness/cleanliness issues and repaired them.

## Repairs Made

- Made the formal graph observe-only at the contract level:
  `authority_contract.signal_allowed` is now always `false`.
- Added `authority_contract.invariant_passed` so graph health is visible without
  implying trade permission.
- Changed child-vs-parent flip logic to require reconstructed child body-close
  price beyond the parent protected level.
- Ignored stale child breaks that predate the current parent external break.
- Kept wick probes informational when they are correctly segregated from
  confirmed BOS/CHoCH.
- Cleaned the sparse structure-map renderer header so title, mixed-context
  thesis, and invariant status no longer overlap.

## Validation

- `tests/test_wp0040_formal_structure_graph.py -q`: 20 passed.
- `tests/test_ai_smc_trade_ready_cases.py tests/test_wp0037_acceptance_gauntlet.py -q`: 12 passed.
- `git diff --check`: clean.
- `.venv/bin/python -m compileall smc_desk tools tests`: passed.
- `.venv/bin/python -m pytest -q`: 735 passed, 1 skipped.

## Live Observe-Only Smoke

Command:

```bash
.venv/bin/python tools/run_live_ai_smc_full_system.py --symbols BTCUSDT SUIUSDT --output-root analysis_runs
```

Run directory:

`/Users/tobimobolade/smc-codex-desk/analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260707_094402/`

Both BTCUSDT and SUIUSDT returned:

- `LOCAL_DETERMINISTIC_WORKFLOW:VALIDATED`;
- `official_state=THESIS_ONLY`;
- no hard issues;
- no external LLM API call;
- paper/live execution disabled.

Both formal graphs reported:

- `parent_child_context.status=PARENT_CHILD_CONFLICT`;
- `invariants.status=PASS`;
- `authority_contract.signal_allowed=false`;
- `authority_contract.trade_promotion_blocked=true`.

## Remaining Truth

This is a strong authority/guardrail layer, not proof of market edge. It improves
structural correctness, prevents false promotion, and produces cleaner visual
proof, but any predictive edge still needs separate outcome validation.
