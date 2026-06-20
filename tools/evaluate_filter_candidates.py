#!/usr/bin/env python3
"""Evaluate interpretable SMC filters on train and holdout research rows.

This is the promotion gate after ``build_research_dataset.py`` and
``calibrate_from_research.py``. It tries simple feature filters on in-sample
rows, then checks whether the same filter still improves out-of-sample rows.

The goal is not to maximize a backtest. The goal is to stop the system from
learning fake confidence. A filter is promoted only when it improves expectancy
on both train and holdout data, has enough holdout samples, and stays positive
after costs.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


CHECKLIST_KEYS = [
    "directional_bias",
    "fresh_or_partial_poi",
    "premium_discount_aligned",
    "liquidity_sweep",
    "displacement_break",
    "sweep_before_break",
    "price_at_or_near_poi",
    "stop_has_volatility_buffer",
    "risk_reward_floor",
]


Predicate = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class Candidate:
    name: str
    description: str
    predicate: Predicate


@dataclass
class CandidateResult:
    name: str
    description: str
    status: str
    train_n: int
    train_win_rate: float | None
    train_avg_r: float | None
    train_profit_factor: float | None
    train_avg_r_lift: float | None
    train_win_rate_lift: float | None
    holdout_n: int
    holdout_win_rate: float | None
    holdout_avg_r: float | None
    holdout_profit_factor: float | None
    holdout_avg_r_lift: float | None
    holdout_win_rate_lift: float | None
    selected_holdout_pct: float
    reason: str


def _tf(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _f(value: Any) -> float | None:
    try:
        if value in {"", None}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def dedupe_overlaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: (r.get("symbol", ""), r.get("entry_index", ""), r.get("decision_index", ""))):
        key = (row.get("symbol", ""), str(row.get("entry_index", "")))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def triggered_rows(rows: list[dict[str, Any]], dedupe: bool) -> list[dict[str, Any]]:
    triggered = [row for row in rows if _tf(row.get("triggered")) and _f(row.get("r_multiple")) is not None]
    return dedupe_overlaps(triggered) if dedupe else triggered


def expectancy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rs = [_f(row.get("r_multiple")) for row in rows]
    values = [value for value in rs if value is not None]
    if not values:
        return {"n": 0, "win_rate": None, "avg_r": None, "total_r": 0.0, "profit_factor": None}
    wins = [value for value in values if value > 0.05]
    losses = [value for value in values if value < -0.05]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "n": len(values),
        "win_rate": round(len(wins) / len(values), 4),
        "avg_r": round(sum(values) / len(values), 4),
        "total_r": round(sum(values), 4),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else None,
    }


def checklist(key: str) -> Candidate:
    return Candidate(
        f"check_{key}",
        f"Checklist component is true: {key}.",
        lambda row, col=f"chk_{key}": _tf(row.get(col)),
    )


def eq_filter(field: str, value: str) -> Candidate:
    return Candidate(
        f"{field}_{value}",
        f"{field} equals {value}.",
        lambda row, field=field, value=value: str(row.get(field, "")) == value,
    )


def rr_filter(name: str, description: str, predicate: Predicate) -> Candidate:
    return Candidate(name, description, predicate)


def build_base_candidates(train: list[dict[str, Any]], holdout: list[dict[str, Any]]) -> list[Candidate]:
    rows = train + holdout
    candidates: list[Candidate] = []
    for key in CHECKLIST_KEYS:
        values = {_tf(row.get(f"chk_{key}")) for row in rows}
        if len(values) > 1:
            candidates.append(checklist(key))
    for field in ["verdict", "setup_grade", "poi_kind", "poi_status", "session", "direction"]:
        values = sorted({str(row.get(field, "")) for row in rows if str(row.get(field, ""))})
        for value in values:
            candidates.append(eq_filter(field, value))
    candidates.extend(
        [
            Candidate("htf_aligned", "HTF alignment matches the setup direction.", lambda row: _tf(row.get("htf_aligned"))),
            Candidate(
                "htf_agreement_ge_0_67",
                "At least two of the three HTFs agree.",
                lambda row: (_f(row.get("htf_agreement_ratio")) or 0.0) >= 0.67,
            ),
            Candidate(
                "htf_agreement_1_00",
                "All three HTFs agree.",
                lambda row: (_f(row.get("htf_agreement_ratio")) or 0.0) >= 1.0,
            ),
            Candidate(
                "confluence_lt_0_875",
                "Avoid the highest confluence bucket if it is overconfident.",
                lambda row: (_f(row.get("confluence_score")) or 0.0) < 0.875,
            ),
            Candidate(
                "confluence_ge_0_75",
                "Confluence score is at least 0.75.",
                lambda row: (_f(row.get("confluence_score")) or 0.0) >= 0.75,
            ),
            Candidate(
                "confluence_ge_0_50",
                "Confluence score is at least 0.50.",
                lambda row: (_f(row.get("confluence_score")) or 0.0) >= 0.50,
            ),
            Candidate(
                "planned_rr_lt_3",
                "Avoid very stretched first targets; planned R:R is below 3.",
                lambda row: (_f(row.get("planned_rr")) or 0.0) < 3.0,
            ),
            Candidate(
                "planned_rr_2_to_4",
                "Planned R:R sits in the moderate 2 to 4 range.",
                lambda row: 2.0 <= (_f(row.get("planned_rr")) or 0.0) < 4.0,
            ),
            Candidate(
                "planned_rr_ge_3",
                "Planned R:R is at least 3.",
                lambda row: (_f(row.get("planned_rr")) or 0.0) >= 3.0,
            ),
            Candidate(
                "planned_rr_ge_4",
                "Planned R:R is at least 4.",
                lambda row: (_f(row.get("planned_rr")) or 0.0) >= 4.0,
            ),
            Candidate(
                "planned_rr_ge_5",
                "Planned R:R is at least 5.",
                lambda row: (_f(row.get("planned_rr")) or 0.0) >= 5.0,
            ),
            Candidate(
                "poi_width_ge_0_25",
                "POI width is at least 0.25% of price.",
                lambda row: (_f(row.get("poi_width_pct")) or 0.0) >= 0.25,
            ),
            Candidate(
                "poi_width_ge_0_50",
                "POI width is at least 0.50% of price.",
                lambda row: (_f(row.get("poi_width_pct")) or 0.0) >= 0.50,
            ),
            Candidate(
                "poi_score_ge_0_80",
                "POI quality score is at least 0.80.",
                lambda row: (_f(row.get("poi_score")) or 0.0) >= 0.80,
            ),
            Candidate(
                "not_after_hours",
                "Skip after-hours setups.",
                lambda row: str(row.get("session", "")) != "after_hours",
            ),
            Candidate(
                "london_or_overlap",
                "London or London/NY overlap session.",
                lambda row: str(row.get("session", "")) in {"london", "london_ny_overlap"},
            ),
            Candidate(
                "live_execute_like",
                "Only literal Execute verdicts.",
                lambda row: str(row.get("verdict", "")) == "Execute",
            ),
        ]
    )
    return candidates


def and_candidate(left: Candidate, right: Candidate) -> Candidate:
    return Candidate(
        f"{left.name}__and__{right.name}",
        f"{left.description} AND {right.description}",
        lambda row, left=left, right=right: left.predicate(row) and right.predicate(row),
    )


def candidate_status(
    train_exp: dict[str, Any],
    holdout_exp: dict[str, Any],
    base_train: dict[str, Any],
    base_holdout: dict[str, Any],
    min_train_n: int,
    min_holdout_n: int,
    min_holdout_avg_r_lift: float,
) -> tuple[str, str]:
    if train_exp["n"] < min_train_n:
        return "rejected", f"train sample below {min_train_n}"
    if holdout_exp["n"] < min_holdout_n:
        return "rejected", f"holdout sample below {min_holdout_n}"
    if train_exp["avg_r"] is None or holdout_exp["avg_r"] is None:
        return "rejected", "missing expectancy"

    train_lift = train_exp["avg_r"] - (base_train["avg_r"] or 0.0)
    holdout_lift = holdout_exp["avg_r"] - (base_holdout["avg_r"] or 0.0)
    if train_lift <= 0:
        return "rejected", "does not improve train avg R"
    if holdout_lift < min_holdout_avg_r_lift:
        return "rejected", "does not improve holdout avg R enough"
    if holdout_exp["avg_r"] <= 0:
        return "watchlist", "improves holdout but expectancy is still not positive"
    if holdout_exp["profit_factor"] is not None and holdout_exp["profit_factor"] < 1.0:
        return "watchlist", "positive avg R but profit factor is below 1"
    return "promoted_candidate", "passed train and holdout promotion gates"


def evaluate_candidate(
    candidate: Candidate,
    train: list[dict[str, Any]],
    holdout: list[dict[str, Any]],
    base_train: dict[str, Any],
    base_holdout: dict[str, Any],
    args: argparse.Namespace,
) -> CandidateResult:
    train_rows = [row for row in train if candidate.predicate(row)]
    holdout_rows = [row for row in holdout if candidate.predicate(row)]
    train_exp = expectancy(train_rows)
    holdout_exp = expectancy(holdout_rows)
    status, reason = candidate_status(
        train_exp=train_exp,
        holdout_exp=holdout_exp,
        base_train=base_train,
        base_holdout=base_holdout,
        min_train_n=args.min_train_n,
        min_holdout_n=args.min_holdout_n,
        min_holdout_avg_r_lift=args.min_holdout_avg_r_lift,
    )
    if status == "promoted_candidate" and ("verdict_Watch" in candidate.name or "verdict_Pass" in candidate.name):
        status = "research_only"
        reason = "uses a non-Execute verdict; study the pattern but do not deploy it as a live entry rule"

    def lift(value: float | None, baseline: float | None) -> float | None:
        if value is None or baseline is None:
            return None
        return round(value - baseline, 4)

    return CandidateResult(
        name=candidate.name,
        description=candidate.description,
        status=status,
        train_n=train_exp["n"],
        train_win_rate=train_exp["win_rate"],
        train_avg_r=train_exp["avg_r"],
        train_profit_factor=train_exp["profit_factor"],
        train_avg_r_lift=lift(train_exp["avg_r"], base_train["avg_r"]),
        train_win_rate_lift=lift(train_exp["win_rate"], base_train["win_rate"]),
        holdout_n=holdout_exp["n"],
        holdout_win_rate=holdout_exp["win_rate"],
        holdout_avg_r=holdout_exp["avg_r"],
        holdout_profit_factor=holdout_exp["profit_factor"],
        holdout_avg_r_lift=lift(holdout_exp["avg_r"], base_holdout["avg_r"]),
        holdout_win_rate_lift=lift(holdout_exp["win_rate"], base_holdout["win_rate"]),
        selected_holdout_pct=round(holdout_exp["n"] / max(1, base_holdout["n"]), 4),
        reason=reason,
    )


def sort_results(results: list[CandidateResult]) -> list[CandidateResult]:
    status_rank = {"promoted_candidate": 0, "research_only": 1, "watchlist": 2, "rejected": 3}
    return sorted(
        results,
        key=lambda item: (
            status_rank.get(item.status, 9),
            -(item.holdout_avg_r_lift if item.holdout_avg_r_lift is not None else -999.0),
            -(item.holdout_win_rate_lift if item.holdout_win_rate_lift is not None else -999.0),
            -item.holdout_n,
        ),
    )


def render_md(report: dict[str, Any]) -> str:
    base_train = report["baseline"]["train"]
    base_holdout = report["baseline"]["holdout"]
    promoted = [r for r in report["results"] if r["status"] == "promoted_candidate"]
    research_only = [r for r in report["results"] if r["status"] == "research_only"]
    watchlist = [r for r in report["results"] if r["status"] == "watchlist"]
    top = report["results"][:12]
    lines = [
        "# SMC Filter Training Gate",
        "",
        "This report tests simple filters on in-sample rows, then validates the exact same filters on holdout rows.",
        "",
        "## Baseline",
        "",
        "| split | n | win% | avg R | total R | PF |",
        "|---|---:|---:|---:|---:|---:|",
        f"| train | {base_train['n']} | {base_train['win_rate']} | {base_train['avg_r']} | {base_train['total_r']} | {base_train['profit_factor']} |",
        f"| holdout | {base_holdout['n']} | {base_holdout['win_rate']} | {base_holdout['avg_r']} | {base_holdout['total_r']} | {base_holdout['profit_factor']} |",
        "",
        "## Promotion Verdict",
        "",
    ]
    if promoted:
        lines.append(f"- Promoted candidates: {len(promoted)}. Treat these as rule-upgrade candidates, not live guarantees.")
    else:
        lines.append("- No filter passed promotion gates. The correct upgrade is to block false confidence, not force a weak rule live.")
    if research_only:
        lines.append(f"- Research-only candidates: {len(research_only)}. These include non-Execute verdicts and must not become live entries without a separate confirmation rule.")
    if watchlist:
        lines.append(f"- Watchlist candidates: {len(watchlist)}. These improved some metrics but are not production-ready.")
    lines.extend(
        [
            "",
            "## Top Candidates",
            "",
            "| status | filter | train n | train avgR lift | holdout n | holdout win lift | holdout avgR lift | reason |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in top:
        lines.append(
            f"| {row['status']} | `{row['name']}` | {row['train_n']} | {row['train_avg_r_lift']} | "
            f"{row['holdout_n']} | {row['holdout_win_rate_lift']} | {row['holdout_avg_r_lift']} | {row['reason']} |"
        )

    lines.extend(
        [
            "",
            "## How To Use This",
            "",
            "- A promoted candidate may be tested in the backtester as a new gate.",
            "- A rejected candidate should not become a rule, even if it looks good on screenshots.",
            "- If no filter is promoted, keep live behavior conservative and collect more reviewed cases.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(path: Path, results: list[CandidateResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(CandidateResult.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate SMC filter candidates on train and holdout research CSVs.")
    parser.add_argument("--train", nargs="+", required=True, help="In-sample research CSV path(s).")
    parser.add_argument("--holdout", nargs="+", required=True, help="Holdout research CSV path(s).")
    parser.add_argument("--output-dir", default="backtests/filter_training")
    parser.add_argument("--dedupe", choices=["on", "off"], default="on")
    parser.add_argument("--min-train-n", type=int, default=50)
    parser.add_argument("--min-holdout-n", type=int, default=30)
    parser.add_argument("--min-holdout-avg-r-lift", type=float, default=0.02)
    parser.add_argument("--max-pair-candidates", type=int, default=80)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    train = triggered_rows(load_rows([Path(path) for path in args.train]), dedupe=args.dedupe == "on")
    holdout = triggered_rows(load_rows([Path(path) for path in args.holdout]), dedupe=args.dedupe == "on")
    base_train = expectancy(train)
    base_holdout = expectancy(holdout)

    base_candidates = build_base_candidates(train, holdout)
    single_results = [
        evaluate_candidate(candidate, train, holdout, base_train, base_holdout, args)
        for candidate in base_candidates
    ]
    useful_for_pairs = [
        candidate
        for candidate, result in zip(base_candidates, single_results, strict=True)
        if result.train_n >= args.min_train_n and result.holdout_n >= max(10, args.min_holdout_n // 2)
    ][: args.max_pair_candidates]
    pair_candidates: list[Candidate] = []
    for i, left in enumerate(useful_for_pairs):
        for right in useful_for_pairs[i + 1 :]:
            pair_candidates.append(and_candidate(left, right))

    pair_results = [
        evaluate_candidate(candidate, train, holdout, base_train, base_holdout, args)
        for candidate in pair_candidates
    ]
    results = sort_results(single_results + pair_results)
    report = {
        "inputs": {
            "train": args.train,
            "holdout": args.holdout,
            "dedupe": args.dedupe,
            "min_train_n": args.min_train_n,
            "min_holdout_n": args.min_holdout_n,
            "min_holdout_avg_r_lift": args.min_holdout_avg_r_lift,
        },
        "baseline": {"train": base_train, "holdout": base_holdout},
        "results": [asdict(result) for result in results],
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "filter_training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "filter_training_report.md").write_text(render_md(report), encoding="utf-8")
    write_csv(out_dir / "filter_training_candidates.csv", results)
    print(render_md(report))
    print(f"\nWrote {out_dir / 'filter_training_report.md'}")


if __name__ == "__main__":
    main()
