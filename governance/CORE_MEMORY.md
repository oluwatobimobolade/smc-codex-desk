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
- Historical WP-0040 completion validation: 735 passed, 1 skipped. The current repository count is recorded under WP-0041A below.

**WP-0041 Professional AI SMC Annotation Planner (2026-07-09):** AI-directed professional markup under graph authority.
- Added `annotation_plan_v2` as the professional SMC drawing instruction layer beside legacy labels/levels.
- Added v2 drawing objects: local structure segments, bounded POI zones, liquidity lines, conditional path projections, and trade boxes gated to `TRADE_PLAN_READY`.
- Added `annotation_plan_validator.py` and wired it into the main consistency validator so unsupported drawings downgrade to `REVIEW_REQUIRED`.
- Upgraded official renderer to prefer v2 and write annotation plan, validation, and self-review artifacts in each run.
- Local deterministic provider now emits conservative v2 watch markup from certified active-range evidence.
- Validation: 5 WP-0041 tests passed, affected suite 59 passed, full suite 740 passed / 1 skipped. BTCUSDT/SUIUSDT and GBPUSD smoke runs validated observe-only.

**WP-0041A Annotation Integrity Repair (2026-07-09):** The hard repair that makes WP-0041 mechanically honest.
- New `annotation_evidence.py` builds canonical `AnnotationEvidenceAnchor` index from detector candidates and graph active range (exact price, price band, start/end timestamps, timeframe, direction, structure scope, kind, source).
- Validator now mechanically verifies drawn price/span/scope/kind/type against source anchors (8 bps tolerance, 2-candle span tolerance). Mismatches emit specific issues (`*_price_mismatch`, `*_span_mismatch`, `*_scope_mismatch`, `*_kind_mismatch`).
- New `annotation_visual_critic.py` is a downgrade-only critic that audits the actual built scene for visible labels, drawing object density per chart template, and overlap risk. Its result is saved as `annotation_visual_review.json`, and `annotation_self_review.md` is rebuilt from the real critic result.
- New `annotation_candidate_composer.py` is a deliberate selector that picks at most four evidence-grounded marks (active POI, latest visible external 15m structure, active-range liquidity, conditional path). The conditional path is only emitted when a certified active POI exists in a path-allowed state.
- Renderer suppresses generic banners, footer, and explanatory text when `level_source=annotation_plan_v2`. Scene reports `legacy_labels_suppressed` and embeds the visual critic payload.
- Orchestrator writes `annotation_visual_review.json`, `annotation_validation.json`, `annotation_plan_v2.json`, and a critic-driven `annotation_self_review.md` in each run.
- Live runner wired to `compose_local_annotation_plan_v2` so live path produces evidence-grounded V2 markup instead of generic range decoration.
- V2 `trade_box` geometry verified against validated entry/stop/target plans within tolerance; legacy text is suppressed.
- Adversarial tests cover: moved-BOS price/span mismatch, internal-as-external relabel, path-without-active-POI, native V2 trade box, and visual-critic overlap cleanup.
- 2026-07-10 re-audit added confirmation/lifecycle anchors, wick-probe rejection, evidence-grounded active-POI selection, critic-enforced official downgrade, empty-V2 legacy suppression, bounded one-candle POI display, and decision-time-correct offline XAU replay.
- A final coordinate audit found that evidence indices used 120 candles while the official chart used 240. Official rendering now uses the evidence-window length, timestamp geometry overrides raw indices, and out-of-window evidence cannot snap to an edge. POI lifecycle is independently replayed from subsequent candles because order-block detector lifecycle is incomplete.
- The final live deterministic GBPUSD smoke mapped a fresh watch-only 15m OB at its true July 10 origin, explicitly recorded the bullish-HTF/bearish-active-range conflict, rendered only a bounded OB plus local BOS/BSL, and kept entry/SL/TP/trade box absent. The visual critic passed.
- Validation after re-audit: 12 WP-0041A tests passed, WP-0041+WP-0041A combined 17 passed, affected integrity suite 126 passed, and the full repository suite passed 760 / skipped 1.

**BR-004 to BR-006 AI-First Perception Lab (2026-07-10):** AI becomes the operating structure colleague under hard market-truth controls.
- Protected benchmark registry now separates doctrine, development, blind validation, and annotation-comprehension partitions. Its blind directory is hash-ledger guarded and remains unpopulated; public BTCUSDT development and GBPUSD annotation cases are weak AI labels only.
- The six-role lab is executable without an external API: blind chart reader -> certified candidate reconciler -> causal episode builder -> adversarial critic -> sparse annotation planner -> visual critic. Every prompt, input, raw output, parsed output, provider mode, and evidence ID is logged; a critic can only revise or downgrade.
- Source-grounded AI doctrine panel completed: five pilot rules accepted (body-close over exact protected level, parent/child subordination, causal grounding, abstention, POI identity); displacement threshold and deeper-OB priority remain contested hypotheses. It cannot modify detector semantics.
- BTCUSDT was inspected on clean 4H/1H charts and run in `MANUAL_AI_ASSISTED_JSON` mode with no API. It correctly treated the 1H bullish recovery as stale/subordinate to the later 4H/1D bearish parent and produced no signal. The output is AI weak consensus, never gold or execution authority.
- Final validation for this source-bound slice: 810 passed, 1 skipped. The global perception/annotation readiness gate stays closed pending blind cases and repeated frozen evaluation.

**WP-0041B Professional AI Annotation Render Loop (2026-07-11):** The AI-selected structure story now becomes a real, verified chart.
- Added a certified semantic-to-geometry resolver. AI selects evidence IDs; deterministic evidence owns every price, timestamp, span, type, and timeframe.
- Added a sparse multi-timeframe renderer with clean baselines, exact object reconciliation, image hashes, changed-pixel proof, nonblank checks, and clutter limits.
- Moved the visual critic after rendering. A PASS now requires attestation of the exact render manifest and every annotated image hash; stale or absent render evidence is rejected.
- BTCUSDT historical proof rendered three selected objects across 4H and 1H: controlling bearish 4H CHoCH, protected high, and dashed stale 1H bullish recovery. No POI or trade box was invented.
- Full validation: 815 passed, 1 skipped. This is observe-only mechanism validation, not predictive edge or execution readiness.

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
- Visual annotation renderer prefers `annotation_plan_v2` professional SMC markup, draws sparse validated objects, and gates entry-SL-TP boxes strictly to ready trades.
- Forex session gap trimming handles exchange closures without breaking consensus.
- Formal MTF structure graph is the single authoritative source for all AI theses, chart annotations, POI claims, and trade/watch states.

## Known Flaws

- Headless visual capture (Kimi WebBridge) is visual context only; DOM-verified TradingView state verification remains audit-only.
- Large adjudicated human gold datasets are still not loaded at scale.
- Machine Learning (XGBoost) and predictive models remain in research status and are not decision authority.

## Current Release Candidate

- Release ID: `colleague-core-rc0`
- Status: research foundation with canonical runtime and reconciled governance
- Live execution: disabled
- Paper execution: disabled
- Predictive authority: not certified

## Prohibited Claims

Do not claim guaranteed profitability, a foolproof strategy, certain future price prediction, human-grade gold truth from AI labels, or live trading readiness. Passing tests means code behaved as specified; it does not prove market correctness.

## Next Approved Milestone

Complete the compact Perception and Annotation Readiness Bridge, BR-001 through
BR-006. The bridge must prove reproducibility, candle/timeframe truth,
provenance, benchmark separation, governed AI roles, and an independent human
structure pilot before authoritative structure semantics are redesigned.

**BR-001 to BR-003 local foundation (2026-07-10):**
- Canonical perception no longer imports legacy engine/rules/mtf/case-library authority indirectly.
- PerceptionEngineV2 loads detector-only `PERCEPTION_DETECTOR_CONFIG_V2`.
- `market_truth_certificate_v1` binds every completed 1H/4H/1D candle to exact 15m source rows and decision time.
- The AI is central to semantic hierarchy, causal episodes, alternatives, ambiguity, and annotation selection, but has no candle, coordinate, invariant-bypass, trade-promotion, or execution authority.
- BTCUSDT deterministic baseline fingerprint `92a25a13e0da2c153994fc00ca8546b256b388910fb3871fcb8cb66bfea66944` reproduced exactly.
- Final validation reached 799 passed, 1 skipped after retaining one failed contamination-guard attempt. Readiness remains closed until BR-004 through BR-006.

**WP-0042 to WP-0044 foundation reconciliation (2026-07-10):**
- WP-0042 froze commit `554e499` and preserved the WP-0041A re-audit in `stash@{0}`.
- WP-0043 established `smc_desk.colleague.orchestrator_v3` as canonical and passed with the explicit limitation that full CLI mapping remains deferred.
- WP-0044 restored the preserved WP-0041A code, retained the stash as recovery evidence, and reconciled it with WP-0043.
- Validation history is append-only and source-bound; the generic `latest_validation` claim is prohibited.
- Both controlling PDFs are present and SHA-256 registered. The companion repository is historical and non-authoritative.
- `smc_desk.mtf` is mixed transitional authority: deterministic resampling remains canonical while old snapshot helpers are comparison-only.
