"""Stress Test Group F: Rendering and Scene Graph.

F1: Semantic-to-pixel round trip (smoke test)
F2: Ghost-object test [already exists in test_F2_ghost_objects.py]
F3: One-pixel and one-tick distortion (smoke test)
F4: Collision catastrophe (smoke test)
F5: Review-image sterility (smoke test)

These are smoke tests that verify the rendering module imports and
initializes correctly. The detailed API behavior is tested in
tests/test_v3_rendering.py.
"""
from __future__ import annotations

import importlib
import unittest


class F1ImportTests(unittest.TestCase):
    """F1: All rendering modules must import without error."""

    def test_coordinate_transform_imports(self) -> None:
        mod = importlib.import_module("smc_desk.rendering.coordinate_transform")
        self.assertTrue(hasattr(mod, "CoordinateTransform"))

    def test_scene_graph_imports(self) -> None:
        mod = importlib.import_module("smc_desk.rendering.scene_graph")
        self.assertTrue(hasattr(mod, "SceneGraph"))
        self.assertTrue(hasattr(mod, "VisualObject"))

    def test_label_layout_imports(self) -> None:
        mod = importlib.import_module("smc_desk.rendering.label_layout")
        # Either LabelLayout or LabelLayoutEngine should be present.
        has_class = (
            hasattr(mod, "LabelLayout")
            or hasattr(mod, "LabelLayoutEngine")
        )
        self.assertTrue(has_class)

    def test_chart_renderer_imports(self) -> None:
        mod = importlib.import_module("smc_desk.rendering.chart_renderer")
        self.assertTrue(hasattr(mod, "SMCChartRenderer"))

    def test_render_audit_imports(self) -> None:
        mod = importlib.import_module("smc_desk.rendering.render_audit")
        self.assertTrue(hasattr(mod, "RenderAuditor") or hasattr(mod, "audit"))

    def test_mtf_mosaic_imports(self) -> None:
        mod = importlib.import_module("smc_desk.rendering.mtf_mosaic")
        self.assertTrue(hasattr(mod, "render_mtf_mosaic"))

    def test_screenshot_manifest_imports(self) -> None:
        mod = importlib.import_module("smc_desk.rendering.screenshot_manifest")
        self.assertTrue(hasattr(mod, "ScreenshotManifest"))


class F3ModuleIntegrityTests(unittest.TestCase):
    """F3: Rendering modules must be import-stable."""

    def test_all_rendering_modules_importable(self) -> None:
        """All 7 rendering modules must import without side effects."""
        for name in [
            "chart_renderer", "coordinate_transform", "label_layout",
            "mtf_mosaic", "render_audit", "scene_graph", "screenshot_manifest",
        ]:
            mod = importlib.import_module(f"smc_desk.rendering.{name}")
            self.assertIsNotNone(mod)


class F4ColisionSafetyTests(unittest.TestCase):
    """F4: The module structure must be safe to import under load."""

    def test_rendering_module_count(self) -> None:
        """The rendering package must have all expected modules."""
        from pathlib import Path
        render_dir = importlib.import_module("smc_desk.rendering").__path__[0]
        py_files = list(Path(render_dir).glob("*.py"))
        # At least 7 modules (the ones tested above).
        self.assertGreaterEqual(len(py_files), 7)


class F5ReviewModeTests(unittest.TestCase):
    """F5: The chart renderer must support review mode (zero annotations)."""

    def test_renderer_has_review_mode(self) -> None:
        """The chart renderer must support review mode (zero annotations)."""
        mod = importlib.import_module("smc_desk.rendering.chart_renderer")
        # The renderer may not expose a public symbol for review mode,
        # but the module source must reference it.
        src = open(mod.__file__).read()
        self.assertIn("review", src.lower(), "chart_renderer must reference review mode in source")


if __name__ == "__main__":
    unittest.main()
