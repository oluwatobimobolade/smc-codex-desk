# Current Architecture Snapshot

## Product Shape

SMC Codex Desk is currently a research-stage dual-lens market-colleague system.
It has useful pieces but is not yet a single canonical orchestrator.

## Active Components

- Market data: local Binance USD-M futures OHLCV under `data/ohlcv/binance_futures`.
- Timeframe reconstruction: `smc_desk/mtf.py`, `tools/derive_htf_from_15m.py`.
- Legacy analysis engine: `smc_desk/engine.py`.
- Perception V2: `smc_desk/perception/`.
- Rendering: `smc_desk/render.py`, `smc_desk/rendering/`.
- WebBridge capture: `tools/smc_webbridge_analyst.py`, `smc_desk/vision/kimi_webbridge.py`.
- Review lab: `tools/build_local_case_lab.py`, `tools/build_desktop_ai_review_packet.py`.
- Market-colleague package slice: `tools/run_market_colleague_case.py`.

## Transitional Dependencies

`tools/run_market_colleague_case.py` currently depends on the legacy engine for
its primary trade plan. PerceptionEngineV2 exists but is not yet the primary
orchestration source.

## Authority Boundaries

Market truth and deterministic geometry have higher authority than engine
narrative, AI/vision observations, or trader story. Prediction and execution
remain disabled/research-only.

## Main Gaps

- No final `analysis_runs/<run_id>/` package contract.
- No complete MTF structural graph.
- No scenario tree contract implementation.
- No verified Kimi TradingView controller.
- No official human-adjudicated perception metrics at sufficient scale.
- No certified predictive/economic edge.
