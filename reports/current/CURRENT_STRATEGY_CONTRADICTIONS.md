# Current Strategy Contradictions

Status: initial WP-0001 report.

## Contradiction 1 - Old SMC Strategy Docs vs New Active Candidate

Older strategy docs can imply broad multi-pair SMC discretion, A/A+ grading,
fixed 3R expectations, or higher risk on strong setups. RASC-SMC-V1 is narrower:
BTCUSDT first, objective 4H regime, Daily veto, qualified 1H FVG, 15m
confirmation, close entry, 0% capital risk.

## Contradiction 2 - Ontology vs Strategy Parameters

`PERCEPTION_ONTOLOGY_V2.yaml` currently contains risk and strategy fields. The
constitution requires perception definitions and strategy profiles to separate.

## Contradiction 3 - Passing Tests vs Market Correctness

The repo has many passing tests, but tests do not prove strategy expectancy.
They prove implementation behaviour against current specs.

## Contradiction 4 - Engine Case Output vs Final Orchestrator

`tools/run_market_colleague_case.py` creates a strong vertical slice, but it is
not yet the final PerceptionEngineV2-led orchestrator and should be marked
transitional.
