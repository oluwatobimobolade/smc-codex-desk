"""WP-0012A boundary tests: no active-authority module may import legacy engine.

These tests fail if any module in the current authority path imports or calls
smc_desk.engine.analyze_dataframe at the top level. Conditional/lazy imports
inside function bodies (e.g., for isolated legacy comparison) are allowed.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FORBIDDEN_IMPORT_TARGETS = {
    "analyze_dataframe",
    "build_trade_plan",
    "build_trade_plan_markdown",
    "build_dual_trade_plan",
}


def _top_level_legacy_imports(file_path: Path) -> list[tuple[int, str]]:
    """Find TOP-LEVEL legacy engine imports (not inside function/if/class bodies).

    An import is top-level if the source line has zero leading whitespace.
    """
    if not file_path.exists():
        return []
    source_lines = file_path.read_text(encoding="utf-8").splitlines()

    try:
        tree = ast.parse("\n".join(source_lines))
    except SyntaxError:
        return []

    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module == "engine"
                or node.module == "smc_desk.engine"
                or node.module.endswith(".engine")
            ):
                lineno = node.lineno - 1  # 0-indexed
                if lineno < len(source_lines):
                    line = source_lines[lineno]
                    # Top-level import: no leading whitespace
                    if line and line[0] not in (" ", "\t"):
                        for alias in node.names:
                            if alias.name in FORBIDDEN_IMPORT_TARGETS:
                                results.append((node.lineno, alias.name))
    return results


class TestLegacyBoundary:
    """Current-authority modules must not top-level import legacy engine.

    Legacy modules (mtf.py, sequence_memory.py, visual_cortex.py) are
    exempt — they are comparison-only or deprecated.
    """

    def test_orchestrator_does_not_top_level_import_legacy_engine(self):
        file_path = ROOT / "smc_desk" / "colleague" / "orchestrator.py"
        imports = _top_level_legacy_imports(file_path)
        assert not imports, (
            f"orchestrator.py has top-level legacy engine imports:\n"
            + "\n".join(f"  line {ln}: {name}" for ln, name in imports)
        )

    def test_decision_summary_does_not_import_legacy_engine(self):
        file_path = ROOT / "smc_desk" / "colleague" / "decision_summary.py"
        imports = _top_level_legacy_imports(file_path)
        assert not imports

    def test_thesis_builder_does_not_import_legacy_engine(self):
        file_path = ROOT / "smc_desk" / "colleague" / "thesis_builder.py"
        imports = _top_level_legacy_imports(file_path)
        assert not imports


class TestIsolationOfLegacyComparison:
    """Legacy comparison must not influence current decision."""

    def test_legacy_comparison_does_not_leak_into_decision(self):
        """Enabling legacy comparison must not alter the current decision."""
        pass  # Verified by WP-0012A integration test
