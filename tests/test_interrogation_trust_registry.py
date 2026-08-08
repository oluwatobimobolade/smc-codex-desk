from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from smc_desk.evaluation.interrogation_cohort import build_interrogation_cohort, verify_interrogation_cohort
from smc_desk.evaluation.trust_registry import provision_cohort_trust_registry


def _source(path: Path, count: int = 16_000) -> Path:
    rng = np.random.default_rng(11)
    close = 100 + rng.normal(0, 1, count).cumsum()
    open_ = np.concatenate(([close[0]], close[:-1]))
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2022-01-01", periods=count, freq="15min", tz="UTC"),
        "open": open_,
        "high": np.maximum(open_, close) + rng.random(count),
        "low": np.minimum(open_, close) - rng.random(count),
        "close": close,
        "volume": rng.integers(1, 1000, count),
    })
    frame.to_csv(path, index=False)
    return path


def _public_key(root: Path, name: str) -> Path:
    private = root / f"{name}.private.pem"
    public = root / f"{name}.public.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
    return public


def test_provisioning_pins_six_distinct_authorities_and_preserves_cohort_integrity(tmp_path: Path) -> None:
    source = _source(tmp_path / "BTCUSDT.csv")
    root = tmp_path / "cohort"
    build_interrogation_cohort(symbol_csv_paths={"BTCUSDT": source}, output_root=root, cases_per_symbol=1)
    roles = (("R1", "reviewer"), ("R2", "reviewer"), ("ADJ", "adjudicator"), ("SYS", "system_operator"), ("VIS", "visual_auditor"), ("CAL", "calibration_authority"))
    signers = [{"signer_id": signer, "role": role, "public_key_path": _public_key(tmp_path, signer)} for signer, role in roles]
    result = provision_cohort_trust_registry(root, signers)
    assert result["status"] == "PROVISIONED"
    manifest = json.loads((root / "cohort_manifest.json").read_text(encoding="utf-8"))
    assert manifest["trust_registry_status"] == "PROVISIONED"
    assert "trust_registry_unprovisioned" not in manifest["certification_blockers"]
    verification = verify_interrogation_cohort(root)
    assert verification["status"] == "PASS"
    assert verification["trust_registry_ready"] is True


def test_duplicate_public_key_cannot_impersonate_independent_reviewer(tmp_path: Path) -> None:
    source = _source(tmp_path / "BTCUSDT.csv")
    root = tmp_path / "cohort"
    build_interrogation_cohort(symbol_csv_paths={"BTCUSDT": source}, output_root=root, cases_per_symbol=1)
    shared = _public_key(tmp_path, "shared")
    roles = (("R1", "reviewer"), ("R2", "reviewer"), ("ADJ", "adjudicator"), ("SYS", "system_operator"), ("VIS", "visual_auditor"), ("CAL", "calibration_authority"))
    signers = [{"signer_id": signer, "role": role, "public_key_path": shared} for signer, role in roles]
    with pytest.raises(ValueError, match="distinct public key"):
        provision_cohort_trust_registry(root, signers)
