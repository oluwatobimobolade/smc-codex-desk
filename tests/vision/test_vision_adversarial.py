import pytest
import json
from unittest.mock import MagicMock
from smc_desk.vision.provider_registry import registry
from smc_desk.vision.blind_reader import BlindReader

def test_prompt_injection_resilience():
    mock_provider = MagicMock()
    valid_resp = json.dumps({
        "response_id": "test", "case_id": "c1", "provider": "mock", "model": "mock",
        "prompt_version": "1", "schema_version": "1", "chart_valid": True,
        "metadata_read": {"symbol": "BTC", "timeframe": "15m", "venue": "binance", "latest_visible_timestamp": "2026", "scale_type": "linear", "price_labels_legible": True, "time_labels_legible": True, "is_cropped": False, "indicators_obscure_price": False}, "structure_read": "bearish",
        "detected_objects": [], "overall_confidence": 0.8, "created_at": "2026-06-24T00:00:00Z"
    })
    mock_provider.read_chart.return_value = (valid_resp, MagicMock())
    registry.register("mock", mock_provider)
    reader = BlindReader(store_dir="tests/vision/cases")
    
    import smc_desk.vision.blind_reader as br
    original_val = br.validate_image_file
    br.validate_image_file = lambda *args, **kwargs: {"valid": True, "errors": []}
    
    manifest = {"image_hash": "dummy", "chart_width": 1920, "chart_height": 1080}
    reader.read_blindly("c1", "dummy.png", "mock", "mock", manifest, dry_run=False)
    
    called_prompt = mock_provider.read_chart.call_args[0][1]
    assert "hallucinate" in called_prompt.lower() or "price" in called_prompt.lower() or "guess" in called_prompt.lower()
    
    br.validate_image_file = original_val

def test_extreme_crop_handling():
    mock_provider = MagicMock()
    mock_response = json.dumps({
        "response_id": "test", "case_id": "c1", "provider": "mock", "model": "mock",
        "prompt_version": "1", "schema_version": "1", "chart_valid": False,
        "metadata_read": {"symbol": "BTC", "is_cropped": True}, "structure_read": "unknown",
        "detected_objects": [], "overall_confidence": 0.0, "created_at": "2026-06-24T00:00:00Z"
    })
    mock_provider.read_chart.return_value = (mock_response, MagicMock())
    registry.register("mock", mock_provider)
    
    reader = BlindReader(store_dir="tests/vision/cases")
    
    import smc_desk.vision.blind_reader as br
    original_val = br.validate_image_file
    br.validate_image_file = lambda *args, **kwargs: {"valid": True, "errors": []}
    
    manifest = {"image_hash": "dummy", "chart_width": 1920, "chart_height": 1080}
    result = reader.read_blindly("c1", "dummy.png", "mock", "mock", manifest, dry_run=True, mock_response_str=mock_response)
    
    assert result.chart_valid is False
    assert result.metadata_read.is_cropped is True
    
    br.validate_image_file = original_val
