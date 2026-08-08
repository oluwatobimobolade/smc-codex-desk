# WP-SMC-01 - Verified Repository Truth

Status: `PASS_SOURCE_BOUND_DIRTY_BASELINE`

This work package binds the expert-perception programme to the repository that
actually exists on 2026-07-12. It is a source census and authority map, not a
claim of SMC accuracy or predictive edge.

## Gate

The gate passes only when all four required baseline artefacts exist, the
source manifest is reproducible, and the recorded test commands complete:

- `CURRENT_IMPLEMENTATION_MAP.md`
- `VERIFIED_GAP_MATRIX.yaml`
- `BASELINE_TEST_REPORT.json`
- `BASELINE_SOURCE_MANIFEST.tsv`

The canonical runtime remains observe-only. The experimental programme must
not be promoted into `PerceptionEngineV2` by this work package.

## Result

- Source records: 849
- Manifest SHA-256: `7e037c581c0fef159d2311cb19b67d3c02688590c3cc6abf3de229fe05a032a4`
- Focused baseline: 85 passed
- Full baseline: 960 passed, 1 skipped
- Honest limitation: this is a reproducible manifest of a dirty working tree,
  not a clean immutable Git commit.

