"""Make an analyst-reviewed development cohort markable and seal the answer.

The input directory is a *definition set*: candidate decision times plus
machine-readable selection provenance. It is not a gold set merely because a
folder name says so. The builder refuses unreviewed inputs by default, because
sequential placeholder dates and hand-assigned regime labels cannot produce a
valid accuracy number.

No professional markup currently exists, so every perception threshold in
this repository remains a reasoned default rather than a measurement.

For a genuinely analyst-reviewed definition set, this builds the three missing
pieces per case:

1. **A clean chart.** Candles only, no annotations, no labels, no hints. The
   reviewer must read the market, not grade the machine.
2. **A markup template.** Pre-filled with the case identity and the fields to
   complete, conforming to ``evaluation.annotation_schema``.
3. **A sealed system answer.** What the pipeline itself concluded, written to
   a separate file and hashed. It is generated here so it cannot be adjusted
   after seeing the human markup, and the reviewer never opens it.

Blinding is the point. If the reviewer can see the system's answer, the
resulting "agreement" measures suggestion, not perception.

Usage::

    python tools/build_markup_cohort.py \\
        --gold-set data/gold_sets/definition_set_20 \\
        --source data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_4year.csv \\
        --output review_queues/markup_cohort_<date>
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from smc_desk.evaluation.cohort_integrity import (
    COHORT_SCHEMA,
    FAILED_COHORT_STATUS,
    INVALID_COHORT_STATUS,
    MARKUP_SCHEMA,
    RENDER_TIMEFRAMES,
    REVIEWED_DEFINITION_STATUS,
    VALID_COHORT_STATUS,
    artifact as _artifact,
    case_ids_sha256 as _case_ids_sha256,
    definition_case_set_sha256 as _definition_case_set_sha256,
    json_bytes as _json_bytes,
    manifest_content_sha256 as _manifest_content_sha256,
    reviewed_definition_issues as _reviewed_definition_issues,
    sha256_bytes as _sha256_bytes,
    sha256_file as _sha256_file,
    write_json as _write_json,
)

# Candles shown before the decision time. Enough to read structure without
# making the chart unreadable.
CONTEXT_CANDLES = {"15m": 180, "1h": 150, "4h": 120, "1d": 180}


class CohortGenerationError(RuntimeError):
    """A case could not produce a complete, scoreable sealed answer."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-set", default="data/gold_sets/definition_set_20")
    parser.add_argument(
        "--source", default="data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_4year.csv"
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--reviewer-id", default="founder")
    parser.add_argument(
        "--limit", type=int, default=0, help="Build only the first N cases (0 = all)."
    )
    parser.add_argument(
        "--allow-unreviewed-definition-set",
        action="store_true",
        help=(
            "Diagnostic escape hatch. The output remains INVALID_DO_NOT_MARK and "
            "cannot be scored. Never use this to manufacture a gold set."
        ),
    )
    return parser.parse_args()


def _resample(
    frame: pd.DataFrame,
    timeframe: str,
    decision_time: pd.Timestamp,
) -> pd.DataFrame:
    """Use the canonical close-visible-at reconstruction contract."""
    from smc_desk.data.timeframe_reconstruction import resample_ohlcv

    return resample_ohlcv(frame, timeframe, decision_time)


def _slice_at(df: pd.DataFrame, decision_time: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """Everything closed at or before the decision time, and nothing after."""
    decision = pd.Timestamp(decision_time)
    if decision.tzinfo is None:
        decision = decision.tz_localize("UTC")
    else:
        decision = decision.tz_convert("UTC")

    timestamps = pd.to_datetime(df["timestamp"], utc=True)
    if "close_time" in df.columns:
        close_times = pd.to_datetime(df["close_time"], utc=True)
    else:
        # The canonical source stores candle OPEN timestamps. The 12:00 row
        # is not evidence available at 12:00; its final OHLCV arrives at 12:15.
        close_times = timestamps + pd.Timedelta("15min")
    history = df.loc[close_times <= decision].copy()
    history["timestamp"] = timestamps.loc[history.index]
    if history.empty:
        raise ValueError("no fully closed candles at or before the decision time")
    return {
        "15m": history.tail(CONTEXT_CANDLES["15m"]).reset_index(drop=True),
        "1h": _resample(history, "1h", decision).tail(CONTEXT_CANDLES["1h"]).reset_index(drop=True),
        "4h": _resample(history, "4h", decision).tail(CONTEXT_CANDLES["4h"]).reset_index(drop=True),
        "1d": _resample(history, "1d", decision).tail(CONTEXT_CANDLES["1d"]).reset_index(drop=True),
    }


def _definition_set_status(root: Path) -> dict[str, Any]:
    """Load provenance for case selection; absence means unreviewed, not valid."""
    path = root / "definition_set_status.json"
    if not path.exists():
        return {
            "selection_status": "UNREVIEWED",
            "reason": "definition_set_status.json is missing",
        }
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"definition set status must be a JSON object: {path}")
    return payload


def _iter_object_records(value: Any):
    """Yield detector records from flat lists or nested scale mappings."""
    if isinstance(value, dict):
        if value.get("object_id"):
            yield value
            return
        for nested in value.values():
            yield from _iter_object_records(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _iter_object_records(nested)


def _evaluation_object_index(
    detector_candidates: dict[str, Any],
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    """Index the real detector schema for price-based evaluation.

    Detector fields such as liquidity kind and side live inside ``evidence``.
    The scorer receives both a compact price lookup and enough metadata to
    audit what kind of object was matched.
    """
    group_defaults = {
        "swings": "swing",
        "structure_breaks": "structure_break",
        "liquidity_levels": "liquidity",
        "sweeps": "sweep",
        "order_blocks": "order_block",
        "fvgs": "fvg",
        "poi_grade_fvgs": "fvg",
        "inducements": "inducement",
        "pois": "poi",
        "active_pois": "poi",
    }
    prices: dict[str, float] = {}
    metadata: dict[str, dict[str, Any]] = {}

    for timeframe, payload in (detector_candidates or {}).items():
        if not isinstance(payload, dict):
            continue
        for group, default_primitive in group_defaults.items():
            records = payload.get(group) or []
            for record in _iter_object_records(records):
                object_id = str(record.get("object_id") or "")
                if not object_id:
                    continue
                object_key = f"{timeframe}:{object_id}"
                evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
                price = _object_price(record, evidence, group=group)
                if price is not None:
                    prices[object_key] = price
                primitive = (
                    record.get("break_type")
                    or record.get("kind")
                    or evidence.get("break_kind")
                    or evidence.get("level_kind")
                    or default_primitive
                )
                if group == "swings" and primitive == default_primitive:
                    primitive = (
                        "swing_high"
                        if str(record.get("direction") or "").lower() == "bearish"
                        else "swing_low"
                    )
                metadata[object_key] = {
                    "object_id": object_id,
                    "group": group,
                    "primitive": str(primitive),
                    "direction": str(record.get("direction") or ""),
                    "timeframe": str(record.get("timeframe") or timeframe),
                    "scope": str(
                        record.get("structure_scope")
                        or record.get("scope")
                        or evidence.get("structure_scope")
                        or evidence.get("scope")
                        or ""
                    ),
                    "side": str(record.get("side") or evidence.get("side") or ""),
                    "pivot_time": record.get("pivot_time"),
                    "confirmed_at": record.get("confirmed_at"),
                }
    return prices, metadata


def _object_price(
    record: dict[str, Any],
    evidence: dict[str, Any],
    *,
    group: str,
) -> float | None:
    if group == "swings":
        direction = str(record.get("direction") or "").lower()
        swing_price = record.get("price_high") if direction == "bearish" else record.get("price_low")
        try:
            if swing_price is not None:
                return float(swing_price)
        except (TypeError, ValueError):
            pass
    for value in (
        record.get("price"),
        record.get("pivot_price"),
        evidence.get("broken_price"),
        evidence.get("swept_price"),
    ):
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            pass
    try:
        low = float(record["price_low"])
        high = float(record["price_high"])
    except (KeyError, TypeError, ValueError):
        return None
    return (low + high) / 2.0


def _render_clean(frame: pd.DataFrame, path: Path, title: str) -> None:
    """Candles only. No annotation, no level, no hint of the system's view."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    o = frame["open"].astype(float).to_numpy()
    h = frame["high"].astype(float).to_numpy()
    low = frame["low"].astype(float).to_numpy()
    c = frame["close"].astype(float).to_numpy()
    n = len(frame)
    span = max(float(h.max() - low.min()), 1e-9)

    fig, ax = plt.subplots(figsize=(16, 8.5))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    ax.grid(color="#eceff1", linewidth=0.7, alpha=0.9)
    floor = span * 0.0008
    for i in range(n):
        colour = "#159a8c" if c[i] >= o[i] else "#e65353"
        ax.plot([i, i], [low[i], h[i]], color="#242424", linewidth=0.65, zorder=2)
        height = max(abs(c[i] - o[i]), floor)
        ax.bar(i, height, bottom=min(o[i], c[i]), width=0.62,
               color=colour, edgecolor=colour, linewidth=0.4, zorder=3)

    step = max(1, n // 9)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels(
        [pd.Timestamp(frame["timestamp"].iloc[i]).strftime("%m-%d %H:%M") for i in ticks],
        fontsize=9, color="#5b6670",
    )
    ax.set_xlim(-1, n)
    ax.set_ylim(low.min() - span * 0.06, h.max() + span * 0.06)
    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color="#12181c", pad=14)
    for side in ("top", "left"):
        ax.spines[side].set_visible(False)
    ax.yaxis.tick_right()
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor="#ffffff")
    plt.close(fig)


def _markup_template(case_id: str, reviewer_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """The questions a reviewer answers. Deliberately the trader's order."""
    return {
        "schema": MARKUP_SCHEMA,
        "case_id": case_id,
        "reviewer_id": reviewer_id,
        "instrument": metadata.get("instrument"),
        "decision_time": metadata.get("decision_time"),
        "review_status": "IN_PROGRESS",
        "review_completed_at": "",
        "instructions": [
            "Mark this chart as you would for a client, at the decision time only.",
            "You cannot see future candles and neither could the system.",
            "Leave a field empty if the market genuinely does not show it.",
            "Ambiguity is a valid answer: set is_ambiguous and say why.",
            "Set review_status to COMPLETE and add review_completed_at only after every question was considered.",
        ],
        # 1. Context first.
        "htf_bias": "",                       # bullish | bearish | ranging | unclear
        "context_timeframe": "",              # which timeframe you took bias from
        "bias_reasoning": "",
        # 2. Location.
        "dealing_range": {"high": None, "low": None, "timeframe": "", "price_location": ""},
        # 3. Structure that matters.
        "annotations": [],                    # bos | choch | swing_high | swing_low
        # 4. Liquidity.
        "liquidity": {
            "swept": [],
            "unswept": [],
            "expected_draw": {"price": None, "direction": "", "timeframe": "", "why": ""},
        },
        # 5. The POI you would actually watch.
        "primary_poi": {"price_low": None, "price_high": None, "timeframe": "",
                        "kind": "", "why_this_one": ""},
        # 6. The decision.
        "what_are_you_waiting_for": "",
        "what_would_invalidate_this": "",
        "would_you_trade_this": "",           # yes | no | watch
        "reviewer_notes": "",
    }


def _review_instructions() -> str:
    return """# Blind chart review instructions

1. Confirm `cohort_manifest.json` says `VALID_FOR_EXPERT_DEVELOPMENT` or
   `VALID_FOR_BLIND_REVIEW`. Do not mark any invalid cohort.
2. Never open `_sealed_system_answer.json` before submitting the case.
3. Copy `markup_template.json` to `markup.json` and review all four charts.
4. Record BOS, CHoCH, swing highs, and swing lows in `annotations`. Record
   sweeps under `liquidity.swept`; sweep precision is not scored until its
   significance rule is expert-approved.
5. Genuine blank ranges, draws, and POIs are valid. Do not invent a mark merely
   to fill the form.
6. When every question has been considered, set `review_status` to `COMPLETE`
   and add a timezone-aware `review_completed_at`. Partial forms are refused.

The scorer verifies the source, manifest, charts, metadata, template, and
sealed-answer hashes before producing any metric. Agreement is not evidence of
profitability or execution authority.
"""


def _decision_from_market_state(market_state: dict[str, Any]) -> dict[str, Any]:
    """Map the observe-only state machine to the reviewer's three choices."""
    state = str((market_state or {}).get("state") or "")
    if state == "TRADE_PLAN_READY":
        classification = "yes"
    elif state in {"NO_CONTEXT", "INVALIDATED"}:
        classification = "no"
    elif state in {
        "MAP_CONTEXT",
        "LIQUIDITY_EVENT_IDENTIFIED",
        "ACCEPTED_DISPLACEMENT",
        "POI_MAPPED",
        "PRICE_APPROACHING_POI",
        "PRICE_AT_POI",
        "LTF_CONFIRMATION_PENDING",
    }:
        classification = "watch"
    else:
        classification = None
    return {
        "classification": classification,
        "source_state": state or None,
        "authority": "observe_only_no_signal_or_execution_authority",
    }


def _validate_system_answer(
    answer: dict[str, Any], expected_timeframes: tuple[str, ...] = RENDER_TIMEFRAMES
) -> None:
    """Reject a partial answer before a reviewer can ever see the case."""
    issues: list[str] = []
    if answer.get("generation_status") != "COMPLETE":
        issues.append("generation_status is not COMPLETE")
    if not answer.get("pack_hash"):
        issues.append("pack_hash is missing")
    if not answer.get("decision_time"):
        issues.append("decision_time is missing")
    market_state = answer.get("market_state")
    if not isinstance(market_state, dict) or not market_state.get("state"):
        issues.append("market_state.state is missing")
    decision = answer.get("decision")
    if not isinstance(decision, dict) or decision.get("classification") not in {"yes", "no", "watch"}:
        issues.append("decision classification is unresolved")

    detector_timeframes = set(answer.get("detector_timeframes") or [])
    atr = answer.get("atr") if isinstance(answer.get("atr"), dict) else {}
    for timeframe in expected_timeframes:
        if timeframe not in detector_timeframes:
            issues.append(f"detector output missing for {timeframe}")
        try:
            atr_value = float(atr.get(timeframe))
            if atr_value <= 0 or not math.isfinite(atr_value):
                raise ValueError
        except (TypeError, ValueError):
            issues.append(f"positive ATR missing for {timeframe}")

    prices = answer.get("object_prices") if isinstance(answer.get("object_prices"), dict) else {}
    metadata = answer.get("object_metadata") if isinstance(answer.get("object_metadata"), dict) else {}
    for timeframe, object_ids in (answer.get("significant_structure") or {}).items():
        for object_id in object_ids or []:
            key = f"{timeframe}:{object_id}"
            if key not in prices:
                issues.append(f"significant object has no price: {key}")
            else:
                try:
                    if not math.isfinite(float(prices[key])):
                        raise ValueError
                except (TypeError, ValueError):
                    issues.append(f"significant object has invalid price: {key}")
            if key not in metadata:
                issues.append(f"significant object has no metadata: {key}")
            else:
                item = metadata[key]
                if str(item.get("timeframe") or "").lower() != str(timeframe).lower():
                    issues.append(f"significant object timeframe mismatch: {key}")
                if str(item.get("primitive") or "").lower() not in {
                    "bos", "choch", "swing_high", "swing_low"
                }:
                    issues.append(f"significant object primitive is not scoreable: {key}")
    if issues:
        raise CohortGenerationError("; ".join(issues))


def _system_answer(timeframe_dfs: dict[str, pd.DataFrame], symbol: str) -> dict[str, Any]:
    """Run the pipeline and record what it concluded. Sealed from the reviewer."""
    from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
    from smc_desk.colleague.run_context import dataframe_to_candles
    from smc_desk.perception.engine_v2 import PerceptionEngineV2

    detector_candidates: dict[str, Any] = {}
    for timeframe in RENDER_TIMEFRAMES:
        frame = timeframe_dfs.get(timeframe)
        if frame is None or frame.empty:
            raise CohortGenerationError(f"required timeframe is empty: {timeframe}")
        try:
            candles = dataframe_to_candles(
                frame, venue="BINANCE", instrument=symbol, timeframe=timeframe
            )
            snapshot = PerceptionEngineV2().analyze(candles, candles[-1].close_time)
            # PerceptionSnapshot is a pydantic model: model_dump, not to_dict.
            detector_candidates[timeframe] = (
                snapshot.model_dump(mode="json")
                if hasattr(snapshot, "model_dump") else snapshot
            )
        except Exception as exc:  # noqa: BLE001 -- case must fail closed
            raise CohortGenerationError(
                f"detector failed for {timeframe}: {type(exc).__name__}: {exc}"
            ) from exc

    # The detector emits raw order blocks and FVGs; it does NOT populate `pois`
    # or `active_pois`. That is a separate lifecycle pass the canonical
    # orchestrator runs before sealing evidence. Skipping it leaves the causal
    # POI authority with nothing to adjudicate, so every case reports
    # CAUSAL_ORIGIN_UNRESOLVED and the state machine can never progress past
    # ACCEPTED_DISPLACEMENT. Mirror what orchestrator_v3 does.
    detector_candidates = _apply_poi_lifecycle(detector_candidates, timeframe_dfs)

    pack = build_smc_evidence_pack(
        symbol=symbol, timeframe_dfs=timeframe_dfs,
        detector_candidates=detector_candidates, max_candles_per_timeframe=120,
    )
    graph = pack.get("formal_structure_graph") or {}
    narrative = graph.get("narrative_context") or {}
    active_range = graph.get("active_range") or {}
    significance = (pack.get("structural_significance") or {}).get("timeframes") or {}
    object_prices, object_metadata = _evaluation_object_index(detector_candidates)

    market_state = pack.get("market_state") or {}
    answer = {
        "sealed": True,
        "generation_status": "COMPLETE",
        "note": "Generated before markup. Do not open until the reviewer has submitted.",
        "pack_hash": (pack.get("provenance") or {}).get("pack_hash"),
        "decision_time": graph.get("decision_time"),
        "detector_timeframes": list(RENDER_TIMEFRAMES),
        "htf_bias": narrative.get("context_bias"),
        "context_timeframe": narrative.get("context_timeframe"),
        "narrative_state": narrative.get("state"),
        "narrative_sentence": narrative.get("sentence"),
        "dealing_range": {
            "high": active_range.get("high"), "low": active_range.get("low"),
            "timeframe": active_range.get("timeframe"),
            "price_location": active_range.get("price_location"),
        },
        "draw": narrative.get("draw"),
        "market_state": market_state,
        "decision": _decision_from_market_state(market_state),
        "significant_structure": {
            timeframe: node.get("major_object_ids", [])
            for timeframe, node in significance.items()
            if isinstance(node, dict)
        },
        "atr": {
            timeframe: node.get("atr")
            for timeframe, node in significance.items()
            if isinstance(node, dict) and node.get("atr") is not None
        },
        "object_index_key_schema": "<timeframe>:<object_id>",
        "object_prices": object_prices,
        "object_metadata": object_metadata,
    }
    _validate_system_answer(answer)
    return answer


def _apply_poi_lifecycle(
    candidates: dict[str, Any], timeframe_dfs: dict[str, pd.DataFrame]
) -> dict[str, Any]:
    """Populate `pois` / `active_pois`, exactly as orchestrator_v3 does."""
    from smc_desk.perception.poi_lifecycle import build_poi_lifecycle_by_timeframe
    from smc_desk.perception.structure_hierarchy import build_mtf_structure_hierarchy

    normalized: dict[str, Any] = {}
    for timeframe, value in candidates.items():
        payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        normalized[timeframe] = dict(payload) if isinstance(payload, dict) else {}
    current_prices = {
        timeframe: float(df["close"].iloc[-1])
        for timeframe, df in timeframe_dfs.items()
        if timeframe in normalized and not df.empty
    }
    try:
        hierarchy = build_mtf_structure_hierarchy(normalized, current_prices=current_prices)
        lifecycle = build_poi_lifecycle_by_timeframe(
            normalized, hierarchy, current_prices=current_prices
        )
    except Exception as exc:  # noqa: BLE001 -- case must fail closed
        raise CohortGenerationError(
            f"POI lifecycle failed: {type(exc).__name__}: {exc}"
        ) from exc

    for timeframe, payload in normalized.items():
        pois = lifecycle.get(timeframe, []) or []
        payload["pois"] = pois
        payload["active_pois"] = [
            poi for poi in pois
            if str(poi.get("validity_status") or "").startswith("VALID")
        ]
    return normalized


def _frame_fingerprint(frame: pd.DataFrame) -> dict[str, Any]:
    """Bind the exact causal rows used without duplicating source data."""
    def utc_iso(value: Any) -> str:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        return timestamp.isoformat()

    columns = [
        column for column in ("timestamp", "close_time", "open", "high", "low", "close", "volume")
        if column in frame.columns
    ]
    canonical = frame.loc[:, columns].copy()
    for column in ("timestamp", "close_time"):
        if column in canonical.columns:
            canonical[column] = pd.to_datetime(canonical[column], utc=True).map(
                lambda value: value.isoformat()
            )
    payload = canonical.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    return {
        "sha256": _sha256_bytes(payload),
        "row_count": len(frame),
        "first_timestamp": utc_iso(frame["timestamp"].iloc[0]) if len(frame) else None,
        "last_timestamp": utc_iso(frame["timestamp"].iloc[-1]) if len(frame) else None,
    }


def build_cohort(
    *,
    gold_root: Path,
    source_path: Path,
    out_root: Path,
    reviewer_id: str,
    limit: int = 0,
    allow_unreviewed_definition_set: bool = False,
) -> dict[str, Any]:
    """Build once into a sibling staging directory, then rename atomically."""
    gold_root = gold_root.expanduser().resolve()
    source_path = source_path.expanduser().resolve()
    out_root = out_root.expanduser().resolve()
    if out_root.exists():
        raise FileExistsError(
            f"Refusing to overwrite immutable cohort output: {out_root}. Use a new output path."
        )
    if not gold_root.is_dir():
        raise ValueError(f"definition set does not exist: {gold_root}")
    if not source_path.is_file():
        raise ValueError(f"OHLCV source does not exist: {source_path}")
    if not str(reviewer_id).strip():
        raise ValueError("reviewer_id must not be blank")

    all_cases = sorted(
        path for path in gold_root.iterdir()
        if path.is_dir() and (path / "metadata.json").is_file()
    )
    all_case_ids = [path.name for path in all_cases]
    all_case_set_sha256 = _definition_case_set_sha256(gold_root, all_case_ids)
    decision_keys: set[str] = set()
    for case_path in all_cases:
        metadata = json.loads((case_path / "metadata.json").read_text(encoding="utf-8"))
        if not str(metadata.get("instrument") or "").strip():
            raise ValueError(f"case {case_path.name} has no instrument")
        decision_value = str(metadata.get("decision_time") or "")
        try:
            decision = pd.Timestamp(decision_value)
        except ValueError:
            raise ValueError(f"case {case_path.name} has an invalid decision_time") from None
        if decision.tzinfo is None:
            raise ValueError(f"case {case_path.name} decision_time must include a timezone")
        decision_key = decision.tz_convert("UTC").isoformat()
        if decision_key in decision_keys:
            raise ValueError(f"definition set contains duplicate decision_time: {decision_key}")
        decision_keys.add(decision_key)
    definition_status = _definition_set_status(gold_root)
    reviewed = definition_status.get("selection_status") == REVIEWED_DEFINITION_STATUS
    if reviewed:
        provenance_issues = _reviewed_definition_issues(
            definition_status, all_case_ids, all_case_set_sha256
        )
        if provenance_issues:
            raise ValueError("Invalid analyst-review provenance: " + "; ".join(provenance_issues))
    elif not allow_unreviewed_definition_set:
        raise ValueError(
            "Refusing to build an evaluation cohort from an unreviewed definition set: "
            f"{definition_status.get('selection_status')}. Select cases with an analyst and "
            "record complete definition_set_status_v2 provenance, or use the diagnostic "
            "escape hatch (whose output remains invalid and unscoreable)."
        )
    cases = all_cases[:limit] if limit else all_cases
    if not cases:
        raise ValueError("definition set contains no cases with metadata.json")

    out_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out_root.name}.building-", dir=out_root.parent))
    try:
        source = pd.read_csv(source_path)
        required_source_columns = {"timestamp", "open", "high", "low", "close", "volume"}
        missing_source_columns = sorted(required_source_columns - set(source.columns))
        if missing_source_columns:
            raise ValueError(f"OHLCV source is missing columns: {missing_source_columns}")
        source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)
        if not source["timestamp"].is_monotonic_increasing:
            raise ValueError("OHLCV source timestamps are not monotonic")
        if source["timestamp"].duplicated().any():
            raise ValueError("OHLCV source contains duplicate timestamps")
        for column in ("open", "high", "low", "close", "volume"):
            numeric = pd.to_numeric(source[column], errors="coerce")
            if numeric.isna().any():
                raise ValueError(f"OHLCV source contains invalid {column} values")
            source[column] = numeric

        case_rows: list[dict[str, Any]] = []
        for case_dir in cases:
            metadata = json.loads((case_dir / "metadata.json").read_text(encoding="utf-8"))
            case_id = case_dir.name
            symbol = str(metadata.get("instrument") or "BTCUSDT")
            decision_time = pd.Timestamp(metadata["decision_time"])
            case_out = staging / case_id
            charts_dir = case_out / "charts"
            charts_dir.mkdir(parents=True)

            try:
                timeframe_dfs = _slice_at(source, decision_time)
                empty = [tf for tf in RENDER_TIMEFRAMES if timeframe_dfs.get(tf) is None or timeframe_dfs[tf].empty]
                if empty:
                    raise CohortGenerationError(f"empty required timeframes: {', '.join(empty)}")

                for timeframe in RENDER_TIMEFRAMES:
                    _render_clean(
                        timeframe_dfs[timeframe],
                        charts_dir / f"{symbol}_{timeframe}_clean.png",
                        f"{symbol} · {timeframe.upper()}   (decision time {decision_time:%Y-%m-%d %H:%M} UTC)",
                    )

                template_info = _write_json(
                    case_out / "markup_template.json",
                    _markup_template(case_id, reviewer_id, metadata),
                )
                answer = _system_answer(timeframe_dfs, symbol)
                _validate_system_answer(answer)
                sealed_decision = pd.Timestamp(answer["decision_time"])
                if sealed_decision.tzinfo is None:
                    sealed_decision = sealed_decision.tz_localize("UTC")
                else:
                    sealed_decision = sealed_decision.tz_convert("UTC")
                requested_decision = pd.Timestamp(decision_time)
                if requested_decision.tzinfo is None:
                    requested_decision = requested_decision.tz_localize("UTC")
                else:
                    requested_decision = requested_decision.tz_convert("UTC")
                if sealed_decision != requested_decision:
                    raise CohortGenerationError(
                        f"sealed decision time {sealed_decision} does not match requested {requested_decision}"
                    )
                answer_info = _write_json(case_out / "_sealed_system_answer.json", answer)
                metadata_info = _write_json(case_out / "metadata.json", metadata)

                artifacts = {
                    "markup_template.json": template_info,
                    "_sealed_system_answer.json": answer_info,
                    "metadata.json": metadata_info,
                }
                for chart in sorted(charts_dir.glob("*.png")):
                    artifacts[f"charts/{chart.name}"] = _artifact(chart)
                source_slices = {
                    timeframe: _frame_fingerprint(timeframe_dfs[timeframe])
                    for timeframe in RENDER_TIMEFRAMES
                }
                seal_payload = {"artifacts": artifacts, "source_slices": source_slices}
                row = {
                    "case_id": case_id,
                    "status": "READY",
                    "regime": metadata.get("regime_type"),
                    "decision_time": str(decision_time),
                    "charts": [path.name for path in sorted(charts_dir.glob("*.png"))],
                    "system_state": (answer.get("market_state") or {}).get("state"),
                    "system_bias": answer.get("htf_bias"),
                    "sealed_answer_sha256": answer_info["sha256"],
                    "artifacts": artifacts,
                    "source_slices": source_slices,
                    "case_seal_sha256": _sha256_bytes(_json_bytes(seal_payload)),
                }
                case_rows.append(row)
                print(
                    f"  {case_id}: READY ({metadata.get('regime_type')}) -> system says "
                    f"{answer.get('htf_bias')} / {(answer.get('market_state') or {}).get('state')}"
                )
            except Exception as exc:  # noqa: BLE001 -- preserve a fail-closed audit record
                error = {
                    "schema": "cohort_generation_error_v1",
                    "case_id": case_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                error_info = _write_json(case_out / "generation_error.json", error)
                case_rows.append({
                    "case_id": case_id,
                    "status": "FAILED",
                    "regime": metadata.get("regime_type"),
                    "decision_time": str(decision_time),
                    "reason": str(exc),
                    "artifacts": {"generation_error.json": error_info},
                })
                print(f"  {case_id}: FAILED ({type(exc).__name__}: {exc})")

        ready = [row for row in case_rows if row["status"] == "READY"]
        failed = [row for row in case_rows if row["status"] != "READY"]
        invalid_reasons: list[str] = []
        if failed:
            validation_status = FAILED_COHORT_STATUS
            invalid_reasons.append(
                f"{len(failed)} case(s) failed complete system-answer generation."
            )
        elif not reviewed:
            validation_status = INVALID_COHORT_STATUS
            invalid_reasons.append(
                "The source definition set was not analyst-reviewed; its case labels are not ground truth."
            )
        else:
            validation_status = VALID_COHORT_STATUS

        definition_status_path = gold_root / "definition_set_status.json"
        instructions_path = staging / "REVIEW_INSTRUCTIONS.md"
        instructions_path.write_text(_review_instructions(), encoding="utf-8")
        manifest = {
            "schema": COHORT_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "validation_status": validation_status,
            "invalid_reasons": invalid_reasons,
            "definition_set": {
                "path": str(gold_root),
                "status": definition_status,
                "status_file_sha256": (
                    _sha256_file(definition_status_path) if definition_status_path.exists() else None
                ),
                "all_case_ids": all_case_ids,
                "all_case_ids_sha256": _case_ids_sha256(all_case_ids),
                "all_case_set_sha256": all_case_set_sha256,
                "selected_case_ids": [path.name for path in cases],
            },
            "source": {
                "path": str(source_path),
                "sha256": _sha256_file(source_path),
                "size_bytes": source_path.stat().st_size,
            },
            "reviewer_id": reviewer_id,
            "case_count": len(case_rows),
            "ready_count": len(ready),
            "failed_count": len(failed),
            "blinding": {
                "sealed_answers_generated_before_markup": True,
                "output_overwrite_permitted": False,
                "artifact_hashes_required_before_scoring": True,
            },
            "cohort_artifacts": {
                "REVIEW_INSTRUCTIONS.md": _artifact(instructions_path),
            },
            "cases": case_rows,
        }
        manifest["cohort_content_sha256"] = _manifest_content_sha256(manifest)
        _write_json(staging / "cohort_manifest.json", manifest)
        if out_root.exists():
            raise FileExistsError(
                f"Refusing to overwrite immutable cohort output: {out_root}. Use a new output path."
            )
        staging.rename(out_root)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> None:
    args = parse_args()
    out_root = Path(args.output).expanduser().resolve()
    try:
        manifest = build_cohort(
            gold_root=Path(args.gold_set),
            source_path=Path(args.source),
            out_root=out_root,
            reviewer_id=args.reviewer_id,
            limit=args.limit,
            allow_unreviewed_definition_set=args.allow_unreviewed_definition_set,
        )
    except (FileExistsError, ValueError) as exc:
        raise SystemExit(str(exc)) from None

    print(f"\n{manifest['ready_count']}/{manifest['case_count']} cases ready in {out_root}")
    if manifest["validation_status"] == FAILED_COHORT_STATUS:
        raise SystemExit(
            "Cohort generation failed closed. Inspect generation_error.json files; do not mark it."
        )
    print("Each case is hash-sealed; copy markup_template.json to markup.json only when reviewing.")


if __name__ == "__main__":
    main()
