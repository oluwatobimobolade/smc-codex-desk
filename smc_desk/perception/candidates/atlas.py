"""Multi-scale candidate atlas.

Per programme §4 ("Expert swing selection") and §4.2. Run every candidate
generator without allowing one to become final authority. The atlas fuses
their outputs into one indexed store by stable candidate_id (the id is
timeframe+type+time, so two generators finding the same pivot share one record
and the ``generator_sources`` list records every generator that produced it).

The atlas also enriches each record post-fusion with cross-generator
statistics (touch_count across all generators, average prominence across
those that measured it, cross-scale presence, etc.). The reconciler AI
consumes the unified index.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from smc_desk.data.hashing import object_sha256
from smc_desk.perception.candidates import (
    changepoint as changepoint_mod,
    directional_change as dc_mod,
    displacement as displacement_mod,
    prominence as prominence_mod,
)
from smc_desk.perception.candidates import fractal as fractal_mod
from smc_desk.perception.candidates.schema import (
    ALL_GENERATORS,
    SwingCandidate,
    candidate_id,
)


GENERATOR_FRACTAL = "fractal"
GENERATOR_DIRECTIONAL_CHANGE = "directional_change"
GENERATOR_PROMINENCE = "prominence"
GENERATOR_CHANGEPOINT = "changepoint"
GENERATOR_DISPLACEMENT = "displacement"


@dataclass(frozen=True)
class AtlasConfig:
    """Configuration for a single atlas build.

    Each timeframe may have its own generator parameters. The atlas will run
    each generator per (timeframe, params) and fuse.
    """
    timeframe: str
    bars_left: int = 5
    bars_right: int = 5
    fractal_scale: str = "internal"
    dc_thresholds: tuple[float, ...] = (0.5, 0.75, 1.0, 1.5, 2.0)
    prominence_window: int = 10
    prominence_atr: float = 1.0
    changepoint_features: tuple[str, ...] = (
        "log_return_mean",
        "log_return_variance",
        "range_atr",
        "directional_persistence",
        "body_ratio",
    )
    displacement_min_consecutive: int = 2
    displacement_min_body_ratio: float = 0.4
    displacement_min_range_atr: float = 0.5


@dataclass
class AtlasBuildResult:
    timeframe: str
    candidates: list[SwingCandidate] = field(default_factory=list)
    by_id: dict[str, SwingCandidate] = field(default_factory=dict)
    generator_run_counts: dict[str, int] = field(default_factory=dict)
    fusion_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def atlas_sha256(self) -> str:
        return object_sha256([c.to_dict() for c in self.candidates])


def build_for_timeframe(
    df: pd.DataFrame,
    *,
    config: AtlasConfig,
    decision_time: pd.Timestamp | None = None,
    generators: Iterable[str] | None = None,
) -> AtlasBuildResult:
    """Run the requested generators against ``df`` and fuse into one atlas.

    The atlas enforces the as-of boundary itself. When ``decision_time`` is
    supplied, only candles whose full timeframe has completed are retained.
    """
    input_rows = len(df)
    df = _prepare_frame(df, timeframe=config.timeframe, decision_time=decision_time)
    gens = tuple(generators) if generators is not None else ALL_GENERATORS
    out: list[SwingCandidate] = []
    counts: dict[str, int] = {g: 0 for g in ALL_GENERATORS}
    tf = config.timeframe

    def emit(cands):
        for c in cands:
            out.append(c)
            counts[c.generator_source] += 1

    if GENERATOR_FRACTAL in gens:
        emit(
            fractal_mod.detect_dataframe(
                df,
                timeframe=tf,
                bars_left=config.bars_left,
                bars_right=config.bars_right,
                scale=config.fractal_scale,
            )
        )
    if GENERATOR_DIRECTIONAL_CHANGE in gens:
        emit(dc_mod.detect(df, timeframe=tf, thresholds=config.dc_thresholds))
    if GENERATOR_PROMINENCE in gens:
        emit(
            prominence_mod.detect(
                df,
                timeframe=tf,
                window=config.prominence_window,
                prominence_atr=config.prominence_atr,
            )
        )
    if GENERATOR_CHANGEPOINT in gens:
        emit(changepoint_mod.detect(df, timeframe=tf, features=config.changepoint_features))
    if GENERATOR_DISPLACEMENT in gens:
        emit(
            displacement_mod.detect(
                df,
                timeframe=tf,
                min_consecutive=config.displacement_min_consecutive,
                min_body_ratio=config.displacement_min_body_ratio,
                min_range_atr=config.displacement_min_range_atr,
            )
        )

    fused = _fuse(out)
    if decision_time is not None:
        cutoff = pd.Timestamp(decision_time)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        fused = [
            candidate
            for candidate in fused
            if not candidate.available_at or _as_utc_timestamp(candidate.available_at) <= cutoff
        ]
    summary = {
        "timeframe": tf,
        "total_emitted": len(out),
        "after_fusion": len(fused),
        "by_generator": counts,
        "decision_time": pd.Timestamp(decision_time).isoformat() if decision_time is not None else None,
        "rows_input": input_rows,
        "rows_used": len(df),
        "forming_or_future_rows_excluded": input_rows - len(df),
        "config": asdict(config),
    }
    by_id = {c.candidate_id: c for c in fused}
    return AtlasBuildResult(
        timeframe=tf,
        candidates=fused,
        by_id=by_id,
        generator_run_counts=counts,
        fusion_summary=summary,
    )


def build_multi_timeframe(
    timeframe_dfs: Mapping[str, pd.DataFrame],
    *,
    decision_time: pd.Timestamp,
    configs: Mapping[str, AtlasConfig] | None = None,
) -> dict[str, AtlasBuildResult]:
    """Build one source-consistent atlas per timeframe under one cutoff."""
    out: dict[str, AtlasBuildResult] = {}
    for timeframe, frame in timeframe_dfs.items():
        cfg = (configs or {}).get(timeframe) or AtlasConfig(timeframe=timeframe)
        if cfg.timeframe != timeframe:
            raise ValueError(f"Atlas config timeframe {cfg.timeframe!r} does not match {timeframe!r}.")
        out[timeframe] = build_for_timeframe(frame, config=cfg, decision_time=decision_time)
    return out


def _prepare_frame(
    df: pd.DataFrame,
    *,
    timeframe: str,
    decision_time: pd.Timestamp | None,
) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Candidate atlas frame missing columns: {sorted(missing)}")
    frame = df.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if frame["timestamp"].duplicated().any():
        raise ValueError("Candidate atlas refuses duplicate timestamps.")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("Candidate atlas refuses out-of-order timestamps.")
    if ((frame["high"] < frame[["open", "close"]].max(axis=1))
            | (frame["low"] > frame[["open", "close"]].min(axis=1))
            | (frame["high"] < frame["low"])).any():
        raise ValueError("Candidate atlas refuses invalid OHLC geometry.")
    if decision_time is not None:
        cutoff = pd.Timestamp(decision_time)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        frame = frame[frame["timestamp"] + _timeframe_delta(timeframe) <= cutoff]
    return frame.reset_index(drop=True)


def _timeframe_delta(timeframe: str) -> pd.Timedelta:
    tf = timeframe.lower()
    if tf.endswith("m"):
        return pd.Timedelta(minutes=int(tf[:-1]))
    if tf.endswith("h"):
        return pd.Timedelta(hours=int(tf[:-1]))
    if tf.endswith("d"):
        return pd.Timedelta(days=int(tf[:-1]))
    raise ValueError(f"Unsupported atlas timeframe: {timeframe!r}")


def _utc_iso(value: Any) -> str:
    ts = pd.Timestamp(value)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.isoformat().replace("+00:00", "Z")


def _as_utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _fuse(candidates: Sequence[SwingCandidate]) -> list[SwingCandidate]:
    """Merge candidates that share a candidate_id (same timeframe + pivot + time).

    The first record encountered owns identity fields; later records contribute
    generator_sources and enrich optional fields (prominence, ATR move,
    displacement_after, fvg_created, etc.) if present. Cross-scale presence
    is set when multiple generators produced the same record.
    """
    by_id: dict[str, SwingCandidate] = {}
    generator_for_id: dict[str, set[str]] = {}
    for c in candidates:
        existing = by_id.get(c.candidate_id)
        if existing is None:
            by_id[c.candidate_id] = c
            generator_for_id[c.candidate_id] = {c.generator_source}
        else:
            generator_for_id[c.candidate_id].add(c.generator_source)
            merged = _merge(existing, c)
            by_id[c.candidate_id] = merged
    fused: list[SwingCandidate] = []
    for c in by_id.values():
        gens = sorted(generator_for_id[c.candidate_id])
        # Frozen dataclass -- rebuild with the cross_generator hypothesis appended
        new_hyp = list(c.causal_origin_hypotheses) + [{"cross_generator": gens}]
        fused.append(
            SwingCandidate(
                candidate_id=c.candidate_id,
                timeframe=c.timeframe,
                pivot_type=c.pivot_type,
                pivot_time=c.pivot_time,
                pivot_price=c.pivot_price,
                generator_source=c.generator_source,
                confirmed_at=c.confirmed_at,
                available_at=c.available_at,
                generator_sources=tuple(gens),
                scale=c.scale,
                prominence=c.prominence,
                volatility_normalized_move=c.volatility_normalized_move,
                bars_left=c.bars_left,
                bars_right=c.bars_right,
                survival_bars=c.survival_bars,
                subordinate_pivot_count=c.subordinate_pivot_count,
                displacement_after=c.displacement_after,
                fvg_created=c.fvg_created,
                breaks_caused=c.breaks_caused,
                liquidity_visibility=c.liquidity_visibility,
                touch_count=c.touch_count,
                age=c.age,
                lifecycle=c.lifecycle,
                parent_candidate_ids=c.parent_candidate_ids,
                child_candidate_ids=c.child_candidate_ids,
                causal_origin_hypotheses=new_hyp,
            )
        )
    return fused


def _merge(a: SwingCandidate, b: SwingCandidate) -> SwingCandidate:
    """Pick the best values across two records with the same candidate_id."""
    # Prefer the first non-None for fields the first record missed.
    def keep(field_name: str):
        va = getattr(a, field_name)
        vb = getattr(b, field_name)
        if va in (None, "", 0, False) and vb not in (None, "", 0, False):
            return vb
        return va

    lif = a.lifecycle if a.lifecycle != "CANDIDATE" else b.lifecycle
    return SwingCandidate(
        candidate_id=a.candidate_id,
        timeframe=a.timeframe,
        pivot_type=a.pivot_type,
        pivot_time=a.pivot_time,
        pivot_price=a.pivot_price,
        generator_source=a.generator_source,
        confirmed_at=max(filter(None, (a.confirmed_at, b.confirmed_at)), default=None),
        available_at=max(filter(None, (a.available_at, b.available_at)), default=None),
        generator_sources=tuple(sorted(set(a.generator_sources or (a.generator_source,)) | set(b.generator_sources or (b.generator_source,)))),
        scale=a.scale,
        prominence=keep("prominence"),
        volatility_normalized_move=keep("volatility_normalized_move"),
        bars_left=keep("bars_left"),
        bars_right=keep("bars_right"),
        survival_bars=keep("survival_bars"),
        subordinate_pivot_count=keep("subordinate_pivot_count"),
        displacement_after=bool(a.displacement_after or b.displacement_after),
        fvg_created=bool(a.fvg_created or b.fvg_created),
        breaks_caused=list({*a.breaks_caused, *b.breaks_caused}),
        liquidity_visibility=a.liquidity_visibility or b.liquidity_visibility,
        touch_count=max(a.touch_count, b.touch_count),
        age=max(a.age, b.age),
        lifecycle=lif,
        parent_candidate_ids=list({*a.parent_candidate_ids, *b.parent_candidate_ids}),
        child_candidate_ids=list({*a.child_candidate_ids, *b.child_candidate_ids}),
        causal_origin_hypotheses=list(a.causal_origin_hypotheses) + list(b.causal_origin_hypotheses),
    )


__all__ = [
    "AtlasConfig",
    "AtlasBuildResult",
    "build_for_timeframe",
    "build_multi_timeframe",
] + list(ALL_GENERATORS)
