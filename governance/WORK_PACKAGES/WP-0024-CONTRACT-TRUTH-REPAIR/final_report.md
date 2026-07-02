# WP-0024 Contract Truth Repair

Status: `PASS_ACCEPTED`

Date: `2026-06-27`

## Purpose

Repair the system contracts identified after the WP-0023 audit:

- Stop overclaiming HTF validation.
- Make V6 story charts the human-facing visual authority.
- Keep legacy annotations as debug-only.
- Rank active POIs with explicit trader-readable reasons.
- Add an active truth memory index.
- Make generated gauntlet manifests package-relative.
- Treat incomplete TradingView evidence as visual context mismatch.
- Log observe-only research events and a pending outcome contract.

## Changes

### HTF Truth

- Replaced the manifest claim `direct_vs_resampled_validation` with `derived_htf_consistency`.
- Added `native_htf_audit`.
- The native audit refuses to call local HTF files native when their `source` column indicates `derived_from_15m`.

### Chart Authority

- Renamed the legacy annotation stage to `04_debug_legacy_annotations`.
- Added explicit `chart_authority: debug_only_legacy_not_decision_authority`.
- Kept `04a_story_charts` as the V6-aligned decision-authority visual stage.
- Final report now shows `legacy_debug_charts_generated` and `decision_authority_story_charts_generated`.

### POI Selection

- Added ranked POI selection via `rank_poi_candidates`.
- Active POIs now carry:
  - `selection_score`
  - `selection_rank`
  - `selection_reasons`
- Watch-state output now includes a `poi_selection` audit object with rejected candidates.

### Memory Truth

- Added `active_truth_index.json` beside `decision_memory.jsonl`.
- The active truth index stores one current interpretation per symbol.
- Contradictory older records remain append-only but are marked superseded.

### Portable Manifests

- Generated chart, MTF, and memory package paths are now package-relative.
- Image manifests include `exists_at_write` so reports can verify generated assets without absolute `/Users/...` paths.

### Visual Reconciliation

- `reconcile_engine_vs_tradingview` now distinguishes:
  - `REVIEW_REQUIRED` for missing/failed visual capture.
  - `VISUAL_CONTEXT_MISMATCH` for incomplete screenshot/timeframe evidence.
  - `VISUAL_AUDIT_AVAILABLE` only when required screenshot coverage exists.
- TradingView remains audit-only and never changes market truth.

### Research Events

- Added `12_research_events`.
- The stage writes:
  - `event_ledger.jsonl`
  - `pending_outcome_contract.json`
  - `unresolved_resolution_stub.json`
  - `research_event_manifest.json`
- This creates a later outcome-testing contract without paper/live execution.

## Verification

- Focused tests:
  - `22 passed in 2.99s`
- Visual boundary regression:
  - `2 passed in 0.98s`
- Governance consistency:
  - `GOVERNANCE CONSISTENCY: PASS`
- Full suite:
  - `532 passed, 1 skipped in 86.30s`

## Live Package Check

Command:

```bash
.venv/bin/python tools/run_wp0020_market_colleague_gauntlet.py --symbol BTCUSDT --source data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_4year.csv --out analysis_runs/WP0024_BTCUSDT_CONTRACT_REPAIR_20260627 --mode csv --visual-mode skip
```

Result:

- Status: `PARTIAL_PASS`
- Failed layer: `07_tradingview_visual` because visual capture was intentionally skipped.
- Clean charts: `4`
- Legacy debug charts: `4`
- V6 story authority charts: `4`
- Research events: `2264`
- Pending outcome contract: `pending_observation`
- HTF derived consistency: `aligned`
- Native HTF audit: `not_available`, because local `1h/4h/1d` files are marked `derived_from_15m`, not native.

## Authority Boundary

- `market_edge_claimed: false`
- `paper_execution: disabled`
- `live_execution: disabled`
- `capital_risk: 0`

## Remaining Risks

- Native Binance HTF audit can only prove native alignment when actual native HTF files are present.
- Visual reconciliation still checks screenshot coverage and optional alignment metadata; it does not perform pixel-level chart equivalence.
- Research events are logged, but outcome resolution still needs future-candle runs before any edge statistics are allowed.
