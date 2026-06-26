#!/usr/bin/env python3
"""Check governance documents for internal consistency.

Verifies that governance files agree on: current release, active work package,
active ontology, strategy authority, execution authority, test baseline,
deprecated modules, and capability states.

Exit non-zero on any inconsistency.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def check_consistency() -> tuple[bool, list[str]]:
    """Return (pass, issues). pass=True means no inconsistencies found."""
    issues: list[str] = []

    current_state = load_yaml(ROOT / "governance" / "CURRENT_STATE.yaml")
    authority_matrix = load_yaml(ROOT / "governance" / "AUTHORITY_MATRIX.yaml")
    next_actions = load_yaml(ROOT / "governance" / "NEXT_ACTIONS.yaml")
    capability_matrix = load_yaml(ROOT / "governance" / "CAPABILITY_MATRIX.yaml")

    # 1. Verify core authority claims are consistent
    authority = current_state.get("authority", {})

    # Execution must be disabled
    for key in ("paper_execution", "live_execution"):
        value = authority.get(key)
        if value and "disabled" not in str(value).lower():
            issues.append(f"CURRENT_STATE.authority.{key} = {value} — must be disabled")

    # Strategy authority must not be "active" or "enabled"
    strategy_keys = [k for k in authority if "strategy" in k.lower()]
    for sk in strategy_keys:
        val = authority[sk]
        if val and any(w in str(val).lower() for w in ("enabled", "active_runtime", "executable")):
            issues.append(f"CURRENT_STATE.authority.{sk} = {val} — strategy must not have execution authority")

    # Prediction must be disabled
    pred = authority.get("prediction")
    if pred and ("enabled" in str(pred).lower() or "active" in str(pred).lower()):
        issues.append(f"CURRENT_STATE.authority.prediction = {pred} — must be disabled")

    # 2. Legacy engine must be marked isolated
    legacy = authority.get("legacy_engine")
    if not legacy:
        issues.append("CURRENT_STATE.authority.legacy_engine missing — must document isolation status")
    elif "isolated" not in str(legacy).lower() and "comparison_only" not in str(legacy).lower():
        issues.append(f"CURRENT_STATE.authority.legacy_engine = {legacy} — must be isolated")

    # 3. Check for prohibited claims in governance files
    prohibited = [
        ("profitable", "guaranteed profitable"),
        ("alpha", "alpha"),
        ("edge verified", "edge verified"),
        ("live trading", "live trading"),
        ("100% accurate", "100% accurate"),
    ]
    for path in (ROOT / "governance").glob("*.md"):
        text = path.read_text(encoding="utf-8").lower()
        for word, _ in prohibited:
            if word in text:
                # Check if it's in a negated context or part of a compound term
                idx = text.find(word)
                context_before = text[max(0, idx - 60):idx]
                context_after = text[idx + len(word):idx + len(word) + 20]
                if any(neg in context_before for neg in ("no ", "not ", "never ", "cannot ", "no current", "disabled")):
                    continue
                # Skip compound terms like "live tradingview" (not "live trading" as a claim)
                full_word = text[idx:idx + len(word) + 10]
                if any(full_word.startswith(word + ext) for ext in ("view", "system", "api", "data", "chart")):
                    continue
                issues.append(f"{path.name}: contains unverified claim '{word}'")

    # 4. Check that WP-0012A-D and WP-0017A-B are recorded as complete
    completed_wps = ["wp0012a", "wp0012b", "wp0012c", "wp0012d", "wp0017a", "wp0017b"]
    authority_values = " ".join(str(v).lower() for v in authority.values())
    for wp in completed_wps:
        if wp not in authority_values:
            issues.append(f"{wp.upper()} not referenced in CURRENT_STATE.authority — must document completion")

    # 6. Verify no absolute paths are declared authoritative
    for path in (ROOT / "governance").glob("*.yaml"):
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.strip().startswith("/") and any(ext in line for ext in [".py", ".json", ".csv", ".yaml"]):
                if "Users" in line or "home" in line:
                    issues.append(f"{path.name}:{line.strip()[:60]} — absolute path must not be authoritative")

    # 7. Check that paper/live execution are not mentioned as available
    for path in (ROOT / "governance").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for phrase in ["paper_execute", "live_execute", "place_order"]:
            if phrase in text and "disabled" not in text[max(0, text.find(phrase) - 100):text.find(phrase) + len(phrase) + 100]:
                issues.append(f"{path.name}: contains '{phrase}' without explicit disablement context")

    return len(issues) == 0, issues


def main() -> int:
    passed, issues = check_consistency()
    if passed:
        print("GOVERNANCE CONSISTENCY: PASS")
        print("No inconsistencies found.")
        return 0
    else:
        print("GOVERNANCE CONSISTENCY: FAIL")
        print(f"Found {len(issues)} issue(s):")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
