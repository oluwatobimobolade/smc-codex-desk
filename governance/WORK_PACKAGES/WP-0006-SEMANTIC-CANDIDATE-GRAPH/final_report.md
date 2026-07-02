# WP-0006 Final Report - Semantic Candidate Graph

## Result

The scenario graph now includes conservative SMC semantic candidates:
liquidity pools, inducement, order-block proxies, and breaker candidates.

## Evidence

- Code: `smc_desk/colleague/smc_semantics.py`
- Live graph:
  `analysis_runs/BTCUSDT_live_tv_aligned_colleague_20260625/perception/mtf_state_graph.json`

## Live BTCUSDT Graph

- Graph version: `0.3`
- Nodes: `38`
- Edges: `42`
- Semantic summary:
  - liquidity pool candidates: `13`
  - order-block proxies: `4`
  - breaker candidates: `2`
  - inducement candidates: `1`

## Boundary

These are candidate/proxy semantics. They are useful reasoning objects, but
not human-adjudicated gold labels.

Validation: focused tests passed `12`, compileall passed, and full pytest
returned `354 passed in 25.18s`.
