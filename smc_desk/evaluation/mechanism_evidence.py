"""The MECHANISM_SUPPORTED rung: preregistered association, honestly tested.

`DEFINITION_CONFORMANT` proves two implementations agree about geometry. It says
nothing about whether the geometry means anything. This module answers the next
question -- does a detected object associate with a named market observable more
than a matched control does -- and it is built to make a negative result as easy
to reach as a positive one.

Three things make that possible, and each corresponds to a way this kind of
study is normally wrong:

**A control arm.** Price revisits most levels eventually, so an uncontrolled
"the zone worked" is unfalsifiable. Controls come from ``matched_baseline``.

**Dependence-aware resampling.** Outcome windows overlap, so observations are
not independent and a plain t-test overstates significance -- badly, when the
horizon is long relative to the spacing. A stationary block bootstrap with
blocks no shorter than the horizon preserves the dependence structure.

**A multiple-testing correction.** Testing many hypotheses at 5% makes a false
positive near-certain: fifty tests give roughly a 92% chance that at least one
looks significant by chance. Harvey, Liu and Zhu argue the conventional t=2.0
bar is far too permissive given how much has been tested, and recommend 3.0 for
a new factor. Both that bar and a Benjamini-Hochberg step-up are applied.

The hypotheses themselves live in a hash-sealed preregistration. This module
refuses to test anything that is not in it, which is what stops the result from
being chosen after the fact.

Authority: MECHANISM_SUPPORTED only. It cannot establish participant identity,
deterministic causation, forecast quality, or economic value, and it creates no
signal, paper, or live authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import yaml

from smc_desk.data.hashing import file_sha256, object_sha256
from smc_desk.evaluation.matched_baseline import (
    MatchedCohort,
    balance_report,
    sample_matched_controls,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREREGISTRATION_PATH = ROOT / "specs" / "MECHANISM_PREREGISTRATION_V1.yaml"
DEFAULT_SEAL_PATH = ROOT / "specs" / "MECHANISM_PREREGISTRATION_V1.sha256"
EXPECTED_SCHEMA = "smc_codex_mechanism_preregistration_v1"

CERTIFICATE_STATUSES = {
    "MECHANISM_SUPPORTED",
    "MECHANISM_NOT_SUPPORTED",
    "BOUNDARY_SENSITIVE",
    "UNDERPOWERED",
    "DATA_FAILED",
    "NOT_EVALUATED",
}


@dataclass(frozen=True)
class Preregistration:
    document: Mapping[str, Any]
    sha256: str

    @property
    def contract(self) -> Mapping[str, Any]:
        return self.document.get("statistical_contract") or {}

    def hypothesis(self, hypothesis_id: str) -> Mapping[str, Any] | None:
        for item in self.document.get("hypotheses") or ():
            if isinstance(item, Mapping) and str(item.get("id")) == hypothesis_id:
                return item
        return None


def load_preregistration(
    path: str | Path = DEFAULT_PREREGISTRATION_PATH,
    seal_path: str | Path = DEFAULT_SEAL_PATH,
) -> Preregistration:
    """Load the sealed hypothesis set, refusing any edit made after sealing."""
    source, seal = Path(path), Path(seal_path)
    if not source.is_file():
        raise FileNotFoundError(f"Mechanism preregistration is missing: {source}")
    if not seal.is_file():
        raise FileNotFoundError(f"Mechanism preregistration seal is missing: {seal}")
    digest = file_sha256(source)
    if seal.read_text(encoding="utf-8").strip() != digest:
        raise ValueError("Mechanism preregistration hash mismatch.")
    document = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or document.get("schema") != EXPECTED_SCHEMA:
        raise ValueError("Unexpected mechanism preregistration schema.")
    return Preregistration(document=document, sha256=digest)


def forward_returns(
    candles: pd.DataFrame, indices: Sequence[int], horizon: int, *, signs: Sequence[float] | None = None
) -> np.ndarray:
    """Signed close-to-close return in basis points over ``horizon`` bars."""
    close = candles["close"].astype(float).to_numpy()
    total = len(close)
    out: list[float] = []
    for position, index in enumerate(indices):
        end = index + horizon
        if index < 0 or end >= total or close[index] <= 0:
            continue
        move = (close[end] - close[index]) / close[index] * 10_000.0
        out.append(move * (signs[position] if signs is not None else 1.0))
    return np.asarray(out, dtype=float)


def stationary_block_bootstrap_pvalue(
    treatment: np.ndarray,
    control: np.ndarray,
    *,
    block_length: int,
    resamples: int = 2000,
    seed: int = 0,
    two_sided: bool = False,
) -> dict[str, Any]:
    """Test the difference in means while respecting serial dependence.

    Blocks are drawn with a geometric length whose mean is ``block_length``, so
    the resample preserves the local dependence that overlapping outcome windows
    create. A plain bootstrap would treat those observations as independent and
    return a p-value that is far too small.
    """
    treatment = treatment[np.isfinite(treatment)]
    control = control[np.isfinite(control)]
    if treatment.size < 2 or control.size < 2:
        return {"p_value": None, "reason": "insufficient_observations"}

    observed = float(treatment.mean() - control.mean())
    pooled = np.concatenate([treatment, control])
    rng = np.random.default_rng(seed)
    block_length = max(1, int(block_length))

    def draw(size: int) -> np.ndarray:
        out = np.empty(size, dtype=float)
        filled = 0
        while filled < size:
            start = rng.integers(0, pooled.size)
            length = min(rng.geometric(1.0 / block_length), size - filled)
            take = np.arange(start, start + length) % pooled.size
            out[filled:filled + length] = pooled[take]
            filled += length
        return out

    # Null: both arms come from the same distribution. Resampling the pooled
    # series in blocks builds the null distribution of the mean difference.
    differences = np.empty(resamples, dtype=float)
    for i in range(resamples):
        differences[i] = draw(treatment.size).mean() - draw(control.size).mean()

    if two_sided:
        p_value = float((np.abs(differences) >= abs(observed)).mean())
    else:
        p_value = float((differences >= observed).mean())

    spread = float(differences.std(ddof=1))
    return {
        "observed_difference": round(observed, 6),
        "p_value": round(p_value, 6),
        "bootstrap_t": round(observed / spread, 6) if spread > 0 else None,
        "null_std": round(spread, 6),
        "resamples": resamples,
        "block_length": block_length,
        "two_sided": two_sided,
    }


def benjamini_hochberg(p_values: Sequence[float], false_discovery_rate: float) -> list[bool]:
    """Step-up procedure. Returns, per input position, whether it survives."""
    usable = [(i, p) for i, p in enumerate(p_values) if p is not None and np.isfinite(p)]
    verdicts = [False] * len(p_values)
    if not usable:
        return verdicts
    usable.sort(key=lambda pair: pair[1])
    total = len(usable)
    cutoff_rank = 0
    for rank, (_, p) in enumerate(usable, start=1):
        if p <= false_discovery_rate * rank / total:
            cutoff_rank = rank
    for rank, (index, _) in enumerate(usable, start=1):
        if rank <= cutoff_rank:
            verdicts[index] = True
    return verdicts


def _effective_sample_size(count: int, horizon: int, span: int) -> float:
    """Overlapping windows do not contribute a full observation each.

    Roughly, ``span / horizon`` non-overlapping slots exist; the effective count
    cannot exceed that however many events were detected.
    """
    if horizon <= 0 or span <= 0:
        return float(count)
    return float(min(count, max(1.0, span / horizon)))


def certify_mechanism(
    *,
    hypothesis_id: str,
    candles: pd.DataFrame,
    event_indices: Sequence[int],
    event_signs: Sequence[float] | None = None,
    preregistration: Preregistration | None = None,
    market: str = "UNKNOWN",
    timeframe: str = "UNKNOWN",
    seed: int = 0,
) -> dict[str, Any]:
    """Test one preregistered hypothesis and return a certificate."""
    prereg = preregistration or load_preregistration()
    hypothesis = prereg.hypothesis(hypothesis_id)
    contract = prereg.contract

    base: dict[str, Any] = {
        "schema": "smc_mechanism_certificate_v1",
        "hypothesis_id": hypothesis_id,
        "market": market,
        "timeframe": timeframe,
        "preregistration_sha256": prereg.sha256,
        "authority_contract": {
            "authority_rung": "MECHANISM_SUPPORTED",
            "human_adjudication_used": False,
            "proves": "preregistered_association_with_a_named_market_observable",
            "cannot_prove": [
                "participant_identity",
                "deterministic_causation",
                "forecast_quality",
                "economic_value",
            ],
            "signal_allowed": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
        },
    }

    if hypothesis is None:
        # Refusing an unregistered hypothesis is the whole point of the seal.
        return {**base, "status": "NOT_EVALUATED", "reason": "hypothesis_not_in_sealed_preregistration"}

    horizons = [int(h) for h in (hypothesis.get("horizons_bars") or []) if int(h) > 0]
    two_sided = str(hypothesis.get("prediction") or "") == "two_sided_difference_from_control"
    minimum_events = int(contract.get("minimum_events") or 0)
    minimum_effective = float(contract.get("minimum_effective_sample") or 0)
    minimum_t = float(contract.get("minimum_abs_t_statistic") or 0.0)
    fdr = float(contract.get("false_discovery_rate") or 0.05)
    resamples = int(contract.get("bootstrap_resamples") or 2000)
    controls_per_event = int(contract.get("controls_per_event") or 5)

    base["hypothesis"] = {
        "statement": hypothesis.get("statement"),
        "observable": hypothesis.get("observable"),
        "horizons_bars": horizons,
        "prediction": hypothesis.get("prediction"),
    }

    if candles is None or len(candles) == 0 or not {"high", "low", "close"}.issubset(candles.columns):
        return {**base, "status": "DATA_FAILED", "reason": "candles_missing_or_malformed"}
    if not horizons:
        return {**base, "status": "NOT_EVALUATED", "reason": "no_declared_horizons"}
    if len(event_indices) < minimum_events:
        return {
            **base, "status": "UNDERPOWERED",
            "reason": f"{len(event_indices)} events below preregistered minimum {minimum_events}",
            "event_count": len(event_indices),
        }

    longest = max(horizons)
    cohort: MatchedCohort = sample_matched_controls(
        candles, event_indices,
        controls_per_event=controls_per_event,
        exclusion_bars=longest, horizon_bars=longest, seed=seed,
    )
    if not cohort.samples:
        return {**base, "status": "DATA_FAILED", "reason": "no_events_could_be_matched",
                "matching": cohort.diagnostics}

    sign_by_index = {int(i): float(s) for i, s in zip(event_indices, event_signs or [])} if event_signs else {}
    per_horizon: list[dict[str, Any]] = []
    for horizon in horizons:
        treated_idx = [s.event_index for s in cohort.samples]
        treated_signs = [sign_by_index.get(i, 1.0) for i in treated_idx] if sign_by_index else None
        control_idx: list[int] = []
        control_signs: list[float] = []
        for sample in cohort.samples:
            sign = sign_by_index.get(sample.event_index, 1.0)
            for control in sample.control_indices:
                control_idx.append(control)
                control_signs.append(sign)

        treated = forward_returns(candles, treated_idx, horizon, signs=treated_signs)
        control = forward_returns(candles, control_idx, horizon,
                                  signs=control_signs if sign_by_index else None)
        result = stationary_block_bootstrap_pvalue(
            treated, control, block_length=horizon, resamples=resamples,
            seed=seed + horizon, two_sided=two_sided,
        )
        effective = _effective_sample_size(treated.size, horizon, len(candles))
        per_horizon.append({
            "horizon_bars": horizon,
            "treated_count": int(treated.size),
            "control_count": int(control.size),
            "effective_sample_size": round(effective, 3),
            "treated_mean_bps": round(float(treated.mean()), 6) if treated.size else None,
            "control_mean_bps": round(float(control.mean()), 6) if control.size else None,
            **result,
        })

    survives = benjamini_hochberg([h.get("p_value") for h in per_horizon], fdr)
    for entry, verdict in zip(per_horizon, survives):
        t_stat = entry.get("bootstrap_t")
        entry["survives_fdr"] = bool(verdict)
        entry["meets_t_threshold"] = bool(t_stat is not None and abs(t_stat) >= minimum_t)
        entry["passes"] = bool(entry["survives_fdr"] and entry["meets_t_threshold"])

    base["per_horizon"] = per_horizon
    base["matching"] = cohort.diagnostics
    base["balance"] = balance_report(candles, cohort)
    base["thresholds"] = {
        "minimum_abs_t_statistic": minimum_t,
        "false_discovery_rate": fdr,
        "minimum_events": minimum_events,
        "minimum_effective_sample": minimum_effective,
    }

    underpowered = [h for h in per_horizon if h["effective_sample_size"] < minimum_effective]
    if underpowered:
        base["status"] = "UNDERPOWERED"
        base["reason"] = (
            f"{len(underpowered)} horizon(s) below the preregistered effective sample floor "
            f"of {minimum_effective}; overlapping windows do not each contribute a full observation"
        )
    elif base["balance"].get("balanced") is False:
        # An unbalanced comparison measures the imbalance, not the mechanism.
        base["status"] = "DATA_FAILED"
        base["reason"] = "matched controls failed the covariate balance check"
    else:
        passed = [h["passes"] for h in per_horizon]
        signs = {np.sign(h.get("observed_difference") or 0.0) for h in per_horizon}
        if all(passed) and len(signs) == 1:
            base["status"] = "MECHANISM_SUPPORTED"
        elif any(passed):
            # Preregistered rule: a result at some horizons but not all is a
            # boundary artefact, and reporting only the agreeing subset is
            # explicitly prohibited.
            base["status"] = "BOUNDARY_SENSITIVE"
            base["reason"] = "horizons disagree; the preregistration requires all to agree"
        else:
            base["status"] = "MECHANISM_NOT_SUPPORTED"

    base["certificate_sha256"] = object_sha256(base)
    return base


__all__ = [
    "CERTIFICATE_STATUSES",
    "Preregistration",
    "benjamini_hochberg",
    "certify_mechanism",
    "forward_returns",
    "load_preregistration",
    "stationary_block_bootstrap_pvalue",
]
