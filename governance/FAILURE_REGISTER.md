# Failure Register

Negative evidence is project memory and must not be hidden.

## Known Failure Themes

- Broad SMC open-rule baselines failed to prove robust positive expectancy.
- Watch geometry was previously over-interpreted as trade validation.
- Fixed 3R and high win-rate claims were not proven.
- ML scorer/prediction modules remain unvalidated scaffolding.
- A false bullish CHoCH/BOS reading happened when internal structure was
  allowed to override protected/external structure.
- Native Binance HTF data can disagree with internally derived HTF metadata;
  canonical 15m reconstruction is therefore the source-consistent path.
- WP-0002 confirms the package builder works, but it does not prove predictive
  edge, chart-state equivalence with TradingView, or complete SMC semantic
  perception.
- WP-0003 intentionally makes screenshot-only TradingView manifests fail strict
  alignment. Passing alignment now requires verified chart state or OHLCV
  overlap evidence.
- WP-0011 initially broke strict TradingView alignment because live-shadow
  passed last-closed candle open time into a new availability-time slicer. The
  repair now passes last-closed candle close time and validates the saved ETH
  manifest with zero blocking failures.
- Before WP-0012, `decision.json` and `scenario_tree.json` still consumed the
  legacy engine trade plan even though governance described legacy as
  comparison-only. WP-0012 adds a no-legacy run mode and tests that the current
  decision layer does not use the legacy trade plan.
- WP-0013 produced 50 resolved cases, but all were `NO_SETUP`. This must not be
  presented as signal performance, win rate, profit factor, or validated edge.
- WP-0014 produced review templates only. Blank reviewer files are not human
  agreement and not gold truth.
- WP-0015 found the runtime ontology monolith still contains strategy/risk
  fields. Split contracts exist, but runtime migration remains incomplete.
- WP-0016 completed the runtime config migration, but the BTCUSDT live-shadow
  attempt failed to acquire verified current OHLCV. Kimi/TradingView visual
  screenshots succeeded, TradingView OHLCV timed out, Binance REST failed DNS,
  and browser-side Binance fetch failed. The correct output was no live signal,
  no trade, and zero capital risk.
- The other-AI/V4 transfer reconciliation found a real local FVG blocker:
  `smc_desk/perception/fvg.py` had an indentation syntax error, a local
  `FairValueGapObject` shadowed the canonical ontology object, and FVG terminal
  lifecycle transitions could conflict. WP-0017C repaired this and restored the
  current local full-test baseline to `469 passed, 1 skipped`.
- `governance/NEXT_ACTIONS.yaml` had duplicate keys that collapsed two action
  items. WP-0017C split the malformed item and added duplicate-key regression
  coverage.
- WP-0020 first produced a correct `PARTIAL_PASS` when TradingView/Kimi visual
  capture was skipped; that run is preserved under
  `analysis_runs/WP0020_MARKET_COLLEAGUE_GAUNTLET_BTCUSDT_SKIP_PARTIAL/`.
  The canonical rerun captured four TradingView screenshots and passed visual
  audit availability, but the screenshots are still not market truth and candle
  timing remains not DOM-verified.

## Required Treatment

- Preserve reports and data hashes.
- Convert important failures into regression tests where feasible.
- Do not rename failed ideas as new strategies without explicit evidence.
