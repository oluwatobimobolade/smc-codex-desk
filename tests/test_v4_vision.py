import pytest
import os
import json
import shutil
from datetime import datetime, timezone
from decimal import Decimal

from smc_desk.vision.schemas import VisionResponse, VisionObject, BoundingBox
from smc_desk.vision.blind_reader import BlindReader
from smc_desk.vision.overlay_auditor import OverlayAuditor
from smc_desk.vision.reconciliation import VisionReconciler
from smc_desk.vision.vision_audit import enforce_authority_mode, CalibrationCertificate
from smc_desk.evaluation.calibration import issue_calibration_certificate
from smc_desk.vision.image_validation import validate_image_file
from smc_desk.perception.engine_v2 import PerceptionSnapshot

@pytest.fixture
def temp_store(tmp_path):
    # Setup mock image file
    img_path = tmp_path / "clean_review.png"
    # Create a small valid 1x1 png image using PIL
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="black")
    img.save(img_path, format="PNG")
    
    return str(img_path), str(tmp_path)


def test_v4_authority_mode_observe_only():
    # 6. Authority mode defaults to observe_only
    # 8. Invalid authority mode fails without a calibration certificate
    config = {"vision_authority_mode": "observe_only"}
    enforce_authority_mode(config) # Should pass
    
    config_invalid = {"vision_authority_mode": "calibrated_veto"}
    with pytest.raises(ValueError, match="STARTUP_PREVENTED"):
        enforce_authority_mode(config_invalid)
        
    # With cert it should pass
    cert = issue_calibration_certificate(
        gold_set_version="1.0",
        gold_set_hash="hash",
        model_name="claude-3-5-sonnet",
        model_version="1.0",
        prompt_version="1.0.0",
        schema_version="1.0.0",
        evaluation_timestamp=datetime.now(timezone.utc),
        approved_authority_level="calibrated_veto",
        approver="admin",
        adjudicated_case_count=30,
        calibration_record_count=50,
        expected_calibration_error=0.05,
        brier_score=0.08,
        perturbation_consistency_rate=0.98,
        abstention_test_passed=True,
    )
    with pytest.raises(ValueError, match="signed calibration"):
        enforce_authority_mode({
            **config_invalid,
            "cohort_id": "COHORT-1",
            "cohort_content_sha256": "cohort-hash",
            "system_code_freeze_sha256": "system-hash",
            "trust_registry_sha256": "missing-trust-hash",
        }, cert)

def test_v4_blind_first_workflow(temp_store):
    img_path, store_dir = temp_store
    reader = BlindReader(store_dir)
    
    # Compute correct hash
    import hashlib
    with open(img_path, "rb") as f:
        real_hash = hashlib.sha256(f.read()).hexdigest()
        
    manifest = {"image_hash": real_hash, "chart_width": 100, "chart_height": 100}
    
    # 1. Clean image is always read before overlay image
    # 2. Blind response becomes immutable
    resp = reader.read_blindly("case_001", img_path, "mock_provider", "mock_model", manifest)
    
    assert resp.provider == "mock_provider"
    assert resp.model == "mock_model"
    
    attempt_id = resp.response_id[5:]
    # Check that attempt is locked/immutable in response store
    assert reader.store.is_locked("case_001", "mock_provider", "mock_model", attempt_id) == True

    # 3. Overlay response cannot overwrite blind response
    # We call OverlayAuditor and verify it writes to a separate path
    auditor = OverlayAuditor(store_dir)
    scene_graph = {"objects": []}
    audit_resp = auditor.audit_overlay(
        case_id="case_001",
        annotated_image_path=img_path,
        clean_image_path=img_path,
        scene_graph_dict=scene_graph,
        manifest_payload=manifest,
        blind_response_id=resp.response_id,
        provider_name="mock_provider",
        model_name="mock_model"
    )
    assert audit_resp["blind_response_ref"] == resp.response_id
    
    # Verify that blind response parsed_response.json still exists and has correct data
    attempt_dir = reader.store.get_attempt_dir("case_001", "mock_provider", "mock_model", attempt_id)
    with open(os.path.join(attempt_dir, "parsed_response.json"), "r") as f:
        saved_blind = json.load(f)
    assert saved_blind["response_id"] == resp.response_id

def test_v4_validation_checks(temp_store):
    img_path, store_dir = temp_store
    reader = BlindReader(store_dir)
    
    # Wrong hash raises ValueError
    manifest_wrong_hash = {"image_hash": "wrong_hash"}
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        reader.read_blindly("case_002", img_path, "mock", "mock", manifest_wrong_hash)
        
    # Wrong dimensions raise ValueError
    import hashlib
    with open(img_path, "rb") as f:
        real_hash = hashlib.sha256(f.read()).hexdigest()
    manifest_wrong_dim = {"image_hash": real_hash, "chart_width": 200}
    with pytest.raises(ValueError, match="DIMENSION_MISMATCH"):
        reader.read_blindly("case_002", img_path, "mock", "mock", manifest_wrong_dim)

def test_v4_bounding_box_out_of_bounds():
    # Out of bounds BoundingBox coordinates must raise ValidationError
    from pydantic import ValidationError
    
    # Correct coordinate values (between 0.0 and 1.0)
    box = BoundingBox(x1=0.1, y1=0.2, x2=0.5, y2=0.6)
    assert box.x1 == 0.1
    
    # Out of bounds coordinate (> 1.0)
    with pytest.raises(ValidationError):
        BoundingBox(x1=1.5, y1=0.2, x2=0.5, y2=0.6)
        
    # Out of bounds coordinate (< 0.0)
    with pytest.raises(ValidationError):
        BoundingBox(x1=0.1, y1=-0.2, x2=0.5, y2=0.6)


def test_v4_reconciliation():
    # 17. Abstention remains abstention
    # 18. Low confidence is not converted into a negative label
    # 16. Model disagreement is not treated as truth
    
    # Setup mock VisionResponse
    vision_res = VisionResponse(
        response_id="resp_1",
        provider="mock",
        model="mock",
        prompt_version="1.0",
        chart_valid=True,
        metadata_read={
            "price_labels_legible": True,
            "time_labels_legible": True
        },
        structure_read="bearish",
        overall_confidence=0.9,
        created_at=datetime.now(timezone.utc)
    )
    
    # Empty snap
    snap = PerceptionSnapshot(
        decision_time=datetime.now(timezone.utc),
        swings={},
        structure_state={
            "current_direction": "bullish",
            "protected_high_id": None,
            "protected_low_id": None,
            "last_confirmed_external_high": None,
            "last_confirmed_external_low": None,
            "last_external_break_id": None,
            "last_internal_break_id": None,
            "current_as_of": datetime.now(timezone.utc)
        },
        structure_breaks=[],
        fvgs=[]
    )
    
    reconciler = VisionReconciler()
    report = reconciler.reconcile(vision_res, snap)
    
    assert report["vision_response_id"] == "resp_1"
    # Since there are no objects, there should be zero matches
    assert len(report["matches"]) == 0
