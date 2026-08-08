# System Correctness Audit - Parent/Child Structure + POI Refinement

Date: 2026-07-03

## Verdict

The current work is on the right track and passes the local verification suite.

The user's existing updates around deeper OB reaction priority, FVG-as-secondary, and inducement risk are structurally sound. They correctly address the SUI/BTC-style problem where the system could pick the nearest visible FVG/OB-like area instead of the deeper origin OB that a stronger SMC read would prioritize.

The remaining issue found during this audit was not the POI refinement. It was narrative compression: the system could still describe a parent/child structure conflict too loosely, for example treating a bearish 12H/1D parent plus bullish 1H recovery as simply bullish or simply bearish. That is now guarded.

## Confirmed Existing Work

- `smc_desk/perception/poi_lifecycle.py`
  - POI selector method upgraded to `ranked_active_poi_v3_protected_range_first_deeper_ob_reaction_priority`.
  - Active protected-range validity still outranks freshness/timeframe.
  - FVG-only pockets are secondary unless they overlap OBs or receive fresh confirmation.
  - Shallow/front POIs are marked as `front_inducement_risk` when a deeper same-timeframe valid OB sits behind them.
  - Deeper same-leg OBs are marked as `deeper_order_block_reaction_candidate`.

- `smc_desk/engine.py`
  - Legacy engine ranking now also applies deeper OB / inducement context.
  - The change affects POI preference only. It does not grant execution permission without the existing sweep, displacement, confirmation, stop, target, and RR gates.

- `strategies/smc/POI_REFINEMENT_DOCTRINE.md`
  - Correctly documents that FVG is not OB, nearest zone is not always best, inducement can sit before the true POI, and deeper origin OB can be the better reaction watch area.

## Repair Added During Audit

- `smc_desk/perception/structure_narrative.py`
  - Added `parent_child_context`.
  - Supports `12h` as parent context when daily is unavailable.
  - Produces explicit thesis language such as: `12h remains bearish parent structure while 1h is bullish child recovery...`
  - Forces parent/child conflict to require `mixed` final context.

- `smc_desk/brain/ai_smc_consistency_validator.py`
  - Added hard validation rules:
    - Parent/child conflict cannot be flattened into clean bullish or clean bearish.
    - Parent/child conflict cannot become `TRADE_PLAN_READY`.
    - The final thesis must explicitly name the parent timeframe, child timeframe, both biases, and pullback/recovery context.

- Prompt system updates:
  - `reasoning_order_prompt.py`
  - `evidence_guardrail_prompt.py`
  - `smc_doctrine_prompt.py`
  - `prompt_builder.py`

These now require the AI brain to run a parent-child structure check before finalizing the thesis.

## BTC Annotation Failure Explained

The earlier mistake happened because the system had the pieces but did not force the correct SMC sentence.

Correct BTC read from the user annotation review:

```text
12H: bearish external parent structure
1H: bullish child recovery
15m: bullish external move with bearish internal pullback
Final: mixed / thesis-only / no trade until confirmation
```

The system now has an explicit guard against saying only "bullish" or only "bearish" in this state.

## Verification

```text
Focused parent-child guard tests: 4 passed
Affected POI/engine/BTC/SUI/AI tests: 33 passed
Earlier affected AI/orchestrator set: 38 passed
git diff --check: clean
compileall: passed
Full test suite: 680 passed, 1 skipped in 106.00s
```

## Remaining Risk

This confirms software correctness and regression safety. It does not prove trading edge.

The next useful step is to replay recent BTC/SUI/SOL/AVAX cases through the repaired parent-child + deeper-OB POI lens and check whether the thesis wording, selected POI, and no-trade/trade-ready gates now match the human SMC read.
