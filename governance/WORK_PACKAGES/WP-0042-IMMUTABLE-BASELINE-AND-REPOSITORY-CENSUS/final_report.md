# WP-0042 — Immutable Baseline and Repository Census

**Gate:** `GATE-BASELINE-CENSUS-001`
**Status:** ACCEPTED
**Date:** 2026-07-10
**Baseline commit:** `554e499`

## Summary

The repository was frozen at `554e499` (on branch `wp-0012a-remove-legacy-authority`) and an immutable file-level census was produced. All seven pre-outputs required by the Foundation Stabilisation & Readiness Programme were delivered into `foundation_programme/`.

## What was delivered

| Artefact | Path | Purpose |
|---|---|---|
| Baseline record | `foundation_programme/WP-0042/README.md` | Frozen commit, dirty-tree preservation, classification summary, headline findings |
| SHA-256 file manifest | `foundation_programme/WP-0042/file_manifest.tsv` | 706 files, classification column, authority status |
| Dirty-tree preservation | `stash@{0}`, `stash_show_patch.txt`, `stash_show_files.txt` | WP-0024 / WP-0041A / offline XAUUSD tool work recovered post-`stash -u` |
| Pre-output #1 census | `WP-0042/README.md` § 4 | file-class breakdown (12 classes) |
| Pre-output #2 classification | `file_manifest.tsv` columns 5–6 | source/data/evidence/transient partitioning + authority status |
| Pre-output #3 import/call graph | `pre_outputs/03_import_call_graph.md` | three orchestrator generations, CLI routing, legacy reachability |
| Pre-output #4 conflicting authority claims | `pre_outputs/04_conflicting_authority_claims.md` | 8 distinct conflicts (A–H) |
| Pre-output #5 reproducibility gap | `pre_outputs/05_reproducibility_gap.md` | pyproject, requirements, lockfiles, CI, entry points, .gitignore |
| Pre-output #6 proposed canonical runtime | `pre_outputs/06_canonical_runtime.md` | canonical chain diagram, authority boundary rules, release artefacts |
| Pre-output #7 risk-ranked plan | `pre_outputs/07_risk_ranked_plan.md` | R1–R8 risk model and binding execution order |

## Authority signals (for WP-0043)

- **R1 authority leak:** `orchestrator.py` v1 still imports `smc_desk.rules.RuleConfig`; `tools/analyze_live_dual_lens.py` imports `smc_desk.engine.analyze_dataframe`. Boundary tests required.
- **R3 governance drift:** `VALIDATION_REGISTRY.json` `latest_validation.id` is fixed at `WP-0022` while WP-0041 is the actual current pass.
- **R6 repro:** no lockfile, no CI, no `entry_points`, `requires-python>=3.12` vs. venv Python 3.14.
- **R2 data:** status taxonomy designed in programme but not enforced in canonical loader.
- **R4 holdout:** no technical isolation yet.

## Next WP

**WP-0043 Canonical Runtime and Authority Consolidation** begins immediately. Targets the R1 risk class (highest risk × highest cost).

## Rollback instructions

```
cd /Users/tobimobolade/smc-codex-desk
rm -rf foundation_programme/
git reset --hard 554e499
git stash pop                # restore stashed WP-0024/WP-0041A work
```

## Evidence inventory

All WP-0042 outputs are committed under `foundation_programme/` as durable, greppable artefacts. The SHA-256 manifest is regenerable at any time from `git ls-files` against the frozen HEAD.