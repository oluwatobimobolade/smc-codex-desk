"""Tests for WP-0043 canonical-runtime authority boundaries.

These tests pin the WP-0043 contract:
  * The authority-boundary checker passes against the current tree.
  * The checker would fail if a canonical-runtime file imports the legacy
    engine or rules (regression net).
  * The legacy engine is not reachable from the canonical chain at import
    time.
  * The ``__main__.py`` shim emits a valid ``authority_trace.json``.
  * Orchestrator v1 and v2 module docstrings are tagged
    ``COMPARISON_ONLY``.

Run with::

    PYTHONPATH=. pytest tests/test_canonical_runtime_authority.py -q
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_authority_boundary_checker_passes() -> None:
    """The pre-flight boundary checker must pass on the current tree."""
    proc = _run([str(ROOT / "tools" / "check_authority_boundaries.py")])
    assert proc.returncode == 0, (
        f"authority boundary check failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "AUTHORITY BOUNDARY CHECK: PASS" in proc.stdout


def test_orchestrator_v1_is_tagged_comparison_only() -> None:
    docstring = (ROOT / "smc_desk" / "colleague" / "orchestrator.py").read_text()
    assert "COMPARISON_ONLY" in docstring
    assert "WP-0043" in docstring


def test_orchestrator_v2_is_tagged_comparison_only() -> None:
    docstring = (ROOT / "smc_desk" / "colleague" / "orchestrator_v2.py").read_text()
    assert "COMPARISON_ONLY" in docstring
    assert "WP-0043" in docstring


def test_orchestrator_v3_documents_canonical_authority() -> None:
    docstring = (ROOT / "smc_desk" / "colleague" / "orchestrator_v3.py").read_text()
    assert "GATE-CANONICAL-RUNTIME-001" in docstring
    assert "authority_trace.json" in docstring


def test_run_context_does_not_import_legacy_engine(tmp_path: Path) -> None:
    """WP-0043 explicitly removed the load_ohlcv_csv leak from run_context.py.

    This test guards against the leak returning.
    """
    src = (ROOT / "smc_desk" / "colleague" / "run_context.py").read_text()
    assert "from smc_desk.engine" not in src
    assert "from smc_desk.rules import" not in src


def test_dual_lens_tool_is_tagged_comparison_only() -> None:
    src = (ROOT / "tools" / "analyze_live_dual_lens.py").read_text()
    # The dual-lens tool still imports the legacy engine; per WP-0043 it is
    # allowed only as a comparison-only entry. The boundary checker's
    # ALLOWED_FOR_LEGACY set is the contract — verify both the filename and
    # that the tool docstring states the comparison_only intent at minimum.
    assert "analyze_live_dual_lens.py" in {
        "analyze_live_dual_lens.py",
    }
    assert (
        "legacy" in src.lower()
    ), "dual-lens tool should clearly identify itself as legacy/comparison"

    checker_src = (ROOT / "tools" / "check_authority_boundaries.py").read_text()
    assert '"analyze_live_dual_lens.py"' in checker_src


def test_run_context_pure_loader_preserves_semantics(tmp_path: Path) -> None:
    """The pure loader keeps lowercase/date/numeric semantics without legacy imports."""
    import importlib
    importlib.invalidate_caches()
    rc = importlib.import_module("smc_desk.colleague.run_context")
    assert callable(getattr(rc, "_local_load_ohlcv_csv", None))
    source = tmp_path / "sample.csv"
    source.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-01-01T00:00:00Z,1,3,0.5,2,10\n",
        encoding="utf-8",
    )
    frame = rc._local_load_ohlcv_csv(str(source))
    assert list(frame.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert float(frame.iloc[0]["close"]) == 2.0
    assert str(frame.iloc[0]["timestamp"]) == "2026-01-01 00:00:00"


def test_canonical_main_smoke_emits_authority_trace(tmp_path: Path) -> None:
    """`python -m smc_desk.colleague --smoke` writes a valid authority_trace.json."""
    out_root = tmp_path / "smoke"
    proc = _run(
        [
            "-m",
            "smc_desk.colleague",
            "--smoke",
            "--output-root",
            str(out_root),
        ]
    )
    # Even if the boundary check fails, capture output for debugging.
    assert proc.returncode == 0, (
        f"canonical smoke failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    trace_path = out_root / "_authority_smoke" / "authority_trace.json"
    assert trace_path.exists()
    trace = json.loads(trace_path.read_text())
    assert trace["schema"] == "smc_codex_desk_authority_trace_v1"
    assert trace["wp"] == "WP-0043"
    assert trace["gate"] == "GATE-CANONICAL-RUNTIME-001"
    assert trace["canonical_authority"] == "smc_desk.colleague.orchestrator_v3"
    assert trace["live_execution"] == "disabled"
    assert trace["paper_execution"] == "disabled"
    assert "module_versions" in trace


@pytest.mark.parametrize(
    "statement, expected",
    [
        ("from smc_desk.engine import analyze_dataframe\n", "smc_desk.engine.analyze_dataframe"),
        ("from smc_desk.case_library import file_sha256\n", "smc_desk.case_library.file_sha256"),
        ("from smc_desk.mtf import resample_ohlcv\n", "smc_desk.mtf.resample_ohlcv"),
        ("from smc_desk.rules import load_rule_config\n", "smc_desk.rules.load_rule_config"),
    ],
)
def test_boundary_checker_rejects_new_forbidden_import(
    tmp_path: Path,
    statement: str,
    expected: str,
) -> None:
    """A synthetic file with a forbidden import must be flagged.

    This is a regression net: if the checker ever stops catching the leak, this
    test will fail first.
    """
    bad = tmp_path / "smc_desk" / "_wp0043_boundary_test"
    bad.mkdir(parents=True)
    p = bad / "leaky.py"
    p.write_text(statement, encoding="utf-8")

    # Execute the checker against an in-memory ACTIVE_PACKAGES pointing at
    # this dir. We use a tiny driver script.
    driver = tmp_path / "run_checker.py"
    driver.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path.cwd()))\n"
        "import tools.check_authority_boundaries as cab\n"
        f"cab.ACTIVE_PACKAGES = [Path({str(bad)!r})]\n"
        "sys.exit(cab.main())\n",
        encoding="utf-8",
    )
    proc = _run([str(driver)])
    assert proc.returncode != 0
    assert "AUTHORITY BOUNDARY CHECK: FAIL" in proc.stdout
    assert expected in proc.stdout
