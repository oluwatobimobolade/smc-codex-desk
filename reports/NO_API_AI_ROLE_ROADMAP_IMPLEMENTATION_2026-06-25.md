# No-API AI Role Roadmap Implementation Report

Generated: 2026-06-25

## Purpose

The attached roadmap describes how AI can gradually take over reviewer,
adjudicator, rule-evolution, orchestration, and eventually paper/live trading
roles. The implementation here adapts that roadmap to the current constraint:
no external model API. The system must use local files, generated charts,
manual/desktop AI review, Kimi/TradingView visual inspection when needed, and
strict promotion gates.

The long-term aim remains the same: build a disciplined SMC market colleague
that can reconstruct charts from data, compare them with TradingView, annotate
structure correctly, reason through market state, forecast only when evidence
supports it, and abstain when the edge is not measurable.

## What Was Added

### 1. Desktop AI Review Packets

Added `tools/build_desktop_ai_review_packet.py`.

This creates no-API packets that can be used in Codex, Claude desktop, or any
manual local AI workflow. Each packet contains:

- clean chart image references;
- the case identity and decision time;
- a response JSON template matching the perception annotation schema;
- references to the annotation manual and ontology.

It intentionally excludes:

- `machine_analysis.json`;
- `engine_weak_labels.json`;
- engine overlays;
- future candles.

This allows AI to act as an independent blind reviewer without contaminating
the label process.

### 2. Human Reviewer Agreement Measurement

Added `tools/measure_review_agreement.py`.

This reads two independent reviewer files across a case lab and computes:

- overall precision, recall, and F1;
- per-primitive precision, recall, and F1;
- eligible case count;
- skipped case reasons.

This becomes the baseline an AI reviewer must meet or beat before being
promoted from helper to trusted first-pass reviewer.

### 3. Adjudicated Dataset Export

Added `tools/export_adjudication_dataset.py`.

This exports only cases with `label_status=adjudicated` into JSONL training
rows. It includes:

- clean chart paths;
- reviewer A/B annotations;
- final adjudicated labels;
- adjudicator written justification;
- weak engine label provenance;
- case manifest / source references.

It refuses to create training rows from reviewer drafts or engine weak labels
alone.

### 4. Adjudicator Justification Capture

Updated `tools/build_perception_gold_batch.py`.

Each new `adjudicated.json` now includes:

```json
"adjudicator_justification": ""
```

This is required for future adjudicator training, because the model should
learn not only the final label but why the final label was chosen.

### 5. Local Lab Documentation

Updated `specs/LOCAL_FIRST_RESEARCH_LAB.md` with the new workflow commands:

- build desktop AI review packets;
- measure human reviewer baseline;
- export adjudicated training rows.

## Generated Artifacts

### 100-Case Local Lab

Built:

```text
case_library/local_first_lab/20260625
```

Contents:

- 100 perception candidate cases;
- 20 cases each for BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT;
- 100 `case_manifest.json` files;
- 100 `engine_weak_labels.json` files;
- 400 clean raw chart images.

Important: these are not gold labels yet. They are the blind review lab.

### Desktop AI Packets

Built:

```text
backtests/perception/desktop_ai_packets/20260625
```

Contents:

- 100 prompt files;
- 100 response template JSON files;
- 1 packet manifest.

Verification:

- packet count: 100;
- mode: `desktop_ai_no_api`;
- first prompt does not contain `machine_analysis`;
- first prompt does not contain `engine_weak_labels`.

### Reviewer Agreement Baseline

Built:

```text
backtests/perception/reviewer_agreement/20260625
```

Current result:

```text
status: insufficient_reviewer_annotations
eligible_cases: 0
```

This is correct. The reviewer files have been created but not filled yet, so
the system refuses to invent a human baseline.

### Adjudication Dataset Export

Built summary:

```text
datasets/perception/adjudicated_cases_20260625.summary.json
```

Current result:

```text
status: no_adjudicated_rows
rows: 0
```

This is also correct. No adjudicated labels exist yet, so no training dataset
is valid yet.

## Validation

Focused tests:

```bash
.venv/bin/python -m pytest tests/test_local_first_roadmap.py tests/test_perception_gold_batch.py -q
```

Result:

```text
9 passed
```

Full project tests:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
342 passed in 75.22s
```

Compile check:

```bash
.venv/bin/python -m compileall -q smc_desk tools tests
```

Result: passed.

Scoped diff hygiene:

```bash
git diff --check -- tools/measure_review_agreement.py tools/export_adjudication_dataset.py tools/build_desktop_ai_review_packet.py tools/build_perception_gold_batch.py specs/LOCAL_FIRST_RESEARCH_LAB.md tests/test_local_first_roadmap.py
```

Result: passed.

## What This Achieves Toward the Final Colleague

The system can now create its own clean chart lab from market data, package
those charts for blind human or desktop-AI review, measure whether reviewers
agree, and export only adjudicated truth for future local model training.

This is the foundation for an AI reviewer/adjudicator that earns authority
instead of being trusted by vibes.

The system is now closer to the target colleague because it can:

- recreate charts from OHLCV;
- preserve clean chart evidence;
- separate engine perception from adjudicated truth;
- prepare charts for AI/human visual inspection without API use;
- measure reviewer reliability;
- prepare training data only after adjudication;
- keep live/predictive authority disabled until evidence exists.

## What Is Still Not Proven

- No AI reviewer is promoted yet.
- No AI adjudicator is promoted yet.
- No rule-evolution controller has authority yet.
- No profitable market edge has been proven by this work.
- No future market prediction can be claimed as reliable from this alone.

The next honest proof step is annotation, not signal-calling.

## Immediate Next Step

Start filling the reviewer packets:

```text
backtests/perception/desktop_ai_packets/20260625
```

For each case:

1. Open the prompt markdown.
2. Inspect the clean chart images.
3. Fill the response JSON as `desktop_ai_reviewer` or copy the template for a
   second reviewer.
4. Compare two reviewer files.
5. Fill `adjudicated.json` with final labels and justification.
6. Re-run:

```bash
.venv/bin/python tools/measure_review_agreement.py \
  --root case_library/local_first_lab/20260625 \
  --output-dir backtests/perception/reviewer_agreement/20260625

.venv/bin/python tools/export_adjudication_dataset.py \
  --root case_library/local_first_lab/20260625 \
  --output datasets/perception/adjudicated_cases_20260625.jsonl
```

Only after that can we begin honestly evaluating whether a local/desktop AI
reviewer can match the human baseline.
