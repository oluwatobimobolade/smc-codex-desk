"""Narrative-claims validator (programme §28.4, contested decision #14).

Every accepted interpretation field that contains a numeric, time, or
price-level claim must cite at least one evidence_id. A narrative without
grounded evidence is BLOCK severity (programme contested decision #14:
'YES_ALL_CLAIMS_REQUIRE_EVIDENCE_ID' is the proposed default).

This validator walks the interpretation tree, locates string values that
contain price/level/time-looking tokens, and verifies each has an evidence
list nearby. It is conservative -- it is meant to catch the
'narrative-may-be-evidence-free' rejected alternative.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from smc_desk.validation.primitives import Severity, Violation

_PRICE_RE = re.compile(r"(?<![A-Za-z])[-+]?(?:\d*\.\d+|\d{2,})(?![A-Za-z])")
_TIME_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _contains_claim(s: str) -> bool:
    return bool(_PRICE_RE.search(s) or _TIME_RE.search(s))


def _walk(obj: Any, path: str = "",
          parent_evidence: list[str] | None = None,
          ) -> list[tuple[str, Any, list[str] | None]]:
    """Yield (path, node, parent_evidence_list) tuples for every node,
    skipping structural timestamp / id fields (they ARE the evidence)."""
    skip_keys = {
        "confirmed_at", "candidate_at", "pivot_time", "close_time",
        "confirming_candle_time", "timestamp", "object_id", "event_id",
        "decision_time", "timeframe", "origin_object_id",
        "breaking_candidate_id", "protected_point_id", "range_id",
        "parent_range_id", "created_at",
    }
    if isinstance(obj, Mapping):
        local_evidence = []
        for k, v in obj.items():
            if (k == "evidence_ids" or k.endswith("_evidence_ids")) and isinstance(v, list):
                local_evidence = [x for x in v if isinstance(x, str)]
        for k, v in obj.items():
            sub = f"{path}.{k}" if path else k
            if k in skip_keys:
                continue
            if isinstance(v, (dict, list)):
                yield from _walk(v, sub, local_evidence or parent_evidence)
            else:
                yield (sub, v, local_evidence or parent_evidence)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]", parent_evidence)
    else:
        yield (path, obj, parent_evidence)


def check_narrative_grounding(
    interpretation: Mapping[str, Any],
) -> tuple[Violation, ...]:
    """BLOCK narrative strings with price/time claims and no evidence nearby."""
    out: list[Violation] = []
    for path, node, evidence in _walk(interpretation):
        numeric_field = path.rsplit(".", 1)[-1] in {
            "price", "pivot_price", "broken_price", "body_close_price",
            "price_low", "price_high", "entry", "stop", "target", "invalidation",
        }
        if ((isinstance(node, str) and _contains_claim(node))
                or (numeric_field and isinstance(node, (int, float)))):
            if not evidence:
                out.append(Violation(
                    code="NARRATIVE_NAKED_CLAIM",
                    severity=Severity.BLOCK.value,
                    message=(f"narrative at {path!r} contains price/time claim without "
                             f"grounding evidence_ids nearby"),
                    field_path=path,
                    checker="narrative.grounding",
                ))
    return tuple(out)


__all__ = ["check_narrative_grounding"]
