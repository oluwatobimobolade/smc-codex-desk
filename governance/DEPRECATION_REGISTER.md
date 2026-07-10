# Deprecation Register

This register marks suspected non-authority material. It does not delete or
move files. Archive or deletion requires a dry-run cleanup plan and approval.

## Suspected Legacy Or Superseded Strategy Authority

- `strategies/smc/SMC_ELITE_STRATEGY.md`
- `strategies/smc/house_rules.md`
- `smc_elite_prompt.md`
- old A/A+ grading instructions inside legacy reports or prompts
- old fixed 3R promotion proposals

Status: pending repository authority audit.

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
- `smc_desk.rules` (entire module) — legacy rule system.
- `smc_desk.mtf` — legacy MTF helpers; superseded by `smc_desk.perception.formal_structure_graph`.
  Note: WP-0043 removed the blanket allow for this filename from the boundary
  checker; each importer must be individually justified.
