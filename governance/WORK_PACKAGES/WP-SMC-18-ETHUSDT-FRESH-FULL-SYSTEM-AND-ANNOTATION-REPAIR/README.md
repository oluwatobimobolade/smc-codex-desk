# WP-SMC-18 — ETHUSDT Fresh Full-System and Annotation Repair

Date: 2026-08-10  
Status: PASS — local observe-only validation; empirical certification unchanged  
Gate: `GATE-WP-SMC-18-ETHUSDT-FRESH-FULL-SYSTEM-001`

## Objective

Run ETHUSDT through the complete D1/4H/1H/15M system on fresh completed Binance USD-M candles, inspect the causal graph and every rendered chart independently, repair only defects reproduced by that run, and preserve all POI, trade-state, and execution authority boundaries.

## Repairs

- Added a narrow Binance/Yahoo DNS-resolution fallback that uses public DNS only after a system-DNS connection failure and keeps the requested hostname plus TLS certificate verification intact. It does not change the Mac's DNS settings and never uses insecure TLS.
- Corrected offline/live source narration, critic prompt detection, and acceptance checkpoint propagation so a failed checkpoint cannot be reported as an overall pass.
- Extended required historical OB/FVG context boxes to the latest sealed candle only as derived display geometry. Exact source candles and prices remain immutable, and the extension has no active-entry or bias authority.
- Added the certified active dealing range to its native-timeframe storyboard, including exact Range High, EQ, and Range Low, while preserving the sparse object budget.
- Consolidated narrow-range captions into a compact legend so exact levels remain readable on broad HTF charts.
- Added validator rules proving that both context and active-range extensions end exactly at the sealed window's latest candle; future or moved geometry fails closed.

## Fresh ETHUSDT result

Primary run: `analysis_runs/ethusdt_full_system_validation/LIVE_FULL_SYSTEM_AI_SMC_V3_20260810_120341/ETHUSDT`

Acceptance run: `analysis_runs/ethusdt_full_system_validation/WP0036_GAUNTLET_20260810_120728/ETHUSDT`

- Source: Binance USD-M ETHUSDT perpetual futures, completed candles only, TLS hostname verification required.
- Latest completed 15m/1h/4h price in the acceptance evidence: `1919.60`.
- Official state: `REVIEW_REQUIRED`; direction: `mixed`.
- Active 4H range: `1911.10–1937.67`; EQ `1924.385`; current location discount.
- V3 story: D1 external bearish; 4H and 1H external bullish; 1H internal bearish; 15m internal bullish but latest price below its 1921.71 break level.
- Both causal-POI scenarios remain unresolved. No active POI, entry, stop, target, RR, projected trade path, trade box, paper order, or live order is emitted.
- Historical 4H bearish supply at `1957.47–2009.42` remains material context only after a later bullish external BOS superseded its control.
- Independent semantic review agrees with `REVIEW_REQUIRED / NO TRADE` and is recorded in the acceptance artifact as `CODEX_SEMANTIC_REVIEW.md`.

## Validation

- WP-0036 acceptance gauntlet: all 12 checkpoints PASS.
- Focused geometry/render/context ring: 50 passed.
- Full repository run before governance rebind: 1377 passed, 1 skipped, and one expected source-manifest mismatch; no behavioral test failed.
- Final source-bound canonical run after governance rebind: 1378 passed, 1 skipped, 0 failed in 613.31s.
- Native D1/4H/1H/15M storyboard coverage: PASS.
- Native deterministic bitmap review: PASS with independent semantic review supplied separately.
- Exact implementation source manifest: `SOURCE_MANIFEST.tsv`.

## Limitations

- ETHUSDT is a replication symbol, not the certified initial BTCUSDT scope.
- The built-in provider is local deterministic and made no API LLM call; the Codex thread performed a separate semantic chart review.
- A causal episode, active range, or historical supply zone does not guarantee future reaction.
- The V1/V3 controlling-break disagreement remains intentionally fail-closed and requires reconciliation or fresh evidence.
- No perception-accuracy, predictive-edge, signal, paper, live, execution, or profitability authority is created.
