from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from smc_desk.case_library import file_sha256


TIMEFRAME_ALIASES: dict[str, str] = {
    "15": "15m",
    "15m": "15m",
    "m15": "15m",
    "1h": "1h",
    "1H": "1h",
    "60": "1h",
    "4h": "4h",
    "4H": "4h",
    "240": "4h",
    "1d": "1d",
    "1D": "1d",
    "D": "1d",
}
TV_INTERVALS: dict[str, set[str]] = {
    "15m": {"15", "15m", "15M"},
    "1h": {"60", "1h", "1H"},
    "4h": {"240", "4h", "4H"},
    "1d": {"1D", "1d", "D"},
}
REQUIRED_TIMEFRAMES = ("15m", "1h", "4h", "1d")
TIMEFRAME_DURATIONS = {
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}


def expected_tradingview_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper().replace("/", "").replace("-", "")
    return f"BINANCE:{normalized}.P"


def normalize_timeframe(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    return TIMEFRAME_ALIASES.get(raw) or TIMEFRAME_ALIASES.get(raw.upper())


def _check(name: str, passed: bool, expected: Any = None, observed: Any = None, severity: str = "error") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "expected": expected,
        "observed": observed,
    }


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value in {None, ""}:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def _canonical_screenshots(capture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    screenshots = capture.get("screenshot_hashes") or {}
    if not screenshots and isinstance(capture.get("payload"), dict):
        raw_screenshots = capture["payload"].get("screenshots") or {}
        screenshots = {
            key: {
                "path": str(Path(str(path)).expanduser().resolve()),
                "exists": Path(str(path)).expanduser().exists(),
                "sha256": file_sha256(Path(str(path)).expanduser()) if Path(str(path)).expanduser().exists() else None,
            }
            for key, path in raw_screenshots.items()
        }
    canonical: dict[str, dict[str, Any]] = {}
    for label, meta in screenshots.items():
        tf = normalize_timeframe(label)
        if tf:
            canonical[tf] = dict(meta)
    return canonical


def _state_for_timeframe(payload: dict[str, Any], tf: str) -> dict[str, Any]:
    state = payload.get("chart_state") or payload.get("verified_chart_state") or payload.get("state") or {}
    if not isinstance(state, dict):
        return {}
    timeframes = state.get("timeframes") or state.get("timeframe_states") or {}
    direct = timeframes.get(tf) or timeframes.get(tf.upper()) or timeframes.get(tf.replace("m", "")) or {}
    if direct:
        combined = dict(state)
        combined.update(direct)
        return combined
    return state if normalize_timeframe(state.get("timeframe") or state.get("interval")) == tf else {}


def _read_ohlcv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "timestamp" not in df.columns:
        raise ValueError(f"TradingView OHLCV CSV missing timestamp column: {path}")
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(None)
    return df.sort_values("timestamp").reset_index(drop=True)


def _compare_tv_ohlcv(
    *,
    payload: dict[str, Any],
    timeframe_dfs: dict[str, pd.DataFrame],
    decision_candle_open: pd.Timestamp,
    tolerance: float = 1e-8,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    summary: dict[str, Any] = {"status": "not_supplied", "timeframes": {}}
    raw = payload.get("ohlcv") or payload.get("ohlcv_csvs") or payload.get("tradingview_ohlcv") or {}
    if not isinstance(raw, dict) or not raw:
        return checks, summary

    summary["status"] = "checked"
    source_start = None
    if "15m" in timeframe_dfs and not timeframe_dfs["15m"].empty:
        source_start = pd.to_datetime(timeframe_dfs["15m"]["timestamp"], utc=True).dt.tz_convert(None).min()
    for label, raw_path in raw.items():
        tf = normalize_timeframe(label)
        if not tf or tf not in timeframe_dfs:
            checks.append(_check(f"ohlcv_{label}_timeframe_supported", False, REQUIRED_TIMEFRAMES, label))
            continue
        tv_path = Path(str(raw_path)).expanduser()
        if not tv_path.exists():
            checks.append(_check(f"ohlcv_{tf}_file_exists", False, "existing CSV", str(tv_path)))
            continue
        try:
            tv_df = _read_ohlcv(tv_path)
        except Exception as exc:
            checks.append(_check(f"ohlcv_{tf}_readable", False, "readable OHLCV CSV", str(exc)))
            continue

        local = timeframe_dfs[tf].copy()
        local["timestamp"] = pd.to_datetime(local["timestamp"], utc=True).dt.tz_convert(None)
        if source_start is not None and tf != "15m":
            # A short live 15m pull cannot reconstruct the first HTF bucket if
            # the source starts after that bucket opened. Compare only HTF
            # candles whose full source window exists locally.
            local = local.loc[local["timestamp"] >= source_start]
        local = local.loc[local["timestamp"] <= decision_candle_open].tail(20)
        merged = pd.merge(local, tv_df, on="timestamp", how="inner", suffixes=("_local", "_tv"))
        if merged.empty:
            checks.append(_check(f"ohlcv_{tf}_overlap", False, "overlapping timestamps", {"tv_rows": len(tv_df), "local_rows": len(local)}))
            summary["timeframes"][tf] = {"matched_rows": 0}
            continue
        mismatches = []
        for _, row in merged.iterrows():
            for col in ("open", "high", "low", "close"):
                if abs(float(row[f"{col}_local"]) - float(row[f"{col}_tv"])) > tolerance:
                    mismatches.append(
                        {
                            "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
                            "field": col,
                            "local": float(row[f"{col}_local"]),
                            "tradingview": float(row[f"{col}_tv"]),
                        }
                    )
        summary["timeframes"][tf] = {
            "path": str(tv_path.resolve()),
            "sha256": file_sha256(tv_path),
            "matched_rows": int(len(merged)),
            "mismatches": mismatches[:10],
        }
        checks.append(_check(f"ohlcv_{tf}_matches_local", not mismatches, "exact OHLC match on overlap", summary["timeframes"][tf]))
    return checks, summary


def build_alignment_report(
    *,
    capture: dict[str, Any],
    symbol: str,
    decision_candle_open: pd.Timestamp,
    decision_available_at: pd.Timestamp,
    timeframe_dfs: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Validate external TradingView evidence without granting it market authority."""

    expected_symbol = expected_tradingview_symbol(symbol)
    expected_by_tf: dict[str, dict[str, Any]] = {}
    for tf in REQUIRED_TIMEFRAMES:
        df = timeframe_dfs.get(tf)
        if df is not None and not df.empty:
            open_time = pd.Timestamp(df["timestamp"].iloc[-1])
            if open_time.tzinfo is not None:
                open_time = open_time.tz_convert("UTC").tz_localize(None)
            expected_by_tf[tf] = {
                "last_closed_candle_open": open_time.isoformat(),
                "last_closed_candle_close": (open_time + TIMEFRAME_DURATIONS[tf]).isoformat(),
            }
    expected = {
        "tradingview_symbol": expected_symbol,
        "exchange": "BINANCE",
        "instrument": symbol,
        "required_timeframes": list(REQUIRED_TIMEFRAMES),
        "decision_candle_open": decision_candle_open.isoformat(),
        "decision_available_at": decision_available_at.isoformat(),
        "timeframe_last_closed_candles": expected_by_tf,
        "candle_type": "candles",
        "price_scale": "linear",
        "timezone": "UTC",
    }
    if capture.get("status") != "attached":
        return {
            "status": "NOT_ATTACHED",
            "passed": False,
            "authority": "TradingView screenshots are visual evidence, not OHLCV authority.",
            "expected": expected,
            "checks": [_check("capture_attached", False, "attached TradingView/WebBridge manifest", capture.get("status"))],
            "summary": "No TradingView/WebBridge manifest was attached.",
        }

    payload = capture.get("payload") if isinstance(capture.get("payload"), dict) else {}
    visual_only = str(payload.get("verification_status") or "").lower() == "visual_only_unverified_candle_state"
    checks: list[dict[str, Any]] = []

    observed_symbol = str(payload.get("tradingview_symbol") or payload.get("symbol") or "").upper()
    observed_exchange = str(payload.get("exchange") or "").upper()
    observed_instrument = str(payload.get("instrument") or "").upper().replace("/", "").replace("-", "")
    checks.append(_check("tradingview_symbol", observed_symbol == expected_symbol, expected_symbol, observed_symbol))
    checks.append(_check("exchange", observed_exchange == "BINANCE", "BINANCE", observed_exchange))
    checks.append(_check("instrument", observed_instrument == symbol, symbol, observed_instrument))

    screenshots = _canonical_screenshots(capture)
    for tf in REQUIRED_TIMEFRAMES:
        meta = screenshots.get(tf)
        checks.append(_check(f"screenshot_{tf}_exists", bool(meta and meta.get("exists") and meta.get("sha256")), "existing screenshot with sha256", meta))

    chart_state_proofs = []
    for tf in REQUIRED_TIMEFRAMES:
        state = _state_for_timeframe(payload, tf)
        if not state:
            checks.append(_check(f"chart_state_{tf}_present", False, "verified chart_state for timeframe", None))
            continue
        checks.append(_check(f"chart_state_{tf}_present", True, "verified chart_state for timeframe", "present"))
        interval = str(state.get("interval") or state.get("timeframe") or "")
        checks.append(_check(f"chart_state_{tf}_interval", interval in TV_INTERVALS[tf], sorted(TV_INTERVALS[tf]), interval))
        checks.append(_check(f"chart_state_{tf}_candle_type", str(state.get("candle_type") or "").lower() in {"candles", "ohlc", "bars"}, "candles/bars", state.get("candle_type")))
        checks.append(_check(f"chart_state_{tf}_scale", str(state.get("scale") or state.get("price_scale") or "").lower() == "linear", "linear", state.get("scale") or state.get("price_scale")))
        checks.append(_check(f"chart_state_{tf}_timezone", str(state.get("timezone") or "").upper() in {"UTC", "ETC/UTC"}, "UTC", state.get("timezone")))
        state_symbol = str(state.get("tradingview_symbol") or state.get("symbol") or observed_symbol).upper()
        checks.append(_check(f"chart_state_{tf}_symbol", state_symbol == expected_symbol, expected_symbol, state_symbol))
        last_open = _timestamp(
            state.get("last_closed_candle_open")
            or state.get("decision_candle_open")
            or state.get("last_visible_candle_open")
        )
        last_close = _timestamp(
            state.get("last_closed_candle_close")
            or state.get("decision_available_at")
            or state.get("last_visible_candle_close")
        )
        expected_open = _timestamp(expected_by_tf.get(tf, {}).get("last_closed_candle_open"))
        expected_close = _timestamp(expected_by_tf.get(tf, {}).get("last_closed_candle_close"))
        timing_severity = "warning" if visual_only and last_open is None and last_close is None else "error"
        checks.append(_check(f"chart_state_{tf}_last_closed_open", last_open == expected_open, None if expected_open is None else expected_open.isoformat(), None if last_open is None else last_open.isoformat(), severity=timing_severity))
        checks.append(_check(f"chart_state_{tf}_last_closed_close", last_close == expected_close, None if expected_close is None else expected_close.isoformat(), None if last_close is None else last_close.isoformat(), severity=timing_severity))
        chart_state_proofs.append(tf)

    ohlcv_checks, ohlcv_summary = _compare_tv_ohlcv(
        payload=payload,
        timeframe_dfs=timeframe_dfs,
        decision_candle_open=decision_candle_open,
    )
    checks.extend(ohlcv_checks)

    blocking_failures = [check for check in checks if check["severity"] == "error" and not check["passed"]]
    warning_failures = [check for check in checks if check["severity"] == "warning" and not check["passed"]]
    status = "FAIL" if blocking_failures else "PARTIAL" if warning_failures else "PASS"
    return {
        "status": status,
        "passed": status in {"PASS", "PARTIAL"},
        "authority": "TradingView/WebBridge can verify visual/chart-state alignment only; local OHLCV remains market truth.",
        "expected": expected,
        "observed": {
            "tradingview_symbol": observed_symbol,
            "exchange": observed_exchange,
            "instrument": observed_instrument,
            "screenshots": screenshots,
            "chart_state_timeframes": chart_state_proofs,
            "ohlcv_comparison": ohlcv_summary,
        },
        "checks": checks,
        "blocking_failures": blocking_failures,
        "summary": ("TradingView/WebBridge evidence aligned." if status == "PASS" else "TradingView screenshots attached, but visible candle timing remains unverified." if status == "PARTIAL" else "TradingView/WebBridge evidence did not satisfy strict alignment."),
    }
