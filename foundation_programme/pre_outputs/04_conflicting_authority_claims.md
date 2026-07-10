# Conflicting Authority Claims (WP-0042 pre-output #4)

Generated 2026-07-10 against frozen baseline `554e499`.

This document enumerates claims in the governance record that **disagree with each other or with the actual repository state**. None of these are excuses to skip work — they are the targets WP-0043 / WP-0044 / WP-0045 must reconcile.

## A. Conflicting "next work" pointers

| Source | Says | Actual |
|---|---|---|
| `governance/README_FIRST.md` § "Next Approved Work" | "WP-0001-COLLEAGUE-FOUNDATION" | `NEXT_ACTIONS.yaml` shows priority 1 = WP-0012A (legacy isolation) and priority 41 = WP-0041 (annotation planner) both already COMPLETE; priority 24 = WP-0024-NEXT is `status: next` |
| `governance/STRATEGY_TRUTH_AUDIT.md` first line | "initial WP-0001 audit scaffold. This is not the final full repository strategy audit." | (no contradictory override; flag as still-initial) |

## B. Test-count discrepancies

| Source | Claims |
|---|---|
| `evidence/VALIDATION_REGISTRY.json` latest_validation.commands | `523 passed, 1 skipped in 86.34s` (WP-0022) |
| `governance/CURRENT_STATE.yaml` known_constraints | mentions `389/405/426/453 test-count records as historical provenance` |
| `governance/WORK_PACKAGES/WP-0041-PROFESSIONAL-AI-SMC-ANNOTATION-PLANNER/TEST_REPORT.json` | `740 passed, 1 skipped` |
| The actual frozen baseline `554e499` test count | **must be re-verified** under WP-0045 against the clean install path before claiming any count |

These are not all "conflicts" — they are successive milestones. But the registry's `latest_validation.id` is fixed at WP-0022, which is misleading. WP-0044 must update the registry to either track latest by date or remove the misleading "latest" pointer.

## C. Two `VALIDATION_REGISTRY.json` files exist

| Path | Status |
|---|---|
| `smc-codex-desk/evidence/VALIDATION_REGISTRY.json` | rich, machine-readable per-WP commands, latest_validation.id = WP-0022 |
| `smc-live-market-truth-integration/evidence/VALIDATION_REGISTRY.json` | stub: only `{"status":"PASS","suites":…}` |

The `smc-live-market-truth-integration/` companion repo still ships a stub registry. WP-0047 must decide whether it stays (as a frozen archive) or is moved out of the canonical release.

## D. Document Index references PDFs that may be missing

`governance/DOCUMENT_INDEX.yaml` external_controlling_sources:

```
- /Users/tobimobolade/Downloads/SMC Codex Desk.pdf
- /Users/tobimobolade/Downloads/Master Strategy Truth Audit.pdf
```

`Master Strategy Truth Audit.pdf` is named as a **controlling authority** but was not observed on disk during census. WP-0044 must verify presence; if absent, governance must explicitly note "unavailable" rather than "controlling".

## E. Three orchestrator generations, one is canonical

Files present: `smc_desk/colleague/orchestrator.py`, `orchestrator_v2.py`, `orchestrator_v3.py`.

Current state: `orchestrator_v3` is the canonical per `CURRENT_STATE.yaml`. v1 still imports `smc_desk.rules.RuleConfig` — **a reachability path to legacy rules**. v2 imports `smc_desk.data.truth_validator` and `decision.*` packages (the V6 stack).

WP-0043 must add a boundary test that fails if `orchestrator.py` (v1) or `orchestrator_v2.py` is reachable from the canonical chain.

## F. Permission matrix vs. actual gates

`governance/AUTHORITY_MATRIX.yaml` `may_grant_live_execution_authority: []` (empty list — no one can grant).

Actual orchestrator flags observed: `--allow-shallow-context`, `--allow-stale`, `--bias` — none of these change the empty-list permission. This is consistent but should be asserted under WP-0043 authority-boundary tests.

## G. Stale config references

- `governance/OPEN_RISKS.md` and `governance/FAILURE_REGISTER.md` should be cross-checked against WP-0029 + WP-0041 final reports (they may not yet reference those milestones).
- `opencode.json` at repo root is at least partly AI-provider configuration; its authority status is **not classified** in current governance and is part of the 40 `unclassified` files in the manifest.

## H. Legacy engine reachability

`tools/analyze_live_dual_lens.py` still imports `from smc_desk.engine import analyze_dataframe, load_ohlcv_csv`. This is the **legacy engine entry point** used by the dual-lens runner, and it is *not* part of the WP-0040 graph-authority run. WP-0043 must either:

- (a) Move `tools/analyze_live_dual_lens.py` to a `tools/legacy_dual_lens/` subdir and tag it `comparison_only`, **or**
- (b) Add an authority-boundary test that fails if `tools/run_live_ai_smc_full_system.py` (the canonical AI SMC V3 path) imports `smc_desk.engine`.

---

**Status:** 8 distinct conflicts enumerated. Each becomes an explicit input into WP-0043 / WP-0044 / WP-0045.