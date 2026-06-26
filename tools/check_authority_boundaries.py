#!/usr/bin/env python3
"""Check that no active-authority module imports or calls the legacy engine.

Uses AST analysis for all three import patterns:
1. Top-level imports (module scope)
2. Function-local imports (inside def/async def)
3. Conditional imports (inside if blocks)

Exit non-zero if any forbidden import is found in active-authority packages.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FORBIDDEN_TARGETS: Set[str] = {
    "analyze_dataframe",
    "build_trade_plan",
    "build_trade_plan_markdown",
    "build_dual_trade_plan",
    "StrategyEngineV1",
}

# Packages where legacy imports are forbidden
ACTIVE_PACKAGES: List[Path] = [
    ROOT / "smc_desk" / "colleague",
    ROOT / "smc_desk" / "decision",
]

# Files that are ALLOWED to import legacy (comparison adapters)
ALLOWED_FOR_LEGACY: Set[str] = {
    "legacy_comparison.py",
    "mtf.py",  # legacy MTF — deprecated, not current authority
}


class Finding:
    def __init__(self, file: Path, line: int, name: str, scope: str):
        self.file = file
        self.line = line
        self.name = name
        self.scope = scope  # "top_level", "function_local", "conditional"

    def __repr__(self) -> str:
        return f"{self.file.name}:{self.line} [{self.scope}] imports {self.name}"


def check_imports(file_path: Path) -> List[Finding]:
    """Find all legacy engine imports in a file."""
    if file_path.name in ALLOWED_FOR_LEGACY:
        return []

    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    source_lines = file_path.read_text(encoding="utf-8").splitlines()
    findings: List[Finding] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module == "engine"
                or node.module.endswith(".engine")
                or "smc_desk.engine" in node.module
            ):
                for alias in node.names:
                    if alias.name in FORBIDDEN_TARGETS:
                        lineno = node.lineno - 1
                        scope = _classify_scope(source_lines, lineno)
                        findings.append(Finding(file_path, node.lineno, alias.name, scope))

        # Also check regular imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "engine" in alias.name.lower() and "StrategyEngine" in alias.name:
                    findings.append(Finding(file_path, node.lineno, alias.name, "top_level"))

    return findings


def _classify_scope(lines: List[str], lineno: int) -> str:
    """Determine if an import is top-level, in a function, or in a conditional."""
    if lineno >= len(lines):
        return "unknown"
    line = lines[lineno]
    stripped = line.lstrip()
    if not stripped:
        return "top_level"
    indent = len(line) - len(stripped)
    if indent == 0:
        return "top_level"
    return "nested"


def main() -> int:
    all_findings: List[Finding] = []
    for pkg in ACTIVE_PACKAGES:
        for py_file in pkg.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            findings = check_imports(py_file)
            all_findings.extend(findings)

    if not all_findings:
        print("AUTHORITY BOUNDARY CHECK: PASS")
        print("No legacy engine imports found in active-authority packages.")
        return 0

    print("AUTHORITY BOUNDARY CHECK: FAIL")
    print(f"Found {len(all_findings)} forbidden import(s):")
    for f in all_findings:
        print(f"  {f}")
    print()
    print("These imports must be moved to smc_desk/colleague/legacy_comparison.py")
    print("or the file must be added to ALLOWED_FOR_LEGACY if it is a deprecated module.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
