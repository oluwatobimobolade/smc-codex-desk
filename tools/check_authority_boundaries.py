#!/usr/bin/env python3
"""Check that no active-authority module imports or calls the legacy engine.

Uses AST analysis for all three import patterns:
1. Top-level imports (module scope)
2. Function-local imports (inside def/async def)
3. Conditional imports (inside if blocks)

Exit non-zero if any forbidden import is found in active-authority packages.

WP-0043 (Canonical Runtime and Authority Consolidation, GATE-CANONICAL-RUNTIME-001)
extended the active-package set to include ``smc_desk/brain`` and
``smc_desk/perception`` plus the canonical command surface
(``tools/run_live_ai_smc_full_system.py`` and
``tools/run_wp0020_market_colleague_gauntlet.py``).

BR-001 closes an indirect-import loophole: importing ``case_library``, ``mtf``,
or ``rules`` can load the legacy engine even when no forbidden engine function
is named locally.  The checker therefore rejects whole legacy module roots in
active authority code. Historical v1/v2 gauntlets remain explicit comparison
adapters and are not part of the canonical v3 command surface.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Forbidden call names retained for diagnostic detail.
FORBIDDEN_TARGETS: Set[str] = {
    "analyze_dataframe",
    "build_trade_plan",
    "build_trade_plan_markdown",
    "build_dual_trade_plan",
    "StrategyEngineV1",
    "load_ohlcv_csv",
    "load_rule_config",
}

# Importing any of these modules is itself a violation.  Checking only selected
# function aliases allowed canonical files to import case_library/mtf/rules and
# pull the legacy engine into memory indirectly.
FORBIDDEN_MODULES: Set[str] = {
    "smc_desk.engine",
    "smc_desk.case_library",
    "smc_desk.mtf",
    "smc_desk.rules",
}

# Packages where legacy imports are forbidden (WP-0043 expansion).
ACTIVE_PACKAGES: List[Path] = [
    ROOT / "smc_desk" / "colleague",
    ROOT / "smc_desk" / "decision",
    ROOT / "smc_desk" / "brain",
    ROOT / "smc_desk" / "perception",
]

# Top-level tools that are part of the canonical command surface.
# Anything outside this list is presumed comparison/research and may opt in
# explicitly via ALLOWED_FOR_LEGACY below.
CANONICAL_TOOLS: List[Path] = [
    ROOT / "tools" / "run_live_ai_smc_full_system.py",
    ROOT / "tools" / "run_perception_experiment.py",
]

# Files that are ALLOWED to import legacy (comparison adapters / opt-ins).
# Add to this set only with explicit governance justification.
ALLOWED_FOR_LEGACY: Set[str] = {
    "legacy_comparison.py",            # canonical comparison adapter (WP-0012A)
    "analyze_live_dual_lens.py",       # explicitly tagged comparison_only (WP-0043)
    "orchestrator.py",                 # v1 comparison-only runtime
    "orchestrator_v2.py",              # v2 comparison-only runtime
    "live_shadow.py",                  # pre-v3 comparison/research harness
    "wp0020_gauntlet.py",              # historical v2 gauntlet, not canonical v3
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
            module = node.module or ""
            if _is_forbidden_module(module):
                for alias in node.names:
                    lineno = node.lineno - 1
                    scope = _classify_scope(source_lines, lineno)
                    findings.append(
                        Finding(file_path, node.lineno, f"{module}.{alias.name}", scope)
                    )

        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_module(alias.name):
                    lineno = node.lineno - 1
                    scope = _classify_scope(source_lines, lineno)
                    findings.append(Finding(file_path, node.lineno, alias.name, scope))

    return findings


def _is_forbidden_module(module: str) -> bool:
    return any(module == target or module.startswith(f"{target}.") for target in FORBIDDEN_MODULES)


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
    checked: List[Path] = []

    for pkg in ACTIVE_PACKAGES:
        if not pkg.exists():
            continue
        for py_file in pkg.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            findings = check_imports(py_file)
            all_findings.extend(findings)
            checked.append(py_file)

    for tool in CANONICAL_TOOLS:
        if not tool.exists():
            continue
        findings = check_imports(tool)
        all_findings.extend(findings)
        checked.append(tool)

    if not all_findings:
        print("AUTHORITY BOUNDARY CHECK: PASS")
        print(f"Scanned {len(checked)} files across "
              f"{len(ACTIVE_PACKAGES)} active packages + "
              f"{len(CANONICAL_TOOLS)} canonical tools.")
        print("No forbidden legacy imports found.")
        return 0

    print("AUTHORITY BOUNDARY CHECK: FAIL")
    print(f"Found {len(all_findings)} forbidden import(s) in {len(checked)} scanned files:")
    for f in all_findings:
        print(f"  {f}")
    print()
    print("These imports must be moved to smc_desk/colleague/legacy_comparison.py")
    print("or the file must be added to ALLOWED_FOR_LEGACY with explicit governance justification.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
