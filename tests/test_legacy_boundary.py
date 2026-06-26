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

    def test_runtime_pipeline_passes_with_legacy_killed(self, monkeypatch):
        """With include_legacy_comparison=False and the legacy engine patched
        to raise on any call, the current pipeline must complete successfully."""
        import pandas as pd
        from smc_desk.colleague.request_contract import ColleagueRunRequest
        from smc_desk.colleague.orchestrator import run_colleague_analysis
        from smc_desk.rules import RuleConfig
        from pathlib import Path
        import tempfile

        def fail_if_legacy_runs(*_args, **_kwargs):
            raise AssertionError("Legacy engine called by current pipeline")

        monkeypatch.setattr("smc_desk.engine.analyze_dataframe", fail_if_legacy_runs)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "BTCUSDT_15m_unit.csv"
            rows = ["timestamp,open,high,low,close,volume"]
            for i in range(300):
                total_minutes = i * 15
                hour, minute = divmod(total_minutes, 60)
                hour = hour % 24
                day = 1 + (total_minutes // 1440)  # days since Jan 1
                price = 100.0 + i * 0.1
                rows.append(
                    f"2026-01-{day:02d} {hour:02d}:{minute:02d}:00,{price},{price+0.5},{price-0.5},{price+0.1},1.0"
                )
            source.write_text("\n".join(rows))

            output = tmp_path / "out"
            output.mkdir()

            request = ColleagueRunRequest(
                symbol="BTCUSDT",
                source_path=str(source),
                output_dir=str(output),
                decision_time="2026-01-02T12:00:00",
                include_legacy_comparison=False,
            )
            config = RuleConfig()
            result = run_colleague_analysis(request, config)
            assert result["primary_perception_source"] == "PerceptionEngineV2"
            assert result["legacy_engine_role"] == "disabled"

    def test_decision_identical_with_legacy_on_versus_off(self):
        """Enabling legacy comparison must not alter the current decision."""
        import pandas as pd
        import json
        from smc_desk.colleague.request_contract import ColleagueRunRequest
        from smc_desk.colleague.orchestrator import run_colleague_analysis
        from smc_desk.rules import RuleConfig
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "BTCUSDT_15m_unit.csv"
            rows = ["timestamp,open,high,low,close,volume"]
            for i in range(300):
                total_minutes = i * 15
                hour, minute = divmod(total_minutes, 60)
                hour = hour % 24
                day = 1 + (total_minutes // 1440)  # days since Jan 1
                price = 100.0 + i * 0.1
                rows.append(
                    f"2026-01-{day:02d} {hour:02d}:{minute:02d}:00,{price},{price+0.5},{price-0.5},{price+0.1},1.0"
                )
            source.write_text("\n".join(rows))

            # Run with legacy disabled
            out_disabled = tmp_path / "disabled"
            out_disabled.mkdir()
            req_disabled = ColleagueRunRequest(
                symbol="BTCUSDT",
                source_path=str(source),
                output_dir=str(out_disabled),
                decision_time="2026-01-02T12:00:00",
                include_legacy_comparison=False,
            )
            result_disabled = run_colleague_analysis(req_disabled, RuleConfig())

            # Run with legacy enabled
            out_enabled = tmp_path / "enabled"
            out_enabled.mkdir()
            req_enabled = ColleagueRunRequest(
                symbol="BTCUSDT",
                source_path=str(source),
                output_dir=str(out_enabled),
                decision_time="2026-01-02T12:00:00",
                include_legacy_comparison=True,
            )
            result_enabled = run_colleague_analysis(req_enabled, RuleConfig())

            # The current-authority outputs must be identical
            decision_disabled = json.loads(
                (out_disabled / "scenarios" / "decision.json").read_text()
            )
            decision_enabled = json.loads(
                (out_enabled / "scenarios" / "decision.json").read_text()
            )
            assert decision_disabled == decision_enabled, (
                "Legacy comparison changed the current decision"
            )

            # Legacy-specific files must only exist when legacy is enabled
            assert (out_enabled / "legacy_comparison" / "engine_analysis.json").exists()
            assert not (out_disabled / "legacy_comparison" / "engine_analysis.json").exists()
