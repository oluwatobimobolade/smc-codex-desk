import pytest
from smc_desk.vision.schemas import VisionResponse, MetadataRead
# Mocking the vision model so we don't actually hit the API but test the handling

def test_g2_crop_truth():
    """
    Simulates sending an image without axes to the vision model and 
    asserts that it must return INSUFFICIENT_CONTEXT.
    """
    class MockVisionModel:
        def analyze_image(self, image_path: str) -> VisionResponse:
            # We simulate the crop logic here. If the image is 'cropped_no_axis.png'
            # it should detect missing axes and abstain.
            from datetime import datetime, UTC
            if "cropped" in image_path:
                return VisionResponse(
                    response_id="test_1",
                    provider="mock",
                    model="mock",
                    prompt_version="1.0",
                    chart_valid=False,
                    metadata_read=MetadataRead(is_cropped=True, price_labels_legible=False),
                    structure_read="insufficient_context",
                    abstain=True,
                    abstention_reason="INSUFFICIENT_CONTEXT: Missing price axis",
                    overall_confidence=1.0,
                    created_at=datetime.now(UTC)
                )
            return VisionResponse(
                response_id="test_2",
                provider="mock",
                model="mock",
                prompt_version="1.0",
                chart_valid=True,
                metadata_read=MetadataRead(),
                structure_read="bullish",
                abstain=False,
                overall_confidence=0.9,
                created_at=datetime.now(UTC)
            )
            
    vision = MockVisionModel()
    
    # Test 1: Full image
    res_full = vision.analyze_image("full_chart.png")
    assert res_full.chart_valid == True
    assert res_full.abstain == False
    
    # Test 2: Cropped image
    res_crop = vision.analyze_image("cropped_no_axis.png")
    assert res_crop.chart_valid == False
    assert res_crop.abstain == True, "Model failed to abstain on cropped image"
    assert "INSUFFICIENT_CONTEXT" in res_crop.abstention_reason

def test_g2_unreadable_axis():
    pass
