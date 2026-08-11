# WP-SMC-15 — EURJPY Full-System and Annotation Repair

Date: 2026-08-09  
Status: PASS — local observe-only diagnostic; forex certification unchanged  
Gate: `GATE-WP-SMC-15-EURJPY-FULL-SYSTEM-ANNOTATION-001`

## Objective

Run EURJPY through the complete colleague pipeline, inspect the resulting D1/4H/1H/15M chart story, and repair only defects demonstrated by the real run. The work must remain closed-candle, fail-closed, evidence-bound, and non-executable.

## Confirmed defects repaired

- Expected daily FX weekend and bounded holiday closures no longer invalidate an otherwise continuous daily source. Intraday holes still fail closed.
- Sessioned FX may trim to a sufficiently deep clean post-gap segment; an insufficient recent segment is still rejected.
- Yahoo daily rows are canonicalized by exchange-local trading date and deduplicated so the appended market-time row cannot create a false daily gap.
- Active-range selection cannot pair the high and low of the same outside candle as an alternating swing range.
- Clean chart windows are bounded by timeframe so important candles remain legible.
- Strict `ActivePOI` decision payloads no longer receive the causal-only `linked_break_id`; lineage remains preserved in evidence IDs.
- An enforcement-ready V1/V3 causal disagreement now forces `NO_CONTEXT`, mixed/unresolved decision authority, and `REVIEW_REQUIRED` rather than allowing a provisional directional thesis to look aligned.
- The native story pack now includes D1 and consumes the causal authority's selected primary POI, preventing a valid protected OB from disappearing.

## EURJPY result

Run: `analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260809_182719/EURJPY`

- Source: Yahoo EURJPY spot proxy, completed market data through 2026-08-07.
- Official state: `REVIEW_REQUIRED`.
- Official direction: `mixed`.
- Current closed price: 182.378.
- Active 1H range: 182.322006–182.688004; current price is in discount.
- V1 provisionally votes D1/4H/1H bearish, but the stricter causal replay rejects the controlling D1, 1H, and 15M breaks as insufficient body-close/displacement confirmations.
- The important 4H bearish break survives causal replay. Its selected fresh protected-reversal-origin OB is 187.149002–187.352005, shown as a conditional retrace POI only.
- No validated current-price sweep/displacement/active POI/entry sequence exists. The system therefore emits no entry, stop, target, RR, trade box, paper order, or live order.

The D1/4H/1H/15M storyboards pass deterministic geometry and bitmap checks. Semantic image review remains pending because the run used the deterministic local review provider, not a real vision model.

## Validation

- Focused EURJPY repair ring: 72 passed in 19.83s.
- Full repository behavior run: 1,357 passed, 1 skipped; the only initial failure was the expected stale WP-SMC-14 source fingerprint after these four files changed.
- Compileall: PASS.
- Diff whitespace check: PASS.
- Authority boundary checker: PASS; 130 files scanned.
- Governance consistency: PASS; the 12-test WP-0044 governance ring passed after the new source-bound gate became current.
- New exact source manifest: `SOURCE_MANIFEST.tsv`.

## Limitations

- EURJPY and forex remain outside the certified BTCUSDT/Binance-USDM scope.
- Yahoo is a spot-chart proxy, not executable broker truth.
- The market was closed; this is a diagnostic snapshot, not a live opening signal.
- Deterministic bitmap review does not replace human semantic chart review.
- No perception accuracy, predictive edge, signal, paper execution, live execution, or profitability claim is created.
- Native TradingView Desktop markup was not attempted because the only detected process used the prohibited isolated audit profile rather than the owner's normal signed-in instance.
