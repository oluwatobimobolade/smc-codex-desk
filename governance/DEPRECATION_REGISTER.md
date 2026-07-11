# Deprecation Register

This register marks suspected non-authority material. It does not delete or
move files. Archive or deletion requires a dry-run cleanup plan and approval.

## Suspected Legacy Or Superseded Strategy Authority

- `strategies/smc/SMC_ELITE_STRATEGY.md`
- `strategies/smc/house_rules.md`
- `smc_elite_prompt.md`
- old A/A+ grading instructions inside legacy reports or prompts
- old fixed 3R promotion proposals

Status: `HISTORICAL`. These files are research evidence and cannot direct the
canonical runtime or override the active strategy research contract.

## Research Configs To Relocate Later

- `strategies/smc/rules_open.json`
- `strategies/smc/rules_widthfloor.json`
- `strategies/smc/rules_fvg_width50_partial_research.json`

Status: keep in place until manifests link each config to its result set.

## Comparison-Only Modules (WP-0043)

The following modules are explicitly tagged `comparison_only`. They may not be
imported from canonical-runtime code. They are retained for historical evidence
and side-by-side comparison runs. The authority-boundary checker
(`tools/check_authority_boundaries.py`) flags any other module that imports
them as a forbidden dependency.

- `smc_desk.colleague.orchestrator` (v1) — uses `smc_desk.rules.RuleConfig`.
- `smc_desk.colleague.orchestrator_v2` — earlier cognitive pipeline; superseded by v3.
- `tools/analyze_live_dual_lens.py` — imports legacy `smc_desk.engine`.
- `smc_desk.engine` (entire module) — pre-PerceptionEngineV2 rule engine.
- `smc_desk.rules` (entire module) — legacy/compatibility rule system; canonical
  PerceptionEngineV2 uses `smc_desk.perception.config`.
- `smc_desk.case_library` — historical case-builder surface that imports legacy
  analysis authority; pure hashing and OHLCV utilities now live under
  `smc_desk.data`.
- `smc_desk.mtf` — historical mixed strategy/MTF module. Pure resampling moved
  to `smc_desk.data.timeframe_reconstruction`.

## Historical Mixed-Authority Module

`smc_desk.mtf` remains available for comparison and older research tools, but
it is no longer permitted in the canonical perception import graph.

- Canonical equivalents: `smc_desk.data.timeframe_reconstruction` and
  `smc_desk.data.market_truth_certificate`.
- Historical/comparison helpers: `build_mtf_snapshot` and `snapshot_to_dict`.
- The formal structure graph owns semantic parent/child structure; it does not
  replace candle resampling.

BR-001/BR-002 closed the symbol-level loophole. Authority checks now reject the
whole `smc_desk.mtf` module from active packages.

## Non-Authoritative Companion Repository

- `/Users/tobimobolade/smc-live-market-truth-integration`

Status: `HISTORICAL` reference only. Its source files and validation registry
cannot define current authority and may not be imported by canonical runtime.
