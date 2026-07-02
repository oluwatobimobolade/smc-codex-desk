from __future__ import annotations

import smc_desk.colleague.wp0020_gauntlet as gauntlet
from wp0029_fixtures import sample_df


def test_debug_chart_not_used_as_official_thesis(monkeypatch, tmp_path):
    class Analysis:
        def model_dump(self, mode="json"):
            return {"events": [], "zones": []}

    def fake_analysis(**_kwargs):
        return Analysis(), sample_df()

    def fake_render(_df, _analysis, output_path, min_conf="medium", title=None):
        from PIL import Image
        Image.new("RGB", (400, 240), color=(18, 22, 28)).save(output_path)

    monkeypatch.setattr(gauntlet, "run_legacy_annotation_analysis", fake_analysis)
    monkeypatch.setattr(gauntlet, "render_smc_annotated", fake_render)
    monkeypatch.setattr(gauntlet, "render_mtf_mosaic", lambda _dfs, _analyses, output_path, title="": fake_render(None, None, output_path))

    manifest, _ = gauntlet.render_smc_annotations(
        timeframe_dfs={tf: sample_df() for tf in gauntlet.TIMEFRAMES},
        symbol="BTCUSDT",
        output_dir=tmp_path,
        config=object(),
    )

    assert manifest["chart_authority"] == "debug_only_legacy_not_decision_authority"
    assert manifest["debug_only_banner"] == "DEBUG ONLY - not official trade thesis"
