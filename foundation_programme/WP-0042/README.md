# WP-0042 — Immutable Baseline and Repository Census

**Gate:** `GATE-BASELINE-CENSUS-001`
**Status:** Baseline frozen; census complete; pre-outputs 1–7 in progress.
**Date:** 2026-07-10

---

## 1. Frozen baseline

| Field | Value |
|---|---|
| Commit (HEAD) | `554e499` |
| Branch | `wp-0012a-remove-legacy-authority` |
| Tracked file count | 706 |
| Worktree status (post-freeze) | clean (only `foundation_programme/` untracked) |

Frozen commit message: `WP-0041 + WP-0041A: professional AI SMC annotation planner and integrity repair`

## 2. Preserved dirty work (do not lose)

Prior to freeze, the working tree contained 22 files of in-progress WP-0024 / WP-0041A / XAUUSD offline-tool work. This was stashed, not discarded.

| Field | Value |
|---|---|
| Stash ref | `stash@{0}` |
| Stash label | `WIP on wp-0012a-remove-legacy-authority: 554e499 WP-0041 + WP-0041A: …` |
| Files affected | 22 |
| Patch size | 1073 lines |
| Recovery command | `git stash pop` (only after WP-0042 baseline is accepted) |
| Backup of stash contents | `stash_show_patch.txt`, `stash_show_files.txt` |

**Rollback safety net:** reflog shows `554e499` reachable; `git reset --hard 554e499` returns to frozen state.

## 3. Repository contents (this artefact)

```
WP-0042/
├── README.md                      ← this file
├── branch_baseline.txt            ← "wp-0012a-remove-legacy-authority"
├── head_baseline.txt              ← "554e4997e520615735aa6f6daa136746f3bc252c"
├── head_before_freeze.txt         ← same value (HEAD did not move)
├── tree_status_baseline.txt       ← clean working tree
├── stash_inventory.txt            ← "stash@{0}: WIP …"
├── stash_show_files.txt           ← list of 22 stashed files
├── stash_show_patch.txt           ← full unified diff of stashed work
├── file_manifest.tsv              ← SHA-256 + classification of all 706 tracked files
├── file_manifest.tsv.bak          ← backup of manifest
├── dirty_tree_status_before.txt   ← status captured just before stash
├── dirty_tree_status_v2.txt       ← duplicate capture
├── dirty_err.txt                  ← stderr capture (empty)
├── environment_fingerprint.txt    ← git/python/uname versions
```

## 4. File-classification summary (from `file_manifest.tsv`)

| Class | Count | Authority status |
|---|---:|---|
| `code_source` (smc_desk/) | 224 | authoritative |
| `test_source` (tests/) | 159 | authoritative |
| `governance_source` (governance/) | 107 | authoritative |
| `tool_source` (tools/) | 98 | authoritative |
| **unclassified** (top-level *.md/*.json, .opencode/skills, etc.) | 40 | **needs_review** |
| `generated_evidence` (analysis_runs/, backtests/, outputs/, rendering_examples/, blackbox_gauntlet/) | 23 | non_authority |
| `governance_evidence` (evidence/, governance/INCIDENTS, RELEASES, ADR, WORK_PACKAGES) | 14 | authoritative |
| `strategy_active` (strategies/active/) | 13 | authoritative |
| `spec_source` (specs/) | 11 | authoritative_if_active |
| `research_reference` (research_transcripts/) | 11 | non_authority |
| `prompt_source` (prompts/) | 5 | authoritative |
| `report_evidence` (reports/current/) | 1 | authoritative |

**Total:** 706 (matches `git ls-files | wc -l`).

## 5. Unclassified files — review queue

The 40 files landing in `unclassified` are tracked but do not match any classification rule. These are top-level artefacts (PHASE3/4/5 rendering/vision reports, .opencode skills, top-level opencode.json, sample data, etc.) and require manual triage. They will be reclassified in **WP-0047 (Dataset, Artefact, and Release Separation)** when source / data / evidence / transient layers are defined.

## 6. Environment fingerprint (from `environment_fingerprint.txt`)

```
git version 2.x
Python 3.14.x (project .venv)
<uname -a line>
```

## 7. Authority conflict signals found during census

These will be expanded in pre-output #4 (conflicting authority claims) but are flagged now:

1. Two `VALIDATION_REGISTRY.json` files exist (`smc-codex-desk/evidence/` is rich; `smc-live-market-truth-integration/evidence/` is a stub). The latter is the legacy companion repo and should be archived.
2. `governance/DOCUMENT_INDEX.yaml` references `/Users/tobimobolade/Downloads/SMC Codex Desk.pdf` and `/Users/tobimobolade/Downloads/Master Strategy Truth Audit.pdf` as **controlling authority**, but `Master Strategy Truth Audit.pdf` was not found on disk during inspection — needs verification.
3. `governance/README_FIRST.md` still says "Next Approved Work: WP-0001-COLLEAGUE-FOUNDATION", but the actual work queue in `NEXT_ACTIONS.yaml` is at WP-0041. Stale pointer.
4. `governance/STRATEGY_TRUTH_AUDIT.md` self-describes as "initial WP-0001 audit scaffold. This is not the final full repository strategy audit." — contradicts any "audit complete" claims.
5. Three orchestrator generations exist: `smc_desk/colleague/orchestrator.py`, `orchestrator_v2.py`, `orchestrator_v3.py`. Only `orchestrator_v3` is the active canonical path per `CURRENT_STATE.yaml`, but the older ones are still importable.

## 8. Pre-output roadmap (per programme doc §3)

| # | Output | Path | Status |
|---|---|---|---|
| 1 | Immutable repository census | this file + `file_manifest.tsv` | **DONE** |
| 2 | Source/data/evidence/transient classification | columns in `file_manifest.tsv` | **DONE** (refinement belongs to WP-0047) |
| 3 | Import and call graph | `foundation_programme/pre_outputs/03_import_call_graph.md` | **DONE** |
| 4 | List of conflicting authority claims | `foundation_programme/pre_outputs/04_conflicting_authority_claims.md` | **DONE** (8 items, A–H) |
| 5 | Reproducibility gap report | `foundation_programme/pre_outputs/05_reproducibility_gap.md` | **DONE** |
| 6 | Proposed canonical runtime | `foundation_programme/pre_outputs/06_canonical_runtime.md` | **DONE** |
| 7 | Risk-ranked implementation sequence | `foundation_programme/pre_outputs/07_risk_ranked_plan.md` | **DONE** |

## 9. Acceptance criteria for `GATE-BASELINE-CENSUS-001`

- [x] HEAD pinned and recorded (`554e499`).
- [x] SHA-256 manifest covers all 706 tracked files.
- [x] Classification column present and consistent.
- [x] Dirty-tree work preserved (stash + patch backup).
- [x] Environment fingerprint captured.
- [x] Pre-outputs 3–7 written into `foundation_programme/pre_outputs/`.

## 10. Headline findings (for WP-0043)

- **R1 risk** (authority leakage): `orchestrator.py` v1 still imports `smc_desk.rules.RuleConfig`; `tools/analyze_live_dual_lens.py` still imports `smc_desk.engine`. Both must be locked behind boundary tests.
- **R3 risk** (governance drift): `VALIDATION_REGISTRY.json` `latest_validation.id` is `WP-0022` even though WP-0041 is committed; `README_FIRST.md` `Next Approved Work` still points at `WP-0001`; `STRATEGY_TRUTH_AUDIT.md` self-describes as "initial".
- **R6 risk** (repro): no `poetry.lock` / `uv.lock` / `requirements.lock`, no `.github/workflows`, no `entry_points` in `pyproject.toml`, `requires-python >= 3.12` but actual env is Python 3.14.
- **R2 risk** (data truth): status taxonomy partially defined in WP-0046 design but not yet enforced at the canonical loader; needs WP-0046 fixture coverage.
- **R4 risk** (holdout): `smc_desk/evaluation/holdout_guard.py` exists per `orchestrator.py` imports, but technical isolation (separate path with no `import` reachability) is not yet enforced.

These are the seeds for **WP-0043 (Canonical Runtime and Authority Consolidation)** which becomes the highest-risk-target in the sequence.

## 11. Rollback instructions

If WP-0042 is rejected:

```
cd /Users/tobimobolade/smc-codex-desk
rm -rf foundation_programme/
git reset --hard 554e499   # tree returns to clean WP-0041A WP-0041 commit
```

To recover the in-progress (currently stashed) work:

```
git stash pop
```

Both commands verified against the current reflog.