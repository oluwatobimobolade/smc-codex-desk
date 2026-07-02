# Test Plan

## Static Contract Tests

- Required governance files exist.
- Required strategy candidate files exist.
- `CURRENT_STATE.yaml` keeps live and paper execution disabled.
- RASC-SMC-V1 is marked `RESEARCH_CANDIDATE` and `LIVE_SHADOW_ONLY`.
- No governance/strategy contract claims guaranteed profitability.
- Dataset registry marks the 100-case lab as non-gold and workflow-only.

## Runtime Tests

- Focused pytest for governance contracts.
- Existing market-colleague tests.
- Full pytest suite.
- Compileall for Python sources.

## Manual Evidence

- PDF extraction saved in `tmp/pdfs/`.
- Baseline report saved in this work package after tests.
