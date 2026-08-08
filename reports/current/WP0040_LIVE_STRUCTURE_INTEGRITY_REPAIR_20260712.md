# WP-0040 Live Structure Integrity Repair

## Verdict

PASS for the repaired local observe-only path. This repair removes proven
structural falsehoods; it does not claim predictive edge or execution safety.

## Proven Defects Repaired

1. The formal graph copied one latest broken swing into both `protected_high`
   and `protected_low`.
2. That collapsed anchor could falsely promote a child move to
   `PARENT_BREAK_CONFIRMED`.
3. Detector state could retain the opposite protected side from an older
   regime, creating an inverted protected range.
4. The V3 orchestrator did not run the existing POI lifecycle before sealing
   evidence, leaving `active_pois` empty.
5. Canonical annotations used ambiguous `BOS`/`OB`/`FVG` labels instead of the
   certified timeframe, direction, scope, and object vocabulary.
6. Live manifests exposed candle-open timestamps without an explicit
   candle-close decision cutoff.

## Repairs

- Protected anchors are now resolved side by side from detector structure
  state and certified external swings. The trend-protected side is paired with
  the latest confirmed opposite swing; stale regime state is not reused.
- A new fatal invariant rejects a duplicated, collapsed, or inverted high/low
  pair. Parent-break replay refuses collapsed anchors.
- V3 now runs `build_mtf_structure_hierarchy` and
  `build_poi_lifecycle_by_timeframe` before evidence sealing and exports both
  `pois` and valid `active_pois`.
- The canonical annotation composer now uses
  `certified_annotation_semantic`, producing labels such as `15M BOS` and
  timeframe/direction-specific OB/FVG labels.
- Evidence summaries and live manifests now record `last_open_time`,
  `last_close_time`, and `decision_cutoff_semantics=closed_candle_time`.

## Validation

- Focused structure regressions: 22 passed.
- Focused plus integration regressions: 97 passed.
- Full suite: 943 passed, 1 skipped in 128.26 seconds.
- `compileall`: PASS.
- `git diff --check`: PASS.

## Fresh XRPUSDT Proof

Run: `analysis_runs/LIVE_FULL_SYSTEM_AI_SMC_V3_20260712_054854/XRPUSDT`

- Binance USD-M closed-candle data loaded for 15m, 1h, 4h, and 1d.
- Graph invariants: `PASS`, zero violations.
- Context: `PARENT_CHILD_CONFLICT`, therefore `THESIS_ONLY`.
- Hard validation issues: none.
- POI lifecycle population: 15m 3 active, 1h 7 active, 4h 2 active.
- Official chart uses a local `15M BOS` segment and no trade box.
- Live and paper execution remain disabled.

## Remaining Honest Limits

- Active POI existence does not mean a POI should be displayed or traded when
  final direction is mixed.
- The local deterministic provider is not a real LLM reasoning call.
- This validates structural integrity and refusal behavior, not win rate.
