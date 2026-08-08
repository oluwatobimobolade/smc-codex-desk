# WP-0041A Annotation Integrity Repair - Final Report

## Status: COMPLETE / PASS / RE-AUDITED 2026-07-10

WP-0041A is the integrity repair for the WP-0041 professional AI SMC annotation planner. Where WP-0041 delivered the V2 schema, validator, renderer preference, and artifacts, WP-0041A enforces that every drawn mark is mechanically true, the chart stops narrating at the viewer, and a real downgrade-only critic audits the actual rendered scene before it is accepted.

The formal structure graph remains the hard authority. The visual critic can only remove clutter or request review; it has no promotion path.

## Defects Addressed

Each defect was identified in the WP-0041 review and then verified to be repaired by a focused adversarial test.

### P1: Evidence grounding was too weak

The validator only checked that an `evidence_id` existed; it did not check that the drawn price, span, scope, kind, and type matched that source object. The defect was reproducible: moving a valid BOS to `999999` at unrelated candles still returned `VALIDATED`.

**Repair.** New `smc_desk/brain/annotation_evidence.py` builds a canonical `AnnotationEvidenceAnchor` index from detector candidates and the formal graph active range. Each anchor carries exact price, price band, start/end timestamps, timeframe, direction, structure scope, kind, and source location. The validator now requires the V2 object to match its source anchor within an 8-basis-point price tolerance and a two-candle span tolerance. Mismatches emit `annotation_v2_structure_price_mismatch`, `annotation_v2_structure_span_mismatch`, `annotation_v2_poi_price_mismatch`, `annotation_v2_poi_span_mismatch`, `annotation_v2_liquidity_price_mismatch`, or `annotation_v2_liquidity_span_mismatch`.

**Adversarial test.** `test_wp0041a_rejects_real_evidence_id_with_invented_bos_geometry` rebuilds the original failure (BOS moved to `999999`) and asserts both mismatch issues and `REVIEW_REQUIRED`.

### P1: AI visual self-review was not yet real

The saved `annotation_self_review.md` was a static text summary of validator status, not a second critic looking at the rendered chart for clutter, overlap, bad anchoring, or mismatch.

**Repair.** New `smc_desk/brain/annotation_visual_critic.py` runs `review_annotation_scene` over the actual built scene, checks visible labels, drawing object density per chart template, overlap risk between nearby labels (within 10 candles and 3.5% of price span), and emits a structured `professional_smc_annotation_visual_review_v1` payload. The orchestrator saves the payload as `14_clean_annotation_render/annotation_visual_review.json` and rebuilds `annotation_self_review.md` from the real critic result rather than a static summary. The critic authority is `downgrade_or_cleanup_only` and it never promotes.

**Adversarial tests.** `test_wp0041a_visual_critic_requests_cleanup_for_overlapping_marks` asserts the critic returns `CLEANUP_REQUIRED` with the weaker overlapping object in `cleanup_object_ids`. `test_wp0041a_trade_box_is_v2_native_and_suppresses_legacy_text` asserts a clean V2 trade-ready scene returns critic status `PASSED`.

### P2: Renderer was visually wrong for professional standard

The chart carried generic warning banners, a footer, and explanatory text panels that overwhelmed the actual markup.

**Repair.** The renderer now reports `legacy_labels_suppressed` and `level_source=annotation_plan_v2` when V2 drawing objects are present. Banner and footer rendering paths gate on `level_source != "annotation_plan_v2"` so a V2 chart carries only chart-native marks and the thesis carries the explaining text.

### P2: Live planner was conservative, not the full SMC planner

The live planner was content to mark active-range liquidity, a watch invalidation, and a path. It did not yet rank and select certified BOS/CHoCH, OB, FVG, IDM, and liquidity candidates into a real trader-style composition.

**Repair.** New `smc_desk/brain/annotation_candidate_composer.py` is a deliberate selector (not a second detector). It picks at most four evidence-grounded marks from the certified active POI, the latest visible external structure break on the 15m chart, the active-range boundary liquidity, and a conditional path that is only emitted when there is a certified active POI in a path-allowed state.

**Adversarial test.** `test_wp0041a_path_requires_a_certified_active_poi` removes the active POI and confirms the path emission is blocked at the validator level even if the AI submitted it.

### P2: V2 trade-box was incomplete

It was gated correctly but did not yet model and render a coherent V2 entry/SL/TP trade-box object independently of legacy trade-plan details.

**Repair.** The validator now runs `_check_trade_box_geometry` so a V2 `trade_box` is rejected if `entry_price`, `stop_price`, or `target_prices` do not match the validated entry/stop/target plans within tolerance. The renderer scene reports `level_source`, `show_trade_box`, and `legacy_labels_suppressed` so the box is genuinely drawn from the V2 plan.

### P2: Test coverage was narrower than the written plan

**Repair.** Twelve focused WP-0041A tests now cover coordinate-to-evidence matching, scope/label mismatch, path-without-POI, native V2 trade box, visual-critic cleanup, wick-probe rejection, active watch-POI selection, critic-enforced hard downgrade, empty-V2 legacy suppression, bounded one-candle POI display, off-window evidence rejection, and candle-replayed POI consumption.

## 2026-07-10 Re-Audit Repairs

The first WP-0041A report correctly described the architecture but overstated several guarantees. A fresh live smoke and source audit found the following remaining defects and repaired them.

- Evidence anchors did not carry confirmation, activity, mitigation, or wick-probe state. These fields are now indexed and enforced. Candidate or wick-only structure cannot become BOS/CHoCH; unconfirmed or terminal POIs cannot become active zones.
- The local runner passed `active_poi=None`, so the composer could not emit a real OB/FVG even when one existed. It now selects a confirmed, visible, non-terminal 15m watch POI inside the certified active range. The selection creates no execution authority.
- A visual-critic `REVIEW_REQUIRED` result was written but did not change the official decision. It now hard-downgrades the official state and strips entry, stop, targets, and trade-box authority.
- Cleanup retained the pre-cleanup verdict. The critic now reruns after cleanup and records both the initial and final verdict.
- An empty V2 plan fell back to legacy clutter. Presence of the V2 schema now suppresses legacy labels, levels, banners, and generic paths even when no V2 objects are selected.
- One-candle POIs at the left chart edge rendered as unreadable slivers. The renderer preserves exact evidence geometry but gives the displayed zone a capped 6-12 candle local width. It never becomes a full-width ray.
- The offline XAU helper accepted future candles relative to its stale cutoff and could combine inconsistent native HTFs. It now treats 15m as canonical, trims by closed-candle decision time, derives completed HTFs only, validates OHLC geometry, and labels the run `OFFLINE_STALE_DEMO`, never live.
- Thesis wording previously said no POI was available after the selector found one. The live provider now distinguishes a mapped watch POI from absent entry confirmation and explicitly explains active-range direction conflicts.
- Evidence indices were calculated on a 120-candle pack while the official chart rendered 240 candles, shifting valid marks left. Official chart rendering now uses the exact evidence-window length, and timestamp geometry always overrides raw indices.
- `index_for_time` previously snapped timestamps outside the evidence window to index 0 or the last candle. Out-of-window evidence now has no chart index and is rejected by both the selector and validator.
- Order-block lifecycle fields remain incomplete in the detector. The annotation authority now independently replays all subsequent visible candles and rejects POIs that were consumed or invalidated; partial touches are labeled honestly.

## Pipeline Wiring

The repair is fully wired end-to-end.

- `smc_desk/rendering/smc_trader_annotation_renderer.py` imports `apply_visual_cleanup` and calls it on every rendered scene. `build_smc_trader_annotation_scene` populates `legacy_labels_suppressed`, `level_source`, `visible_labels`, `visible_drawing_object_count`, and embeds the visual critic payload under `visual_critic`.
- `smc_desk/colleague/orchestrator_v3.py` writes the critic payload as `annotation_visual_review.json`, runs `validate_annotation_plan_v2` and writes `annotation_validation.json`, writes `annotation_plan_v2.json`, and rebuilds `annotation_self_review.md` from the critic result and validation issues.
- `tools/run_live_ai_smc_full_system.py` imports `compose_local_annotation_plan_v2` and attaches the composed plan to the AI decision so the live path produces evidence-grounded V2 markup rather than generic range decoration.

## Validation

- Focused WP-0041A tests: `12 passed`.
- WP-0041 + WP-0041A combined: `17 passed`.
- Extended annotation, graph, POI, MTF, decision-time, and offline-replay suite: `126 passed`.
- Focused integrity plus decision-time tests: `25 passed`.
- Compileall: `passed`.
- `git diff --check`: `passed`.
- Full pytest: `760 passed, 1 skipped` in `132.44s`.
- Offline XAU smoke: validated `OFFLINE_STALE_DEMO`; canonical 15m was trimmed at the decision cutoff and only completed HTFs were derived.
- Fresh GBPUSD smoke: `VALIDATED / WATCH_ONLY`; fresh 15m OB mapped at its true July 10 origin without entry/SL/TP, range-direction conflict disclosed, sparse chart passed visual critic.

## Evidence

- Test report: `governance/WORK_PACKAGES/WP-0041A-ANNOTATION-INTEGRITY-REPAIR/TEST_REPORT.json`
- Adversarial tests: `tests/test_wp0041a_annotation_integrity_repair.py`
- Composition module: `smc_desk/brain/annotation_candidate_composer.py`
- Evidence anchor module: `smc_desk/brain/annotation_evidence.py`
- Validator: `smc_desk/brain/annotation_plan_validator.py`
- Visual critic: `smc_desk/brain/annotation_visual_critic.py`
- Renderer cleanup integration: `smc_desk/rendering/smc_trader_annotation_renderer.py` (`apply_visual_cleanup`, `legacy_labels_suppressed`)
- Orchestrator wiring: `smc_desk/colleague/orchestrator_v3.py` (`annotation_visual_review.json`, `annotation_self_review.md`)
- Live runner wiring: `tools/run_live_ai_smc_full_system.py` (`compose_local_annotation_plan_v2`)
- Re-audit report: `reports/current/WP0041A_ANNOTATION_INTEGRITY_REAUDIT_20260710.md`
- Fresh GBPUSD chart: `analysis_runs/WP0041A_REAUDIT_20260710/LIVE_FINAL_VERIFIED/LIVE_FULL_SYSTEM_AI_SMC_V3_20260710_082247/GBPUSD/14_clean_annotation_render/GBPUSD_official_ai_annotation.png`

## Final Truth

WP-0041A does not create trading edge, execution authority, or live readiness. It makes the AI-driven professional annotation planner mechanically honest: every mark must be traceable to a real SMC object, the chart carries only sparse chart-native marks, and a real critic can reject clutter or contradiction before the chart is accepted. The formal graph remains the single authority over both the AI's decisions and the human-readable markup.
