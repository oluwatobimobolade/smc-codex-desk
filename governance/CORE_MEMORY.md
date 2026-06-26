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

- Legacy engine isolated behind `legacy_comparison.py` adapter. Runtime kill-switch
  and decision-invariance tests pass.
- MTF graph with per-timeframe completeness, rich relationships (RETRACES_WITHIN,
  PROTECTS, REFINES), and structural scope awareness.
- Canonical event ledger: duplicate suppression, replay idempotence, schema
  versioning, provisional vs confirmed separation.
- Generic decision pipeline: `smc_desk/decision/` package with strategy-state
  engine, evidence graph, and conservative decision policy (ABSTAIN/OBSERVE/WATCH).
  No PAPER_EXECUTE.
- 426 tests passing. Tagged `wp0012-abcd-complete`.

**Pipeline:** Live/Historical OHLCV → PEV2 (15m/1H/4H/1D) → Event Ledger →
MTF Graph → Strategy-State Engine → Evidence Graph → Decision.

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

- Binance USD-M BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, and BNBUSDT local OHLCV
  data exists.
- 15m is the canonical source; derived 1H/4H/1D can be built from it.
- Local-first case lab and desktop AI review packet tooling exist.
- Holdout guard exists.
- Reviewer/adjudication scaffolding exists.
- PerceptionEngineV2 detects swings, structure breaks, protected structure
  state, and FVGs with causality guards.
- Rendering and market-colleague case packaging exist.

## Known Flaws

- Governance files did not exist before WP-0001.
- `specs/PERCEPTION_ONTOLOGY_V2.yaml` still contains some strategy and risk
  parameters; these must be split without breaking the current engine.
- `tools/run_market_colleague_case.py` is a vertical slice, not the final
  orchestrator.
- Kimi WebBridge capture exists but is not yet a fully verified TradingView
  state controller.
- MTF graph, scenario contract, provisional/confirmed state split, and case
  similarity are incomplete.
- Human gold labels are not yet available at sufficient scale.
- Prediction models remain research-only.

## Current Release Candidate

- Release ID: `colleague-core-rc0`
- Status: research foundation
- Live execution: disabled
- Paper execution: disabled
- Predictive authority: not certified

## Prohibited Claims

Do not claim guaranteed profitability, a foolproof strategy, certain future
price prediction, human-grade gold truth from AI labels, or live trading
readiness. Passing tests means code behaved as specified; it does not prove
market correctness.

## Next Approved Milestone

Complete `WP-0001-COLLEAGUE-FOUNDATION`: governance, repository authority map,
current state, capability matrix, dataset registry, active strategy candidate
contract, baseline test report, and transition roadmap.
