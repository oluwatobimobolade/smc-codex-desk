from __future__ import annotations

from PIL import Image

from smc_desk.vision.visual_proof import evaluate_tradingview_screenshot


def test_blank_tradingview_screenshot_is_unverified(tmp_path):
    path = tmp_path / "BTCUSDT_1h.png"
    Image.new("RGB", (1280, 720), color=(18, 18, 18)).save(path)

    report = evaluate_tradingview_screenshot(
        screenshot_path=path,
        symbol="BTCUSDT",
        timeframe="1h",
        metadata={"symbol": "BTCUSDT", "timeframe": "1h"},
    )

    assert report["image_exists"] is True
    assert report["image_opened"] is True
    assert report["candles_visible"] is False
    assert report["blank_or_loading"] is True
    assert report["visual_status"] == "VISUAL_CONTEXT_UNVERIFIED"
    assert report["review_required"] is True
