# Phase 3 Rendering & Semantic Scene Graph Report

## Implemented Infrastructure

The Rendering and Semantic Scene Graph layer has been fully implemented inside the `smc_desk/rendering/` package. The system guarantees that every visual annotation drawn on a chart is traceably and deterministically mapped to a semantic object produced by `PerceptionEngineV2` without reinterpretation or invention.

### Modules Implemented

1. **`coordinate_transform.py`**:
   - Implements `CoordinateTransform` model to perform deterministic bidirectional transformations:
     - `time_to_x()`, `candle_index_to_x()`
     - `price_to_y()`
     - `x_to_time()`, `y_to_price()`
     - `bounding_box_for_price_zone()`, `bounding_box_for_candle_range()`
   - Fully stable and validated across identical reruns.

2. **`scene_graph.py`**:
   - Pydantic models for scene graph entries (`SceneGraph`, `VisualObject`, `PixelGeometry`, `MarketGeometry`).
   - Visual object IDs are derived deterministically from: `semantic_object_id`, `render_role`, `renderer_version`, and `panel_id`.
   - Supports shape types: `candlestick`, `horizontal_line`, `vertical_line`, `polyline`, `rectangle`, `marker`, `text_label`, `leader_line`, `shaded_region`.

3. **`screenshot_manifest.py`**:
   - Pydantic model (`ScreenshotManifest`) capturing full execution metadata (git commit, data hashes, price limits, plot bounds, engine versions, and final image hash).

4. **`label_layout.py`**:
   - Implements collision handling using a lane reservation and nudge algorithm.
   - Detects bounding box overlaps, nudges labels, draws leader lines when moved, and generates collision/omission reports rather than silently dropping labels.

5. **`mtf_mosaic.py`**:
   - Helper to build multi-timeframe mosaic grids in a clean, isolated fashion.

6. **`render_audit.py`**:
   - Audits that all annotations map 1-to-1 to a valid semantic object, prices align with ticks, timestamps are within range, and future causality is preserved.

7. **`chart_renderer.py`**:
   - Orchestrates the rendering pipeline across four distinct modes:
     - **Clean mode**: Candles, axes, and minimal neutral metadata only.
     - **Live perception mode**: Active swings, current protected structure, latest confirmed BOS/CHoCH, active FVGs.
     - **Audit mode**: All historical perception objects, historical lifecycle changes, and full ID annotations.
     - **Review mode**: Clean candles with stable axes and zero detector annotations (for blind human/vision annotation).

---

## Unsupported Features & Exclusions

* **Logarithmic Scales**: Not supported in this phase. The renderer explicitly checks for log scale configurations and raises a `ValueError` rather than silently rendering them linearly.
* **Prohibited SMC Objects**: No strategy elements (Order Blocks, liquidity sweeps, trade verdicts, grades, strategy targets, stop losses) are rendered. These are outside the validated vertical slice.

---

## Tests Run & Pass Counts

The test suite in [test_v3_rendering.py](file:///Users/tobimobolade/smc-codex-desk/tests/test_v3_rendering.py) verifies all Phase 3 requirements.

* **Coordinate Transform Roundtrips**: Passed.
* **FVG Boundary Accuracy**: Passed (exact tick alignment checked with Decimal).
* **BOS/CHoCH Connector Accuracy**: Passed.
* **Render Modes Isolation**: Passed (Clean & Review mode contains zero annotations).
* **Determinism**: Passed (identical reruns produce identical scene graphs and identical image bytes).
* **Render Auditor Validation**: Passed (referential integrity, tick sizes, bounds, and no future leakage).

**Pass Count**: 6 / 6 test suites passed successfully.
**Regression Test Suite**: All 211 tests in the repository remain fully green.

---

## Known Limitations

1. **Matplotlib Font Metrics**: Text bounding box dimensions are estimated using font metrics. Minor variations in layout may occur depending on system fonts and DPI rendering on different OS platforms.
2. **Lane Saturation**: If too many labels collide in a very narrow price zone, the layout engine nudges them up to the boundary, and any unresolved collisions are recorded in the omission report.

---

## Determinism Status

* **Status**: **Fully Deterministic**
* **Validation**: Verified by rendering identical inputs and asserting 100% equivalence of the serialized `SceneGraph` JSON and PNG image hashes. Non-deterministic Matplotlib metadata is stripped during conversion.

---

## Example Semantic-to-Pixel Mapping

```json
{
  "visual_object_id": "BTCUSDT-15m-FVG-fvg_1::zone-box::renderer-v1::panel-15m",
  "semantic_object_id": "fvg_1",
  "semantic_object_type": "fvg",
  "shape_type": "rectangle",
  "z_index": 1,
  "visibility_status": "visible",
  "pixel_geometry": {
    "x1": 154.2,
    "y1": 420.5,
    "x2": 182.9,
    "y2": 395.1
  },
  "market_geometry": {
    "start_time": "2026-06-23T13:30:00Z",
    "end_time": "2026-06-23T13:45:00Z",
    "price_low": 97.0,
    "price_high": 108.0
  },
  "style_token": "bearish_fvg_active"
}
```

---

## Unresolved Failures

* **None**: All Phase 3 acceptance gates have been fully satisfied and are green.
