import pytest
import json
from unittest.mock import MagicMock
from smc_desk.vision.provider_registry import registry
from smc_desk.vision.overlay_auditor import OverlayAuditor

def test_render_auditor_flags_discrepancy():
    mock_provider = MagicMock()
    mock_response = json.dumps({
        "audit_id": "1", "case_id": "c1", "blind_response_ref": "br1",
        "provider": "mock", "model": "mock", "rendering_defects_found": True,
        "reported_defects": [{"type": "missing_fvg_box", "description": "missing"}],
        "style_mismatch_detected": False, "labels_obscured": False, "created_at": "2026-06-24T00:00:00Z"
    })
    mock_provider.read_chart.return_value = (mock_response, MagicMock())
    registry.register("mock", mock_provider)
    
    auditor = OverlayAuditor(store_dir="tests/vision/cases")
    
    result = auditor.audit_overlay(
        case_id="c1",
        annotated_image_path="dummy.png",
        clean_image_path="dummy_clean.png",
        scene_graph_dict={"fvg_bullish": []},
        manifest_payload={},
        blind_response_id="br1",
        provider_name="mock",
        model_name="mock",
        dry_run=True,
        mock_audit_str=mock_response
    )
    
    assert result["rendering_defects_found"] is True
    assert len(result["reported_defects"]) == 1

def test_render_auditor_passes_clean_chart():
    mock_provider = MagicMock()
    mock_response = json.dumps({
        "audit_id": "2", "case_id": "c2", "blind_response_ref": "br2",
        "provider": "mock", "model": "mock", "rendering_defects_found": False,
        "reported_defects": [],
        "style_mismatch_detected": False, "labels_obscured": False, "created_at": "2026-06-24T00:00:00Z"
    })
    mock_provider.read_chart.return_value = (mock_response, MagicMock())
    registry.register("mock", mock_provider)
    
    auditor = OverlayAuditor(store_dir="tests/vision/cases")
    
    result = auditor.audit_overlay(
        case_id="c2",
        annotated_image_path="dummy.png",
        clean_image_path="dummy_clean.png",
        scene_graph_dict={"fvg_bullish": []},
        manifest_payload={},
        blind_response_id="br2",
        provider_name="mock",
        model_name="mock",
        dry_run=True,
        mock_audit_str=mock_response
    )
    
    assert result["rendering_defects_found"] is False
    assert len(result["reported_defects"]) == 0
