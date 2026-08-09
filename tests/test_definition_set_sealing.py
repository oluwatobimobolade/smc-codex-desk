"""Tests for blind case selection and definition-set sealing.

The previous definition set reached the evaluation pipeline as sequential
date-block placeholders and was then described as "balanced across four
regimes" -- a claim nobody had checked against a chart. `definition_set_v2`
exists so that cannot recur, and these tests pin the refusals that enforce it.

The rule underneath all of them: a program must not be able to supply the
analyst's judgement. Who selected, why, and what they saw are human inputs,
and sealing fails without each of them.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from smc_desk.evaluation.cohort_integrity import (
    case_ids_sha256,
    definition_case_set_sha256,
    reviewed_definition_issues,
)

REPO = Path(__file__).resolve().parents[1]
SEAL = REPO / "tools" / "seal_definition_set.py"


def _survey(tmp_path: Path, count: int = 9) -> Path:
    root = tmp_path / "survey"
    root.mkdir()
    candidates = [
        {
            "candidate_id": f"cand_{i:02d}",
            "decision_time": f"2026-06-{i:02d}T12:00:00Z",
            "status": "RENDERED",
            "charts": ["BTCUSDT_1d_clean.png", "BTCUSDT_4h_clean.png"],
            "last_closed_candle": f"2026-06-{i:02d}T11:45:00Z",
        }
        for i in range(1, count + 1)
    ]
    (root / "survey_manifest.json").write_text(json.dumps({
        "schema": "candidate_survey_v1", "symbol": "BTCUSDT",
        "candidates": candidates,
    }))
    return root


def _picks(tmp_path: Path, cases: list[dict], rationale="Chose these for coverage.") -> Path:
    path = tmp_path / "picks.json"
    path.write_text(json.dumps({"rationale": rationale, "cases": cases}))
    return path


def _run(survey: Path, picks: Path, out: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(SEAL), "--survey", str(survey), "--selections", str(picks),
         "--analyst-id", "tester", "--output", str(out), *extra],
        capture_output=True, text=True, cwd=REPO,
    )


def _valid_cases(n=9):
    regimes = ["trend", "trend", "range", "range", "transition",
               "ambiguous", "ambiguous", "trend", "range"]
    return [
        {"candidate_id": f"cand_{i:02d}", "case_id": f"case_{i:02d}",
         "regime": regimes[i - 1], "note": "seen on the chart"}
        for i in range(1, n + 1)
    ]


# -- the refusals that make placeholders impossible ---------------------------


def test_seal_refuses_without_a_rationale(tmp_path: Path):
    survey = _survey(tmp_path)
    picks = _picks(tmp_path, _valid_cases(), rationale="   ")
    result = _run(survey, picks, tmp_path / "out")
    assert result.returncode != 0
    assert "rationale" in result.stderr


def test_seal_refuses_a_case_without_the_analysts_regime_call(tmp_path: Path):
    """The old labels were date blocks. A human call is now mandatory."""
    cases = _valid_cases()
    cases[0].pop("regime")
    result = _run(_survey(tmp_path), _picks(tmp_path, cases), tmp_path / "out")
    assert result.returncode != 0
    assert "regime" in result.stderr


def test_seal_refuses_a_candidate_not_in_the_survey(tmp_path: Path):
    """Selections must come from charts that were actually rendered and viewed."""
    cases = _valid_cases()
    cases[0]["candidate_id"] = "cand_99"
    result = _run(_survey(tmp_path), _picks(tmp_path, cases), tmp_path / "out")
    assert result.returncode != 0
    assert "not a rendered candidate" in result.stderr


def test_seal_refuses_too_few_cases_without_an_explicit_override(tmp_path: Path):
    result = _run(_survey(tmp_path), _picks(tmp_path, _valid_cases(3)), tmp_path / "out")
    assert result.returncode != 0
    assert "allow-small" in result.stderr


def test_seal_refuses_duplicate_case_ids(tmp_path: Path):
    cases = _valid_cases()
    cases[1]["case_id"] = cases[0]["case_id"]
    result = _run(_survey(tmp_path), _picks(tmp_path, cases), tmp_path / "out")
    assert result.returncode != 0
    assert "duplicate" in result.stderr


def test_seal_refuses_a_non_empty_output_directory(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.json").write_text("{}")
    result = _run(_survey(tmp_path), _picks(tmp_path, _valid_cases()), out)
    assert result.returncode != 0
    assert "already exists" in result.stderr


# -- the happy path produces something the contract accepts -------------------


def test_sealed_set_satisfies_the_v2_contract(tmp_path: Path):
    out = tmp_path / "out"
    result = _run(_survey(tmp_path), _picks(tmp_path, _valid_cases()), out)
    assert result.returncode == 0, result.stderr

    status = json.loads((out / "definition_set_status.json").read_text())
    case_ids = sorted(p.name for p in out.iterdir() if p.is_dir())
    issues = reviewed_definition_issues(
        status, case_ids, definition_case_set_sha256(out, case_ids)
    )
    assert issues == [], issues
    assert status["selection_status"] == "ANALYST_REVIEWED"
    assert status["scoreable"] is True
    assert status["analyst_id"] == "tester"
    assert status["case_ids_sha256"] == case_ids_sha256(case_ids)


def test_each_case_records_the_analysts_own_regime_and_provenance(tmp_path: Path):
    out = tmp_path / "out"
    assert _run(_survey(tmp_path), _picks(tmp_path, _valid_cases()), out).returncode == 0
    metadata = json.loads((out / "case_01" / "metadata.json").read_text())
    assert metadata["regime_type"] == "trend"
    assert metadata["analyst_note"] == "seen on the chart"
    assert metadata["selected_from"]["candidate_id"] == "cand_01"
    assert metadata["decision_time"] == "2026-06-01T12:00:00Z"


def test_editing_a_case_after_sealing_breaks_the_hash(tmp_path: Path):
    """The metadata hash is what stops a later edit inheriting the review."""
    out = tmp_path / "out"
    assert _run(_survey(tmp_path), _picks(tmp_path, _valid_cases()), out).returncode == 0
    status = json.loads((out / "definition_set_status.json").read_text())

    tampered = json.loads((out / "case_01" / "metadata.json").read_text())
    tampered["decision_time"] = "2026-12-25T12:00:00Z"
    (out / "case_01" / "metadata.json").write_text(json.dumps(tampered, indent=2))

    case_ids = sorted(p.name for p in out.iterdir() if p.is_dir())
    issues = reviewed_definition_issues(
        status, case_ids, definition_case_set_sha256(out, case_ids)
    )
    assert any("case_set_sha256" in issue for issue in issues)


# -- the survey stays blind ----------------------------------------------------


def test_survey_manifest_records_the_closed_candle_rule():
    """The lookahead that invalidated the first cohort must not reappear."""
    source = (REPO / "tools" / "survey_candidate_cases.py").read_text()
    assert "close_times <= decision" in source
    # The open-time comparison that admitted the still-forming candle.
    assert 'df["timestamp"] <= decision_time' not in source


def test_survey_renders_no_system_output():
    """A selection made against the machine's answer measures suggestion."""
    source = (REPO / "tools" / "survey_candidate_cases.py").read_text()
    for forbidden in ("build_smc_evidence_pack", "narrative_context",
                      "market_state", "PerceptionEngineV2"):
        assert forbidden not in source, f"survey must not surface {forbidden}"
