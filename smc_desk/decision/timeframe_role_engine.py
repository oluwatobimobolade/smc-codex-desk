"""Timeframe role hierarchy for the SMC colleague."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


ROLE_BY_TIMEFRAME = {
    "1d": "macro_context",
    "4h": "directional_bias",
    "1h": "setup_poi",
    "15m": "entry_confirmation",
}


@dataclass(frozen=True)
class TimeframeRoleAssessment:
    roles: dict[str, str]
    directional_bias_timeframe: str | None
    setup_timeframe: str | None
    execution_timeframe: str | None
    ltf_override_allowed: bool
    directional_bias: str
    setup_bias: str
    execution_role: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = {f"{tf}_role": role for tf, role in self.roles.items()}
        payload.update(
            {
                "directional_bias_timeframe": self.directional_bias_timeframe,
                "setup_timeframe": self.setup_timeframe,
                "execution_timeframe": self.execution_timeframe,
                "ltf_override_allowed": self.ltf_override_allowed,
                "directional_bias": self.directional_bias,
                "setup_bias": self.setup_bias,
                "execution_role": self.execution_role,
                "notes": self.notes,
            }
        )
        return payload


def assess_timeframe_roles(hierarchy_by_tf: Mapping[str, Mapping[str, Any]]) -> TimeframeRoleAssessment:
    roles = {tf: ROLE_BY_TIMEFRAME[tf] for tf in ROLE_BY_TIMEFRAME if tf in hierarchy_by_tf}
    directional_bias = _bias(hierarchy_by_tf.get("4h")) or _bias(hierarchy_by_tf.get("1d")) or "neutral"
    setup_bias = _bias(hierarchy_by_tf.get("1h")) or "neutral"
    notes: list[str] = ["15m is confirmation-only and cannot override 1h/4h external structure."]
    if directional_bias in {"bullish", "bearish"} and setup_bias in {"bullish", "bearish"}:
        if directional_bias == setup_bias:
            notes.append(f"4h directional bias and 1h setup bias align {directional_bias}.")
        else:
            notes.append(f"4h directional bias {directional_bias} conflicts with 1h external setup bias {setup_bias}.")
    one_h = hierarchy_by_tf.get("1h") or {}
    if one_h.get("internal_state") in {"bullish_retracement", "bearish_retracement"}:
        notes.append(f"1h internal state is {one_h.get('internal_state')}; treat as retracement, not HTF override.")
    return TimeframeRoleAssessment(
        roles=roles,
        directional_bias_timeframe="4h" if "4h" in hierarchy_by_tf else None,
        setup_timeframe="1h" if "1h" in hierarchy_by_tf else None,
        execution_timeframe="15m" if "15m" in hierarchy_by_tf else None,
        ltf_override_allowed=False,
        directional_bias=directional_bias,
        setup_bias=setup_bias,
        execution_role="confirmation_only",
        notes=notes,
    )


def _bias(hierarchy: Mapping[str, Any] | None) -> str | None:
    if not hierarchy:
        return None
    bias = str(hierarchy.get("external_bias", "neutral"))
    return bias if bias in {"bullish", "bearish"} else None
