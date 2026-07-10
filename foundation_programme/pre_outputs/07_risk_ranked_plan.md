# Risk-Ranked Implementation Sequence (WP-0042 pre-output #7)

Generated 2026-07-10 against frozen baseline `554e499`.

Risk = (probability of silently corrupting the system) × (cost of corruption). The ranking below drives the order: we tackle highest-risk first, lowest-risk last.

## Risk model

| Class | Example | Rank |
|---|---|---|
| **R1** — Silent authority leakage | Legacy engine reaches canonical run; old orchestrator runs under wrong flag | **highest** |
| **R2** — Silent data corruption | Partial HTF candle counted as complete; duplicate timestamp accepted; future row included | **highest** |
| **R3** — Silent governance drift | Two registries, two test totals, two README pointers all live | **high** |
| **R4** — Holdout leakage | AI/developer accidentally reads protected data; prompt sees holdout labels | **high** |
| **R5** — AI runtime drift | Model/prompt versions mixed across runs; no provenance | **medium** |
| **R6** — Repro gap | No lockfile, no CI, no canonical command | **medium** |
| **R7** — Gold-set ambiguity | Reviewer disagrees, adjudication not preserved | **medium** |
| **R8** — Artefact release bloat | Source release ships 2 GB of generated runs | **low** |

## Implementation order (matches programme WPs)

| Order | WP | Title | Primary risk class | Why this slot |
|---|---|---|---|---|
| 1 | **WP-0042** | Immutable Baseline and Repository Census | R3 | Locks the starting point so every later WP is diffable. |
| 2 | **WP-0043** | Canonical Runtime and Authority Consolidation | **R1** | Authority leakage is the single highest-risk failure mode — fix it before anything else. |
| 3 | **WP-0044** | Governance and Evidence Reconciliation | R3 | Registry/test-count drift means the system doesn't know what passed; gates become meaningless. |
| 4 | **WP-0045** | Reproducible Environment, Test Taxonomy, CI | R6 | Without reproducible install, every prior WP can regress silently. |
| 5 | **WP-0046** | Canonical Data Truth Certification | **R2** | Partial/duplicate/future rows corrupt validation and any "edge" claim. |
| 6 | **WP-0047** | Dataset, Artefact, and Release Separation | R8 | Once data + governance are clean, separating release layers is mechanical. |
| 7 | **WP-0048** | Holdout and Experiment Firewall | **R4** | Protected data is the trust anchor for all future perception claims. |
| 8 | **WP-0049** | Governed AI Runtime Foundation | R5 | AI provenance is needed before any AI run can be cited. |
| 9 | **WP-0050** | Human Gold and Review Operations | R7 | Gold set is the only path to truth-vs-claim adjudication. |
| 10 | **WP-0051** | Foundation Acceptance Gauntlet | all | Final adversarial gate. Must reference every prior gate's evidence. |

## Gate-skips are not allowed

The programme doc states: "Do not skip a failed gate." The risk ranking above implies a stronger constraint:

- **R1, R2, R4 failures block all downstream perception work** regardless of other gate results.
- An R3 (governance drift) failure must be reconciled before WP-0045 can claim a reproducible environment (because "reproducible" presupposes "we agree on what's reproducible").

## Dependency graph

```
WP-0042 ──► WP-0043 ──► WP-0044 ──► WP-0045
              │             │           │
              ▼             ▼           ▼
            WP-0046 ◄── (gate)    WP-0047
              │
              ▼
            WP-0048 ──► WP-0049 ──► WP-0050 ──► WP-0051
```

Specifically:
- WP-0046 (data truth) needs WP-0045's CI taxonomy (otherwise tests can't be classified).
- WP-0048 (holdout firewall) needs WP-0047 (release separation) so protected data can be physically isolated.
- WP-0049 (governed AI) needs WP-0043's authority_trace infrastructure (so AI calls inherit the trace).
- WP-0050 (gold ops) needs WP-0047 (release separation) and WP-0049 (provenance) so reviewer packs carry authoritative traces.
- WP-0051 (foundation gauntlet) consumes every prior gate's `TEST_REPORT.json` / final_report.md as inputs.

## Rollback policy

For each WP:

1. Every gate's evidence file (`final_report.md` + `TEST_REPORT.json` + manifests) is committed to `governance/WORK_PACKAGES/WP-XXXX…/`.
2. The pre-WP HEAD is recorded in the work package's `README.md`.
3. Rollback = `git reset --hard <pre-WP-HEAD>`; the gate's manifests remain in the work-package directory for re-application if desired.

## Stretch risks (programme acknowledges but does not sequence)

- "Three generations of orchestrators" is one specific instance of a broader pattern (multiple stacks frozen at different points in time). WP-0043's boundary tests are the first defence; a future "single source of truth for perception" programme may be needed.
- ML scorer / prediction code remains research scaffolding per `FAILURE_REGISTER.md` and is explicitly **out of scope** for this foundation programme.

## Acceptance for the risk-ranked plan

The plan above is approved if WP-0042 baseline freeze succeeds (`GATE-BASELINE-CENSUS-001`). Once approved, the order in the table is the binding execution sequence.