"""Make a gold-set cohort actually markable, and seal the system's answer.

``data/gold_sets/definition_set_20`` has existed since 2026-06-23 with real
BTCUSDT decision times and a balanced regime spread — and empty reviewer
templates, no charts, and nothing to score against. It has never produced an
accuracy number, which is why every perception threshold in this repository
is a reasoned default rather than a measurement.

This builds the three missing pieces per case:

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
from pathlib import Path
from typing import Any

import pandas as pd

# Candles shown before the decision time. Enough to read structure without
# making the chart unreadable.
CONTEXT_CANDLES = {"15m": 180, "1h": 150, "4h": 120}
RENDER_TIMEFRAMES = ("4h", "1h", "15m")


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
    return parser.parse_args()


def _resample(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    indexed = frame.set_index("timestamp")
    out = (
        indexed.resample(rule, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    # Drop the still-forming bucket: completed candles only.
    return out.iloc[:-1].reset_index()


def _slice_at(df: pd.DataFrame, decision_time: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """Everything closed at or before the decision time, and nothing after."""
    history = df[df["timestamp"] <= decision_time].copy()
    if history.empty:
        raise ValueError("no candles at or before the decision time")
    return {
        "15m": history.tail(CONTEXT_CANDLES["15m"]).reset_index(drop=True),
        "1h": _resample(history, "1h").tail(CONTEXT_CANDLES["1h"]).reset_index(drop=True),
        "4h": _resample(history, "4h").tail(CONTEXT_CANDLES["4h"]).reset_index(drop=True),
        "1d": _resample(history, "1D").reset_index(drop=True),
    }


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
        "case_id": case_id,
        "reviewer_id": reviewer_id,
        "instrument": metadata.get("instrument"),
        "decision_time": metadata.get("decision_time"),
        "instructions": [
            "Mark this chart as you would for a client, at the decision time only.",
            "You cannot see future candles and neither could the system.",
            "Leave a field empty if the market genuinely does not show it.",
            "Ambiguity is a valid answer: set is_ambiguous and say why.",
        ],
        # 1. Context first.
        "htf_bias": "",                       # bullish | bearish | ranging | unclear
        "context_timeframe": "",              # which timeframe you took bias from
        "bias_reasoning": "",
        # 2. Location.
        "dealing_range": {"high": None, "low": None, "timeframe": "", "price_location": ""},
        # 3. Structure that matters.
        "annotations": [
            {
                "primitive": "",              # bos | choch | swing_high | swing_low | sweep
                "direction": "",
                "scope": "external",
                "timeframe": "",
                "timestamp": "",
                "price": None,
                "confidence": 1.0,
                "is_ambiguous": False,
                "notes": "",
            }
        ],
        # 4. Liquidity.
        "liquidity": {
            "swept": [{"price": None, "side": "", "notes": ""}],
            "unswept": [{"price": None, "side": "", "notes": ""}],
            "expected_draw": {"price": None, "direction": "", "why": ""},
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


def _system_answer(timeframe_dfs: dict[str, pd.DataFrame], symbol: str) -> dict[str, Any]:
    """Run the pipeline and record what it concluded. Sealed from the reviewer."""
    from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
    from smc_desk.colleague.run_context import dataframe_to_candles
    from smc_desk.perception.engine_v2 import PerceptionEngineV2

    detector_candidates: dict[str, Any] = {}
    for timeframe, frame in timeframe_dfs.items():
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
        except Exception as exc:  # noqa: BLE001 -- record, never abort the cohort
            detector_candidates[timeframe] = {"error": f"{type(exc).__name__}: {exc}"}

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

    return {
        "sealed": True,
        "note": "Generated before markup. Do not open until the reviewer has submitted.",
        "pack_hash": (pack.get("provenance") or {}).get("pack_hash"),
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
        "market_state": pack.get("market_state"),
        "significant_structure": {
            timeframe: node.get("major_object_ids", [])
            for timeframe, node in significance.items()
            if isinstance(node, dict)
        },
    }


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
    except Exception as exc:  # noqa: BLE001 -- record, never abort the cohort
        for payload in normalized.values():
            payload.setdefault("poi_lifecycle_error", f"{type(exc).__name__}: {exc}")
        return normalized

    for timeframe, payload in normalized.items():
        pois = lifecycle.get(timeframe, []) or []
        payload["pois"] = pois
        payload["active_pois"] = [
            poi for poi in pois
            if str(poi.get("validity_status") or "").startswith("VALID")
        ]
    return normalized


def main() -> None:
    args = parse_args()
    gold_root = Path(args.gold_set).expanduser().resolve()
    out_root = Path(args.output).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    source = pd.read_csv(Path(args.source).expanduser().resolve())
    source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)

    cases = sorted(p for p in gold_root.iterdir() if p.is_dir())
    if args.limit:
        cases = cases[: args.limit]

    manifest: list[dict[str, Any]] = []
    for case_dir in cases:
        metadata_path = case_dir / "metadata.json"
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text())
        case_id = case_dir.name
        symbol = str(metadata.get("instrument") or "BTCUSDT")
        decision_time = pd.Timestamp(metadata["decision_time"])

        case_out = out_root / case_id
        (case_out / "charts").mkdir(parents=True, exist_ok=True)

        try:
            timeframe_dfs = _slice_at(source, decision_time)
        except ValueError as exc:
            manifest.append({"case_id": case_id, "status": "SKIPPED", "reason": str(exc)})
            print(f"  {case_id}: SKIPPED ({exc})")
            continue

        for timeframe in RENDER_TIMEFRAMES:
            frame = timeframe_dfs.get(timeframe)
            if frame is None or frame.empty:
                continue
            _render_clean(
                frame,
                case_out / "charts" / f"{symbol}_{timeframe}_clean.png",
                f"{symbol} · {timeframe.upper()}   (decision time {decision_time:%Y-%m-%d %H:%M} UTC)",
            )

        (case_out / "markup_template.json").write_text(
            json.dumps(_markup_template(case_id, args.reviewer_id, metadata), indent=2)
        )

        answer = _system_answer(timeframe_dfs, symbol)
        (case_out / "_sealed_system_answer.json").write_text(
            json.dumps(answer, indent=2, default=str)
        )
        (case_out / "metadata.json").write_text(json.dumps(metadata, indent=2))

        manifest.append({
            "case_id": case_id,
            "status": "READY",
            "regime": metadata.get("regime_type"),
            "decision_time": str(decision_time),
            "charts": [p.name for p in sorted((case_out / "charts").glob("*.png"))],
            "system_state": (answer.get("market_state") or {}).get("state"),
            "system_bias": answer.get("htf_bias"),
        })
        print(f"  {case_id}: READY ({metadata.get('regime_type')}) "
              f"-> system says {answer.get('htf_bias')} / "
              f"{(answer.get('market_state') or {}).get('state')}")

    ready = [row for row in manifest if row["status"] == "READY"]
    (out_root / "cohort_manifest.json").write_text(json.dumps({
        "schema": "markup_cohort_v1",
        "gold_set": str(gold_root),
        "source": str(args.source),
        "reviewer_id": args.reviewer_id,
        "case_count": len(manifest),
        "ready_count": len(ready),
        "blinding": "System answers are sealed per case and must not be opened before markup.",
        "cases": manifest,
    }, indent=2))

    print(f"\n{len(ready)}/{len(manifest)} cases ready in {out_root}")
    print("Each case has: charts/ (clean), markup_template.json, _sealed_system_answer.json")


if __name__ == "__main__":
    main()
