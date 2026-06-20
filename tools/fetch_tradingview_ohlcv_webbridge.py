#!/usr/bin/env python3
"""Fetch TradingView chart OHLCV through Kimi WebBridge.

This is a live-data fallback for cases where the exchange REST endpoint is not
reachable from the local environment. It queries the same TradingView symbol
shown in the user's browser, e.g. ``BINANCE:ETHUSDT.P``.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


WEBBRIDGE = "http://127.0.0.1:10086/command"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch OHLCV from TradingView via Kimi WebBridge.")
    parser.add_argument("--symbol", required=True, help="TradingView symbol, e.g. BINANCE:ETHUSDT.P")
    parser.add_argument("--interval", default="15", help="TradingView interval, e.g. 15, 60, 240, 1D.")
    parser.add_argument("--bars", type=int, default=2200)
    parser.add_argument("--session", default="tradingview-live-data")
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout-ms", type=int, default=60000)
    return parser.parse_args()


def webbridge_command(action: str, args: dict[str, Any] | None = None, session: str = "tradingview-live-data") -> dict[str, Any]:
    payload = {"action": action, "args": args or {}, "session": session}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        WEBBRIDGE,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _js(symbol: str, interval: str, bars: int, timeout_ms: int) -> str:
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
    send('quote_set_fields', [quoteSession, 'lp', 'lp_time', 'volume', 'ch', 'chp', 'exchange', 'pro_name', 'short_name', 'currency_code']);
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
          finish({{
            ok: true,
            symbol: tvSymbol,
            interval,
            barsRequested: bars,
            barsReturned: candles.length,
            startedAt,
            finishedAt: new Date().toISOString()
          }});
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


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = payload["candles"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume", "source"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "source": f"tradingview:{payload['symbol']}:{payload['interval']}"})


def main() -> None:
    args = parse_args()
    # Ensure there is a TradingView page in this WebBridge session. The data
    # websocket is most reliable when evaluated from tradingview.com.
    webbridge_command(
        "navigate",
        {"url": "https://www.tradingview.com/chart/?symbol=" + quote(args.symbol, safe="") + "&interval=" + args.interval, "newTab": True},
        session=args.session,
    )
    time.sleep(5)
    result = webbridge_command("evaluate", {"code": _js(args.symbol, args.interval, args.bars, args.timeout_ms)}, session=args.session)
    value = result.get("data", {}).get("value")
    if isinstance(value, str):
        payload = json.loads(value)
    else:
        payload = value
    if not payload or not payload.get("ok"):
        raise SystemExit(json.dumps(payload or result, indent=2))
    candles: list[dict[str, Any]] = []
    returned = int(payload["barsReturned"])
    chunk_size = 350
    for start in range(0, returned, chunk_size):
        code = f"JSON.stringify((window.__codex_tv_ohlcv_payload?.candles || []).slice({start}, {start + chunk_size}))"
        chunk_result = webbridge_command("evaluate", {"code": code}, session=args.session)
        chunk_value = chunk_result.get("data", {}).get("value")
        if isinstance(chunk_value, str):
            candles.extend(json.loads(chunk_value))
        elif isinstance(chunk_value, list):
            candles.extend(chunk_value)
        else:
            raise SystemExit(f"Unexpected chunk result for {start}: {chunk_result}")
    payload["candles"] = candles
    output = Path(args.output)
    write_csv(output, payload)
    meta = {
        "symbol": args.symbol,
        "interval": args.interval,
        "bars_requested": args.bars,
        "bars_returned": payload["barsReturned"],
        "first_timestamp": payload["candles"][0]["timestamp"],
        "last_timestamp": payload["candles"][-1]["timestamp"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
