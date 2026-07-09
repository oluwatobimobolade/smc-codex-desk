# Core Memory

## Original Goal

SMC Codex Desk is being built as a market colleague, not as a simple indicator,
chatbot, signal service, or backtest script. The colleague should validate
market data, reconstruct higher-timeframe charts from canonical lower-timeframe
data, compare its internal charts with TradingView through Kimi WebBridge,
reason about SMC structure like a disciplined trader, produce clean annotations,
build conditional scenarios, remember cases, and abstain when the evidence is
not enough.

## Current North Star

The system should become nearly always useful and highly accurate about current
market state, deterministic geometry, and frozen operational definitions. It
must be cautious about future prediction. Future market behaviour is not known
with certainty, and any predictive or economic edge must be earned through
historical validation, untouched holdout testing, live shadow operation, and
calibration.

## Recent Milestones

**WP-0012A–D (2026-06-26):** Complete end-to-end reasoning spine.
- Legacy engine isolated behind `legacy_comparison.py` adapter.
- MTF graph with per-timeframe completeness, rich relationships, and structural scope awareness.
- Canonical event ledger: duplicate suppression, replay idempotence, schema versioning.
- Generic decision pipeline with conservative decision policy. 426 tests passing.

**WP-0018 to WP-0029 (2026-06-27 to 2026-06-28):** Real perception, interpretation hierarchy, and visual annotation.
- Implemented `PerceptionEngineV2` with separate internal and external structure tracks.
- Added professional SMC interpretation layer: external swings control bias, internal breaks are pullbacks only.
- Added MTF consensus guard and resampled NY close daily candle boundaries.
- Replaced direct legacy chart analysis with clean visual annotation boundary.

**WP-0031 to WP-0038/39 (2026-06-29 to 2026-07-04):** Production AI colleague and correct verification.
- Codified intraday doctrine (15m canonical candles, 1m forbidden, minimum 3.0 R:R).
- Standardized AI `AISMCDecision` JSON schema with 15-step reasoning order contract and consistency validator.
- Implemented orchestrator v3 with backfill pagination, context depth checks, and gold-set validation.
- Built modular prompt operating system with stable registry hashes and watch/refusal states.
- Created active dealing range resolver (`source=protected_swing_pair`) and self-review block validation.
- Fixed EUR/NZD and AVAX wicks (visual offsets, base64 chart bytes, forex session-gap trimming).
- Integrated parent-child timeframe conflict guard and POI refinement/inducement doctrine.
- Verified test suite: 680 passed, 1 skipped.

**WP-0040 Formal MTF Structure Graph (2026-07-05):** Single authoritative source for all AI theses.
- Built `smc_desk/perception/formal_structure_graph.py` — deterministic graph, no AI, no randomness, one truth.
- Schema `formal_mtf_structure_graph_v1` with per-timeframe nodes, parent-child context, active range, 6 invariants, authority contract.
- 6 invariants: internal_child_cannot_flip_parent, child_body_close_required_for_parent_break, wick_probes_are_not_breaks, active_range_from_swing_structure, ohcl_summary_not_range_source, parent_child_conflict_blocks_trade_ready.
- Built `smc_desk/rendering/structure_map_renderer.py` — sparse visual proof: gray parent range, thick external BOS, dashed internal CHoCH, no trade box.
- Wired graph into evidence pack builder, consistency validator (hard-downgrade on invariant failures), orchestrator V3 (writes structure_graph.json + structure_map.png), and prompt system (non-negotiable: graph is authoritative).
- Upgraded critic to graph challenger: reads graph first, can ONLY downgrade, NEVER promote.
- 2026-07-07 audit repair: graph `signal_allowed` is always false; `invariant_passed` carries graph health without implying execution permission. Child parent-break logic now requires body close beyond parent protected level, stale child breaks are ignored, wick probes remain informational unless promoted, and structure-map headers no longer overlap.
- 20 WP-0040 tests, all green. Fresh observe-only smoke on BTCUSDT + SUIUSDT passed (THESIS_ONLY, graph conflict, invariants PASS, trade promotion blocked).
- Test suite: 735 passed, 1 skipped.

**WP-0041 Professional AI SMC Annotation Planner (2026-07-09):** AI-directed professional markup under graph authority.
- Added `annotation_plan_v2` as the professional SMC drawing instruction layer beside legacy labels/levels.
- Added v2 drawing objects: local structure segments, bounded POI zones, liquidity lines, conditional path projections, and trade boxes gated to `TRADE_PLAN_READY`.
- Added `annotation_plan_validator.py` and wired it into the main consistency validator so unsupported drawings downgrade to `REVIEW_REQUIRED`.
- Upgraded official renderer to prefer v2 and write annotation plan, validation, and self-review artifacts in each run.
- Local deterministic provider now emits conservative v2 watch markup from certified active-range evidence.
- Validation: 5 WP-0041 tests passed, affected suite 59 passed, full suite 740 passed / 1 skipped. BTCUSDT/SUIUSDT and GBPUSD smoke runs validated observe-only.

**Pipeline:** Live/Historical OHLCV → PEV2 (15m/1H/4H/1D) → Event Ledger → MTF Graph & Parent-Child Guard → Formal Structure Graph (AUTHORITATIVE) → Strategy-State Engine & POI Refinement → Evidence Graph → Decision.

## Architectural History

The project began as an SMC strategy and signal engine. It then moved toward a
dual-lens architecture after several important corrections:

- Screenshots are evidence, not price authority.
- OHLCV and timestamps are the source of market truth.
- 15m Binance futures data became the canonical crypto source.
- 1H, 4H, and 1D are derived internally from 15m to avoid native timeframe
  mismatch and future leakage.
- Internal structure and external/protected structure were separated after a
  false CHoCH/BOS interpretation.
- Watch states were separated from executable trades.
- Engine labels became weak/operational labels, never gold truth.
- Perception accuracy claims now require human-adjudicated real cases.
- Prediction and ML code is research scaffolding until validated.

## Failed Or Unproven Trading Evidence

Historical research has not proven a live trading edge. Broad open-rule tests
were weak after costs. Some narrow FVG-width research subsets looked better, but
they were mostly watch/geometry studies and remain research-only. A 50-trade
audit showed reproducibility of geometry but did not validate a live executable
strategy, especially under 10 bps costs. Win-rate targets and fixed 3R claims
are not authority.

## Current Architecture

The active architecture is moving toward:

- market truth and timeframe reconstruction;
- PerceptionEngineV2 for objective/operational perception objects;
- a market-colleague run package;
- Kimi WebBridge as verified external chart evidence;
- state/scenario tracking;
- human review and adjudication;
- prediction only after separate validation.

The transitional operator command is `tools/run_market_colleague_case.py`. It
currently creates a useful local-first case package, but still relies heavily on
the legacy engine and renderer. It must migrate toward a PerceptionEngineV2-led
orchestrator.

## Current Capabilities

- Binance USD-M BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, and AVAXUSDT local data exists.
- Yahoo FX EURNZD data integration exists.
- 15m is the canonical source; derived 1H/4H/1D timeframes resampled internally.
- PerceptionEngineV2 detects swings, external/internal structure breaks, protected swings, order blocks, and qualified FVGs.
- Active dealing range resolver restricts the trading zone to alternating protected swings.
- Top-down consensus guard identifies parent-child conflicts and forces mixed-bias refusals.
- POI Refinement module ranks inducement zones vs origin order blocks.
- Stricter AI trader brain prompt operating system with modular versioned files, schema constraints, and watch/refusal states.
- Decoupled consistency validator separates doctrine correctness from execution parameters.
- Orchestrator v3 flow runs MTF candle resamples, evidence packaging, provider interfaces, AI critic reviews, and visual annotations.
- Visual annotation renderer draws expected paths for watch layouts and gates entry-SL-TP boxes strictly to ready trades.
- Forex session gap trimming handles exchange closures without breaking consensus.
- Formal MTF structure graph is the single authoritative source for all AI theses, chart annotations, POI claims, and trade/watch states.

## Known Flaws

- Headless visual capture (Kimi WebBridge) is visual context only; DOM-verified TradingView state verification remains audit-only.
- Large adjudicated human gold datasets are still not loaded at scale.
- Machine Learning (XGBoost) and predictive models remain in research status and are not decision authority.

## Current Release Candidate

- Release ID: `colleague-core-rc0`
- Status: research foundation / production-ready colleague loop
- Live execution: disabled
- Paper execution: disabled
- Predictive authority: not certified

## Prohibited Claims

Do not claim guaranteed profitability, a foolproof strategy, certain future price prediction, human-grade gold truth from AI labels, or live trading readiness. Passing tests means code behaved as specified; it does not prove market correctness.

## Next Approved Milestone

Complete `WP-0024-NEXT`: Stage E execution readiness (premium/discount gates affecting POI watch quality, liquidity target maps, ATR threading into all structure layers, and 15m/1h/4h/1d backfill paginator).
