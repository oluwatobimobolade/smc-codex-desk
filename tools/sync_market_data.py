#!/usr/bin/env python3
"""Local-first market data orchestrator.

Default mode is intentionally local-only: verify the existing Binance futures
CSV universe, optionally derive missing HTF files from canonical 15m data, and
write a hash/provenance manifest.  External refresh is opt-in via --refresh.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.case_library import file_sha256
from smc_desk.evaluation.holdout_guard import DEFAULT_HOLDOUT_POLICY, load_holdout_policy
from tools.derive_htf_from_15m import derive_htf
from tools.summarize_ohlcv_quality import DEFAULT_INTERVALS, DEFAULT_SYMBOLS, render_markdown, summarize_file


CANONICAL_CONTRACT = {
    "venue": "BINANCE",
    "market_type": "USD-M perpetual futures",
    "canonical_timeframe": "15m",
    "required_columns": ["timestamp", "open", "high", "low", "close", "volume"],
    "htf_policy": "1h/4h/1d are derived from the canonical repaired 15m files unless explicitly auditing native HTF files.",
    "authority": "local_ohlcv_csv_first",
    "external_refresh": "disabled_by_default",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify and manifest the local Binance futures OHLCV universe.")
    parser.add_argument("--data-root", default=str(ROOT / "data/ohlcv/binance_futures"))
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    parser.add_argument("--intervals", nargs="*", default=DEFAULT_INTERVALS)
    parser.add_argument("--tag", default="4year")
    parser.add_argument(
        "--derive-htf",
        choices=["off", "missing", "force"],
        default="missing",
        help="Derive 1h/4h/1d files from the 15m canonical file before manifesting.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Opt-in external Binance archive refresh via tools/pull_binance_futures_universe.sh.",
    )
    parser.add_argument("--start", help="START env for --refresh, e.g. 2022-06-20.")
    parser.add_argument("--end", help="END env for --refresh. End is exclusive.")
    parser.add_argument("--force-refresh", action="store_true", help="Set FORCE=1 for the refresh script.")
    parser.add_argument("--output", default=str(ROOT / "data/ohlcv/binance_futures/DATA_MANIFEST.json"))
    parser.add_argument("--quality-md", default=str(ROOT / "data/ohlcv/binance_futures/DATA_QUALITY_SUMMARY.md"))
    parser.add_argument("--quality-json", default=str(ROOT / "data/ohlcv/binance_futures/DATA_QUALITY_SUMMARY.json"))
    parser.add_argument("--holdout-policy", default=str(DEFAULT_HOLDOUT_POLICY))
    parser.add_argument("--assert-clean", action="store_true", help="Exit non-zero if the manifest verdict is not PASS.")
    return parser.parse_args()


def normalize_symbol(value: str) -> str:
    raw = value.strip().upper().replace("/", "").replace("-", "")
    if raw.endswith("USD") and not raw.endswith("USDT"):
        return raw[:-3] + "USDT"
    return raw


def _run_refresh(args: argparse.Namespace) -> dict[str, Any]:
    env = os.environ.copy()
    env["SYMBOLS"] = " ".join(normalize_symbol(symbol) for symbol in args.symbols)
    env["INTERVALS"] = " ".join(args.intervals)
    if args.start:
        env["START"] = args.start
    if args.end:
        env["END"] = args.end
    if args.force_refresh:
        env["FORCE"] = "1"
    result = subprocess.run(
        ["bash", str(ROOT / "tools/pull_binance_futures_universe.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": "bash tools/pull_binance_futures_universe.sh",
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def _maybe_derive(data_root: Path, symbol: str, tag: str, targets: list[str], mode: str) -> list[dict[str, Any]]:
    if mode == "off":
        return []
    source = data_root / symbol / f"{symbol}_15m_{tag}.csv"
    derived: list[dict[str, Any]] = []
    if not source.exists():
        return [{"symbol": symbol, "status": "skipped_missing_15m", "source": str(source)}]
    for target in targets:
        if target == "15m":
            continue
        output = data_root / symbol / f"{symbol}_{target}_{tag}.csv"
        if output.exists() and mode == "missing":
            derived.append({"symbol": symbol, "target": target, "status": "exists", "path": str(output)})
            continue
        htf = derive_htf(source, target)
        output.parent.mkdir(parents=True, exist_ok=True)
        htf.to_csv(output, index=False)
        derived.append({"symbol": symbol, "target": target, "status": "written", "rows": int(len(htf)), "path": str(output)})
    return derived


def _file_entry(path: Path, symbol: str, interval: str, tag: str) -> dict[str, Any]:
    summary = summarize_file(path, interval)
    role = "canonical_15m_source" if interval == "15m" else "derived_htf_from_15m"
    clean = bool(summary["exists"] and summary["gaps"] == 0 and summary["duplicates"] == 0 and summary["nan_ohlc"] == 0)
    entry = {
        "symbol": symbol,
        "interval": interval,
        "tag": tag,
        "role": role,
        "path": str(path),
        "sha256": file_sha256(path) if path.exists() else None,
        "quality": summary,
        "clean_for_research": clean,
        "warnings": [],
    }
    if summary["exists"] and int(summary.get("zero_volume") or 0) > 0:
        entry["warnings"].append("zero_volume_rows_present")
    return entry


def build_manifest(args: argparse.Namespace, refresh_result: dict[str, Any] | None, derive_results: list[dict[str, Any]]) -> dict[str, Any]:
    data_root = Path(args.data_root)
    symbols = [normalize_symbol(symbol) for symbol in args.symbols]
    files = [
        _file_entry(data_root / symbol / f"{symbol}_{interval}_{args.tag}.csv", symbol, interval, args.tag)
        for symbol in symbols
        for interval in args.intervals
    ]
    missing = [item for item in files if not item["quality"]["exists"]]
    dirty = [item for item in files if item["quality"]["exists"] and not item["clean_for_research"]]
    verdict = "PASS" if not missing and not dirty else "FAIL"
    policy = load_holdout_policy(args.holdout_policy)
    return {
        "manifest_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "canonical_contract": CANONICAL_CONTRACT,
        "data_root": str(data_root.resolve()),
        "symbols": symbols,
        "intervals": args.intervals,
        "tag": args.tag,
        "mode": "external_refresh_then_local_manifest" if args.refresh else "local_manifest_only",
        "refresh_result": refresh_result,
        "derive_htf": {
            "mode": args.derive_htf,
            "results": derive_results,
        },
        "holdout_policy": {
            "path": str(policy.path) if policy.path else None,
            "windows": [
                {
                    "name": window.name,
                    "start": window.start.isoformat(),
                    "end": None if window.end is None else window.end.isoformat(),
                    "symbols": list(window.symbols),
                    "actions": list(window.actions),
                    "reason": window.reason,
                }
                for window in policy.windows
            ],
        },
        "summary": {
            "file_count": len(files),
            "missing_count": len(missing),
            "dirty_count": len(dirty),
            "zero_volume_warning_count": sum(1 for item in files if "zero_volume_rows_present" in item["warnings"]),
        },
        "files": files,
    }


def main() -> None:
    args = parse_args()
    refresh_result = _run_refresh(args) if args.refresh else None
    if refresh_result and refresh_result["returncode"] != 0:
        print(json.dumps(refresh_result, indent=2), file=sys.stderr)
        raise SystemExit(refresh_result["returncode"])

    data_root = Path(args.data_root)
    symbols = [normalize_symbol(symbol) for symbol in args.symbols]
    derive_results: list[dict[str, Any]] = []
    for symbol in symbols:
        derive_results.extend(_maybe_derive(data_root, symbol, args.tag, list(args.intervals), args.derive_htf))

    manifest = build_manifest(args, refresh_result, derive_results)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    quality_rows = []
    for item in manifest["files"]:
        row = dict(item["quality"])
        row.update({"symbol": item["symbol"], "interval": item["interval"]})
        quality_rows.append(row)
    Path(args.quality_md).write_text(render_markdown(quality_rows), encoding="utf-8")
    Path(args.quality_json).write_text(json.dumps(quality_rows, indent=2), encoding="utf-8")

    print(f"Wrote data manifest to {output}")
    print(f"Verdict: {manifest['verdict']} ({manifest['summary']})")
    if args.assert_clean and manifest["verdict"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
