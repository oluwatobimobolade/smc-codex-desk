# Phase 4 Vision Infrastructure Report

## Implemented Infrastructure

The blind vision evaluation pipeline has been fully implemented in the `smc_desk/vision/` package. The pipeline separates clean visual observations from engine annotations, providing a controlled environment for testing and evaluating vision capabilities.

### Package Architecture

1. **`schemas.py`**: Discriminated Pydantic models for `VisionResponse`, `VisionObject`, and `BoundingBox` to force structured outputs.
2. **`provider_interface.py` & `provider_registry.py`**: Clean abstractions decoupling the domain models from specific cloud/LLM providers (supports mock, Gemini, OpenAI, etc.).
3. **`prompt_templates.py`**: Immutable, versioned prompt templates for Role A (External Chart Reader) and Role B (Internal Visual Auditor).
4. **`image_validation.py`**: Integrity verification checking size, format, orientation, and image file hashes.
5. **`response_store.py`**: Writes raw response files, prompts, and parsed schemas into attempt directories. Computes hashes and locks them as immutable.
6. **`blind_reader.py`**: Runs the blind-first reading process, validating review-mode images (no engine annotations) before sending requests.
7. **`overlay_auditor.py`**: Runs auditor checks on the rendered chart (detects overlaps, missing tags, and incorrect visual boundaries).
8. **`reconciliation.py`**: Performs multi-dimensional, object-level spatial-temporal reconciliation between vision, engine V2, and human gold objects.
9. **`confidence.py`**: Computes reported confidence queues for sorting and inspecting model behaviors.
10. **`vision_audit.py`**: Enforces the authority mode check and manages `CalibrationCertificate` logic.

---

## Tested Technical Behavior

The test suite in [test_v4_vision.py](file:///Users/tobimobolade/smc-codex-desk/tests/test_v4_vision.py) validates the infrastructure:

1. **Clean Image Read Order**: Verified that the Blind Reader enforces clean image validation before any overlay or audit steps are permitted.
2. **Immutability Lock**: Verified that once a blind response is parsed and saved, its attempt directory is locked and cannot be modified.
3. **Overlay Isolation**: Verified that the Overlay Auditor writes to a separate path and cannot overwrite the blind reading response.
4. **Authority Mode default**: Verified that the system defaults to `observe_only` and refuses startup with higher authority modes unless a valid `CalibrationCertificate` is present.
5. **Input Validation**: Verified that corrupted files, incorrect hashes, and dimension mismatches are rejected with explicit errors.
6. **Out-of-bound Pixel Rejection**: Verified that coordinate bounds on `BoundingBox` must be strictly between `0.0` and `1.0` (normalized format), and Pydantic validation raises errors for out-of-bounds coordinates.
7. **Reconciliation Mechanics**: Verified object-level temporal/spatial matching.

**Pass Count**: 5 / 5 test suites passed successfully.

---

## Untested Model Accuracy

* **Statement**: **Vision model accuracy is currently UNTESTED.**
* **Explanation**: No vision accuracy, performance metrics, or alpha assertions are made in this phase. The infrastructure is ready, but the vision model is not certified to make decisions.

---

## Work Blocked on Human Gold Labels

* **Status**: **Calibration Incomplete**
* **Blocked Items**: Scoring vision precision, recall, and false-positive rates remains blocked until the independent human-adjudicated gold set is completed and uploaded.

---

## Known Limitations

1. **OCR Limitations**: Visual review checks verify overall file dimensions and hashes, but OCR validation of text cleanlines is simulated/dry-run in this phase due to heavy library dependencies.
2. **Provider Mocking**: Evaluation is tested using deterministic mock schemas. Live model evaluation will depend on third-party API reliability and model-specific parsing errors.

---

## Security & Provenance Controls

* **Hash Locking**: The response store computes SHA-256 hashes of the raw response, parsed json, prompt text, and manifest configuration. These are stored in `hashes.json` with `immutable: true`.
* **Separate Attempts**: Provider retries generate fresh attempt IDs and save to unique subdirectories, preserving history for auditing.
* **Separation of Concerns**: Strategy, P&L, and trade plans are fully hidden from the vision prompts and schemas.

---

## Exact Authority Mode

```python
vision_authority_mode = "observe_only"
```

* **Veto Gating**: Enforced strictly. The system defaults to `observe_only`. In this mode, no vision outputs are permitted to change engine calculations, confidence scores, target levels, or verdicts.
* **Calibration Gate**: Startup with `calibrated_veto` or `full_fusion` will raise a `ValueError` unless a signed `CalibrationCertificate` is provided. No certificate exists currently.
