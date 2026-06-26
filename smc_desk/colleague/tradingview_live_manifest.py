from __future__ import annotations

import csv
import json
import shutil
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd

from smc_desk.colleague.tradingview_alignment import expected_tradingview_symbol


WEBBRIDGE = "http://127.0.0.1:10086/command"
TIMEFRAMES = {
    "15m": {"tv_label": "15", "interval": "15", "duration": pd.Timedelta(minutes=15)},
    "1h": {"tv_label": "1H", "interval": "60", "duration": pd.Timedelta(hours=1)},
    "4h": {"tv_label": "4H", "interval": "240", "duration": pd.Timedelta(hours=4)},
    "1d": {"tv_label": "1D", "interval": "1D", "duration": pd.Timedelta(days=1)},
}


def webbridge_command(
    action: str,
    args: dict[str, Any] | None = None,
    session: str = "smc-tv-align",
    request_timeout: float = 90.0,
) -> dict[str, Any]:
    payload = {"action": action, "args": args or {}, "session": session}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        WEBBRIDGE,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=request_timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chart_url(tradingview_symbol: str, interval: str) -> str:
    return "https://www.tradingview.com/chart/?symbol=" + quote(tradingview_symbol, safe="") + "&interval=" + interval


def _tv_ws_js(symbol: str, interval: str, bars: int, timeout_ms: int) -> str:
    return f"""
(() => new Promise((resolve) => {{
  const tvSymbol = {json.dumps(symbol)};
  const interval = {json.dumps(interval)};
  const bars = {int(bars)};
  const timeoutMs = {int(timeout_ms)};
  const chartSession = 'cs_' + Math.random().toString(36).slice(2, 14);
  const quoteSession = 'qs_' + Math.random().toString(36).slice(2, 14);
  const ws = new WebSocket('wss://data.tradingview.com/socket.io/websocket');
  let done = false;
  const startedAt = new Date().toISOString();
  const wrap = (m, p) => {{
    const raw = JSON.stringify({{m, p}});
    return `~m~${{raw.length}}~m~${{raw}}`;
  }};
  const send = (m, p) => ws.send(wrap(m, p));
  const finish = (payload) => {{
    if (done) return;
    done = true;
    try {{ ws.close(); }} catch (e) {{}}
    resolve(JSON.stringify(payload));
  }};
  const parsePackets = (raw) => {{
    const packets = [];
    let rest = String(raw);
    while (rest.length > 0) {{
      if (rest.startsWith('~h~')) {{
        const next = rest.indexOf('~m~');
        packets.push({{heartbeat: rest.slice(3, next === -1 ? undefined : next)}});
        rest = next === -1 ? '' : rest.slice(next);
        continue;
      }}
      if (!rest.startsWith('~m~')) break;
      rest = rest.slice(3);
      const split = rest.indexOf('~m~');
      if (split === -1) break;
      const len = Number(rest.slice(0, split));
      const body = rest.slice(split + 3, split + 3 + len);
      rest = rest.slice(split + 3 + len);
      try {{ packets.push(JSON.parse(body)); }} catch (e) {{}}
    }}
    return packets;
  }};
  const timeout = setTimeout(() => finish({{
    ok: false,
    error: 'timeout',
    symbol: tvSymbol,
    interval,
    barsRequested: bars,
    startedAt,
    finishedAt: new Date().toISOString()
  }}), timeoutMs);
  ws.onopen = () => {{
    send('set_auth_token', ['unauthorized_user_token']);
    send('chart_create_session', [chartSession, '']);
    send('quote_create_session', [quoteSession]);
    send('quote_set_fields', [quoteSession, 'lp', 'lp_time', 'volume', 'exchange', 'pro_name', 'short_name', 'currency_code']);
    send('quote_add_symbols', [quoteSession, tvSymbol, {{flags: ['force_permission']}}]);
    const symbolSpec = JSON.stringify({{symbol: tvSymbol, adjustment: 'splits', session: 'regular'}});
    send('resolve_symbol', [chartSession, 'symbol_1', '=' + symbolSpec]);
    send('create_series', [chartSession, 's1', 's1', 'symbol_1', interval, bars]);
  }};
  ws.onerror = () => {{
    clearTimeout(timeout);
    finish({{ok: false, error: 'websocket_error', symbol: tvSymbol, interval, startedAt, finishedAt: new Date().toISOString()}});
  }};
  ws.onmessage = (event) => {{
    for (const packet of parsePackets(event.data)) {{
      if (packet.heartbeat) {{
        try {{ ws.send('~h~' + packet.heartbeat); }} catch (e) {{}}
        continue;
      }}
      if (packet.m === 'timescale_update') {{
        const series = packet.p?.[1]?.s1;
        const rows = series?.s || [];
        if (rows.length > 0) {{
          clearTimeout(timeout);
          const candles = rows.map((row) => {{
            const v = row.v || [];
            return {{
              timestamp: new Date(Number(v[0]) * 1000).toISOString(),
              open: Number(v[1]),
              high: Number(v[2]),
              low: Number(v[3]),
              close: Number(v[4]),
              volume: Number(v[5] || 0)
            }};
          }});
          window.__codex_tv_ohlcv_payload = {{
            ok: true,
            symbol: tvSymbol,
            interval,
            barsRequested: bars,
            barsReturned: candles.length,
            startedAt,
            finishedAt: new Date().toISOString(),
            candles
          }};
          finish({{ok: true, symbol: tvSymbol, interval, barsRequested: bars, barsReturned: candles.length, startedAt, finishedAt: new Date().toISOString()}});
          return;
        }}
      }}
      if (packet.m === 'series_error') {{
        clearTimeout(timeout);
        finish({{ok: false, error: 'series_error', detail: packet.p, symbol: tvSymbol, interval, startedAt, finishedAt: new Date().toISOString()}});
        return;
      }}
    }}
  }};
}}))()
"""


def _extract_payload(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("data", {}).get("value")
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, dict):
        return value
    raise RuntimeError(f"WebBridge returned no JSON payload: {result}")


def fetch_tradingview_ohlcv(
    *,
    tradingview_symbol: str,
    interval: str,
    bars: int,
    session: str,
    timeout_ms: int,
) -> dict[str, Any]:
    request_timeout = max(90.0, float(timeout_ms) / 1000.0 + 30.0)
    result = webbridge_command(
        "evaluate",
        {"code": _tv_ws_js(tradingview_symbol, interval, bars, timeout_ms)},
        session=session,
        request_timeout=request_timeout,
    )
    payload = _extract_payload(result)
    if not payload.get("ok"):
        raise RuntimeError(f"TradingView OHLCV fetch failed: {payload}")
    candles: list[dict[str, Any]] = []
    returned = int(payload["barsReturned"])
    chunk_size = 350
    for start in range(0, returned, chunk_size):
        code = f"JSON.stringify((window.__codex_tv_ohlcv_payload?.candles || []).slice({start}, {start + chunk_size}))"
        chunk = webbridge_command("evaluate", {"code": code}, session=session)
        value = chunk.get("data", {}).get("value")
        if isinstance(value, str):
            candles.extend(json.loads(value))
        elif isinstance(value, list):
            candles.extend(value)
        else:
            raise RuntimeError(f"Unexpected OHLCV chunk result: {chunk}")
    payload["candles"] = candles
    return payload


def closed_candles(payload: dict[str, Any], timeframe: str, now: pd.Timestamp | None = None) -> list[dict[str, Any]]:
    now = now or pd.Timestamp.now(tz="UTC")
    duration = TIMEFRAMES[timeframe]["duration"]
    closed: list[dict[str, Any]] = []
    for row in payload.get("candles", []):
        open_time = pd.Timestamp(row["timestamp"])
        if open_time.tzinfo is None:
            open_time = open_time.tz_localize("UTC")
        else:
            open_time = open_time.tz_convert("UTC")
        if open_time + duration <= now:
            clean = dict(row)
            clean["timestamp"] = open_time.isoformat()
            closed.append(clean)
    return closed


def write_ohlcv_csv(path: Path, rows: list[dict[str, Any]], source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume", "source"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "timestamp": row["timestamp"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row.get("volume", 0),
                    "source": source,
                }
            )


def capture_screenshot(path: Path, session: str) -> Path:
    result = webbridge_command("screenshot", {"format": "png"}, session=session)
    if not result.get("ok"):
        raise RuntimeError(f"Screenshot failed: {result}")
    source_path = Path(result["data"]["path"])
    if not source_path.exists():
        raise FileNotFoundError(f"Screenshot missing at daemon path: {source_path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, path)
    return path


def build_manifest_from_closed_data(
    *,
    symbol: str,
    tradingview_symbol: str,
    output_dir: Path,
    screenshots: dict[str, Path],
    ohlcv_paths: dict[str, Path],
    closed_by_tf: dict[str, list[dict[str, Any]]],
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    chart_state_timeframes: dict[str, Any] = {}
    for tf, rows in closed_by_tf.items():
        if not rows:
            raise ValueError(f"No closed TradingView candles for {tf}.")
        last = rows[-1]
        open_time = pd.Timestamp(last["timestamp"])
        if open_time.tzinfo is None:
            open_time = open_time.tz_localize("UTC")
        else:
            open_time = open_time.tz_convert("UTC")
        close_time = open_time + TIMEFRAMES[tf]["duration"]
        chart_state_timeframes[tf] = {
            "tradingview_symbol": tradingview_symbol,
            "symbol": tradingview_symbol,
            "interval": TIMEFRAMES[tf]["interval"],
            "timeframe": tf,
            "candle_type": "candles",
            "scale": "linear",
            "timezone": "UTC",
            "last_closed_candle_open": open_time.isoformat(),
            "last_closed_candle_close": close_time.isoformat(),
            "last_closed_ohlc": {
                "open": last["open"],
                "high": last["high"],
                "low": last["low"],
                "close": last["close"],
                "volume": last.get("volume", 0),
            },
        }
    return {
        "instrument": symbol,
        "exchange": "BINANCE",
        "tradingview_symbol": tradingview_symbol,
        "captured_at": (captured_at or datetime.now(timezone.utc)).isoformat(),
        "capture_method": "kimi_webbridge_tradingview_ohlcv_and_screenshot",
        "screenshots": {TIMEFRAMES[tf]["tv_label"]: str(path.resolve()) for tf, path in screenshots.items()},
        "ohlcv": {tf: str(path.resolve()) for tf, path in ohlcv_paths.items()},
        "chart_state": {
            "symbol": tradingview_symbol,
            "exchange": "BINANCE",
            "instrument": symbol,
            "candle_type": "candles",
            "scale": "linear",
            "timezone": "UTC",
            "timeframes": chart_state_timeframes,
        },
        "notes": [
            "TradingView evidence is visual/chart-state verification only.",
            "Local OHLCV remains the analysis source unless this CSV is deliberately passed as source.",
        ],
    }


def build_live_alignment_manifest(
    *,
    symbol: str,
    output_dir: Path,
    session: str = "smc-tv-align",
    bars: int = 500,
    timeout_ms: int = 60000,
) -> tuple[Path, dict[str, Any]]:
    symbol = symbol.strip().upper().replace("/", "").replace("-", "")
    tradingview_symbol = expected_tradingview_symbol(symbol)
    output_dir = output_dir.expanduser().resolve()
    screenshots: dict[str, Path] = {}
    ohlcv_paths: dict[str, Path] = {}
    closed_by_tf: dict[str, list[dict[str, Any]]] = {}

    for tf, meta in TIMEFRAMES.items():
        url = chart_url(tradingview_symbol, str(meta["interval"]))
        webbridge_command("navigate", {"url": url, "newTab": tf == "15m"}, session=session)
        time.sleep(3)
        screenshot_path = output_dir / "screenshots" / f"{symbol}_{tf}.png"
        capture_screenshot(screenshot_path, session=session)
        screenshots[tf] = screenshot_path
        payload = fetch_tradingview_ohlcv(
            tradingview_symbol=tradingview_symbol,
            interval=str(meta["interval"]),
            bars=bars,
            session=session,
            timeout_ms=timeout_ms,
        )
        closed = closed_candles(payload, tf)
        closed_by_tf[tf] = closed
        csv_path = output_dir / "ohlcv" / f"{symbol}_{tf}_tradingview.csv"
        write_ohlcv_csv(csv_path, closed, source=f"tradingview:{tradingview_symbol}:{meta['interval']}")
        ohlcv_paths[tf] = csv_path

    manifest = build_manifest_from_closed_data(
        symbol=symbol,
        tradingview_symbol=tradingview_symbol,
        output_dir=output_dir,
        screenshots=screenshots,
        ohlcv_paths=ohlcv_paths,
        closed_by_tf=closed_by_tf,
    )
    manifest_path = output_dir / "tradingview_alignment_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path, manifest
