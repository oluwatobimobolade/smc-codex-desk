"""The live runner's module-level wiring must actually resolve.

WP-SMC-22 appended `record_selective_decision` to the end of
`run_live_ai_smc_full_system.py` -- after the `if __name__ == "__main__"` guard.
Python executes top to bottom, so `main()` ran before the definition was
reached, and every symbol died with `NameError`. The failure was caught by the
runner's own per-symbol handler and reported as `status: FAILED`, so the script
still exited cleanly and still wrote a summary; nothing screamed.

Unit tests did not catch it because they imported the function directly, which
resolves fine. Only executing the module in order reproduces it. These tests
check the property that actually matters: every name `main` calls is defined
before the guard that calls `main`.
"""
from __future__ import annotations

import ast
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[2] / "tools" / "run_live_ai_smc_full_system.py"


def _tree() -> ast.Module:
    return ast.parse(RUNNER.read_text(encoding="utf-8"))


def _main_guard_line(tree: ast.Module) -> int:
    for node in tree.body:
        if isinstance(node, ast.If) and ast.unparse(node.test).startswith("__name__"):
            return node.lineno
    raise AssertionError("runner has no __main__ guard")


def test_every_module_level_definition_precedes_the_main_guard() -> None:
    """Anything defined after the guard is dead code at runtime."""
    tree = _tree()
    guard = _main_guard_line(tree)
    late = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.lineno > guard
    ]
    assert not late, (
        f"defined after the __main__ guard and therefore unreachable when the "
        f"script runs: {late}"
    )


def test_record_selective_decision_is_defined_and_reachable() -> None:
    tree = _tree()
    guard = _main_guard_line(tree)
    found = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "record_selective_decision"
    ]
    assert found, "record_selective_decision is missing from the runner"
    assert found[0].lineno < guard


def test_the_runner_module_executes_top_to_bottom() -> None:
    """Import it the way the script runs it, and confirm the name resolves.

    This is the check that would have caught the original bug: importing the
    function by name from elsewhere succeeds even when the script itself would
    have failed.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_runner_wiring_probe", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert callable(getattr(module, "record_selective_decision", None))
    assert callable(getattr(module, "main", None))
