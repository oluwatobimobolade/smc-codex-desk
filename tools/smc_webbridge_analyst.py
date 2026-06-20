#!/usr/bin/env python3
"""
SMC Elite Analyst — WebBridge Chart Capture Tool

Uses the local Kimi WebBridge daemon to open TradingView, switch through
Daily / 4H / 1H / 15m timeframes, and capture screenshots for later analysis.

Usage:
    python3 tools/smc_webbridge_analyst.py --instrument XAUUSD
    python3 tools/smc_webbridge_analyst.py --instrument EURUSD --session my-analysis

Requirements:
    - Kimi WebBridge running on http://127.0.0.1:10086
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional runtime guard
    Image = None

WEBBRIDGE = "http://127.0.0.1:10086/command"
JOURNAL_ROOT = Path("/Users/tobimobolade/smc-codex-desk/journal")
MIN_CHART_COLOR_RATIO = 0.003

DEFAULT_EXCHANGE_BY_INSTRUMENT = {
    "BTCUSD": "BITSTAMP",
    "ETHUSD": "BITSTAMP",
}
DEFAULT_TRADINGVIEW_SYMBOL_BY_INSTRUMENT = {
    "BTCUSDT": "BINANCE:BTCUSDT.P",
    "ETHUSDT": "BINANCE:ETHUSDT.P",
    "SOLUSDT": "BINANCE:SOLUSDT.P",
    "XRPUSDT": "BINANCE:XRPUSDT.P",
    "BNBUSDT": "BINANCE:BNBUSDT.P",
}


def webbridge_command(action: str, args: dict | None = None, session: str = "smc-elite") -> dict:
    payload = {"action": action, "args": args or {}, "session": session}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        WEBBRIDGE,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def walk_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_nodes(child)


def find_button_ref(snapshot_payload: dict, wanted_name: str) -> str | None:
    wanted = wanted_name.casefold()
    for node in walk_nodes(snapshot_payload):
        if node.get("role") != "button":
            continue
        name = str(node.get("name") or "").casefold()
        if wanted in name and node.get("ref"):
            return str(node["ref"])
    return None


def find_textbox_ref(snapshot_payload: dict, wanted_name: str) -> str | None:
    wanted = wanted_name.casefold()
    for node in walk_nodes(snapshot_payload):
        if node.get("role") != "textbox":
            continue
        name = str(node.get("name") or "").casefold()
        if wanted in name and node.get("ref"):
            return str(node["ref"])
    return None


def has_named_node(snapshot_payload: dict, wanted_name: str) -> bool:
    wanted = wanted_name.casefold()
    return any(wanted in str(node.get("name") or "").casefold() for node in walk_nodes(snapshot_payload))


def write_snapshot_summary(snapshot_payload: dict, path: Path) -> None:
    lines: list[str] = []
    for node in walk_nodes(snapshot_payload):
        role = node.get("role")
        name = node.get("name")
        ref = node.get("ref")
        if role in {"button", "textbox", "tab", "menuitem", "link"} and (name or ref):
            lines.append(f"{role}\t{ref or ''}\t{name or ''}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_webbridge(session: str = "smc-elite") -> None:
    try:
        result = webbridge_command("list_tabs", session=session)
    except Exception as exc:
        raise RuntimeError(
            "Kimi WebBridge is not running. Start it with: ~/.kimi-webbridge/bin/kimi-webbridge start"
        ) from exc


TIMEFRAME_INTERVAL = {
    "1D": "1D",
    "4H": "240",
    "1H": "60",
    "15": "15",
}


def normalize_tradingview_symbol(instrument: str, exchange: str | None = None) -> tuple[str, str, str | None]:
    """Return (TradingView symbol, plain instrument, exchange).

    Screenshots are only useful when they point at the same venue as the OHLCV
    feed. Binance USD-M perp symbols default to TradingView's ``.P`` contracts.
    BTCUSD/ETHUSD stay on Bitstamp as legacy spot symbols.
    """
    raw = instrument.strip().upper().replace("/", "").replace("-", "")
    if ":" in raw:
        prefix, name = raw.split(":", 1)
        return f"{prefix}:{name}", name, prefix

    if not exchange and raw in DEFAULT_TRADINGVIEW_SYMBOL_BY_INSTRUMENT:
        tv_symbol = DEFAULT_TRADINGVIEW_SYMBOL_BY_INSTRUMENT[raw]
        prefix, name = tv_symbol.split(":", 1)
        return tv_symbol, raw, prefix

    chosen_exchange = exchange.strip().upper() if exchange else DEFAULT_EXCHANGE_BY_INSTRUMENT.get(raw)
    if chosen_exchange:
        return f"{chosen_exchange}:{raw}", raw, chosen_exchange
    return raw, raw, None


def build_chart_url(tradingview_symbol: str, timeframe: str = "1D") -> str:
    interval = TIMEFRAME_INTERVAL.get(timeframe, timeframe)
    symbol = quote(tradingview_symbol, safe="")
    return f"https://www.tradingview.com/chart/?symbol={symbol}&interval={interval}"


def open_chart(tradingview_symbol: str, session: str, timeframe: str = "1D") -> None:
    url = build_chart_url(tradingview_symbol, timeframe)
    print(f"Opening TradingView: {url}")
    result = webbridge_command("navigate", {"url": url, "newTab": True}, session=session)
    if not result.get("ok") or not result.get("data", {}).get("success"):
        raise RuntimeError(f"Failed to navigate: {result}")
    # Wait for chart to load.
    time.sleep(4)


def change_timeframe(timeframe: str, tradingview_symbol: str, session: str) -> str:
    """
    Change TradingView timeframe by navigating to the same chart with a
    different interval URL parameter. This is more reliable than keyboard
    shortcuts because it does not depend on which element has focus.
    """
    url = build_chart_url(tradingview_symbol, timeframe)
    print(f"Switching to {timeframe} timeframe...")
    result = webbridge_command("navigate", {"url": url, "newTab": False}, session=session)
    if not result.get("ok") or not result.get("data", {}).get("success"):
        raise RuntimeError(f"Failed to navigate: {result}")
    # Allow chart to redraw.
    time.sleep(3)
    return url


def capture_screenshot(timeframe: str, output_path: Path, session: str) -> Path:
    print(f"Capturing {timeframe} screenshot -> {output_path}")
    result = webbridge_command("screenshot", {"format": "png"}, session=session)
    if not result.get("ok"):
        raise RuntimeError(f"Screenshot failed: {result}")

    source_path = Path(result["data"]["path"])
    if not source_path.exists():
        raise FileNotFoundError(f"Screenshot not found at daemon path: {source_path}")

    # Copy the daemon screenshot to the journal location.
    shutil.copy2(source_path, output_path)
    return output_path


def save_current_screenshot(output_path: Path, session: str) -> Path:
    result = webbridge_command("screenshot", {"format": "png"}, session=session)
    if not result.get("ok"):
        raise RuntimeError(f"Screenshot failed: {result}")
    source_path = Path(result["data"]["path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, output_path)
    return output_path


def set_pine_editor_with_js(session: str, code: str) -> dict:
    script = f"""
(() => {{
  const code = {json.dumps(code)};
  const result = {{ success: false, method: null, length: 0, detail: [] }};

  if (window.monaco?.editor?.getModels) {{
    const models = window.monaco.editor.getModels();
    result.detail.push(`monaco_models=${{models.length}}`);
    if (models.length > 0) {{
      models[0].setValue(code);
      result.success = models[0].getValue() === code;
      result.method = "monaco_model";
      result.length = models[0].getValue().length;
      return result;
    }}
  }}

  const selectors = [
    '.cm-editor .cm-content',
    '[role="textbox"][aria-label*="Editor content"]',
    '.monaco-editor textarea.inputarea',
    'textarea'
  ];

  for (const selector of selectors) {{
    const el = document.querySelector(selector);
    if (!el) {{
      result.detail.push(`${{selector}}=missing`);
      continue;
    }}
    result.detail.push(`${{selector}}=found`);
    el.focus();
    if (el.isContentEditable) {{
      document.execCommand('selectAll', false, null);
      const ok = document.execCommand('insertText', false, code);
      el.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: code.slice(0, 1000) }}));
      result.success = ok || (el.innerText || el.textContent || '').includes('SMC Desk Overlay');
      result.method = selector;
      result.length = (el.innerText || el.textContent || '').length;
      return result;
    }}
    if ('value' in el) {{
      const setter =
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set ||
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      if (setter) setter.call(el, code);
      else el.value = code;
      el.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: code.slice(0, 1000) }}));
      el.dispatchEvent(new Event('change', {{ bubbles: true }}));
      result.success = el.value === code;
      result.method = selector;
      result.length = el.value.length;
      return result;
    }}
  }}

  result.detail.push(`body=${{document.body.innerText.slice(0, 500)}}`);
  return result;
}})()
"""
    evaluated = webbridge_command("evaluate", {"code": script}, session=session)
    if not evaluated.get("ok"):
        raise RuntimeError(f"Editor JS injection failed: {evaluated}")
    value = evaluated.get("data", {}).get("value")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {"success": False, "method": "unknown", "length": 0, "detail": [value]}
    if not isinstance(value, dict):
        value = {"success": False, "method": "unknown", "length": 0, "detail": [repr(value)]}
    return value


def chart_color_ratio(path: Path) -> float | None:
    """Estimate whether the chart pane contains rendered candles.

    TradingView can report the right symbol while the pane is still blank. The
    crop intentionally avoids the toolbar and watchlist, then looks for
    saturated red/green candle pixels.
    """
    if Image is None:
        return None
    with Image.open(path).convert("RGB") as image:
        width, height = image.size
        left = 80
        top = 120
        right = int(width * 0.72)
        bottom = int(height * 0.90)
        crop = image.crop((left, top, right, bottom))
        pixels = crop.load()
        colorful = 0
        sampled = 0
        for y in range(0, crop.height, 2):
            for x in range(0, crop.width, 2):
                r, g, b = pixels[x, y]
                sampled += 1
                if max(r, g, b) > 70 and max(r, g, b) - min(r, g, b) > 35:
                    colorful += 1
        return colorful / max(1, sampled)


def screenshot_has_chart(path: Path) -> tuple[bool, str]:
    ratio = chart_color_ratio(path)
    if ratio is None:
        ok = path.stat().st_size > 120_000
        return ok, f"size={path.stat().st_size}"
    return ratio >= MIN_CHART_COLOR_RATIO, f"chart_color_ratio={ratio:.4f}"


def capture_valid_screenshot(timeframe: str, output_path: Path, session: str, retry_url: str, attempts: int = 4) -> Path:
    wait_seconds = 6
    last_reason = "not captured"
    for attempt in range(1, attempts + 1):
        path = capture_screenshot(timeframe, output_path, session=session)
        ok, reason = screenshot_has_chart(path)
        last_reason = reason
        if ok:
            print(f"Validated {timeframe} chart screenshot ({reason}).")
            return path
        if attempt < attempts:
            print(f"{timeframe} screenshot looks blank ({reason}); retrying after reload {attempt}/{attempts - 1}.")
            webbridge_command("navigate", {"url": retry_url, "newTab": False}, session=session)
            time.sleep(wait_seconds)
            wait_seconds += 3
    raise RuntimeError(f"{timeframe} chart did not render after {attempts} attempts ({last_reason}).")


def probe_pine_panel(session: str, output_dir: Path, wait_seconds: float = 8.0) -> None:
    ensure_webbridge(session=session)
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshot = webbridge_command("snapshot", session=session)
    if not snapshot.get("ok"):
        raise RuntimeError(f"Snapshot failed: {snapshot}")
    if not has_named_node(snapshot["data"], "Pine Editor"):
        pine_ref = find_button_ref(snapshot["data"], "Pine")
        if not pine_ref:
            raise RuntimeError("Could not find TradingView Pine button in the current chart snapshot.")
        clicked = webbridge_command("click", {"selector": pine_ref}, session=session)
        if not clicked.get("ok"):
            raise RuntimeError(f"Could not open Pine panel: {clicked}")
    time.sleep(wait_seconds)

    after = webbridge_command("snapshot", session=session)
    if not after.get("ok"):
        raise RuntimeError(f"Snapshot after Pine click failed: {after}")
    (output_dir / "pine_panel_snapshot.json").write_text(json.dumps(after["data"], indent=2), encoding="utf-8")
    write_snapshot_summary(after["data"], output_dir / "pine_panel_snapshot_summary.tsv")
    image_path = save_current_screenshot(output_dir / "pine_panel_probe.png", session=session)
    print(f"Pine panel snapshot: {output_dir / 'pine_panel_snapshot.json'}")
    print(f"Pine panel summary: {output_dir / 'pine_panel_snapshot_summary.tsv'}")
    print(f"Pine panel screenshot: {image_path}")


def install_pine_overlay(session: str, pine_script: Path, output_dir: Path, wait_seconds: float = 8.0) -> None:
    if not pine_script.exists():
        raise FileNotFoundError(f"Pine script not found: {pine_script}")
    output_dir.mkdir(parents=True, exist_ok=True)

    probe_pine_panel(session=session, output_dir=output_dir / "before_install", wait_seconds=wait_seconds)
    snapshot = webbridge_command("snapshot", session=session)
    if not snapshot.get("ok"):
        raise RuntimeError(f"Snapshot failed before install: {snapshot}")

    editor_ref = find_textbox_ref(snapshot["data"], "Editor content")
    if not editor_ref:
        raise RuntimeError("Could not find Pine Editor textbox after opening the panel.")

    code = pine_script.read_text(encoding="utf-8")
    print(f"Filling Pine Editor with {len(code)} characters from {pine_script}...")
    filled = webbridge_command("fill", {"selector": editor_ref, "value": code}, session=session)
    if not filled.get("ok"):
        print(f"Direct fill failed; trying editor-model injection: {filled}")
        injected = set_pine_editor_with_js(session=session, code=code)
        print(f"Editor-model injection result: {json.dumps(injected, sort_keys=True)}")
        if not injected.get("success"):
            # TradingView virtualizes the editor, so DOM text length can reflect
            # only the visible viewport even after a successful paste.
            if not injected.get("method") or int(injected.get("length") or 0) < 100:
                raise RuntimeError(f"Could not fill Pine Editor: {filled}; injection={injected}")
            print("Editor content appears to be present; continuing despite virtualized verification.")
    time.sleep(2)
    save_current_screenshot(output_dir / "after_fill.png", session=session)

    after_fill = webbridge_command("snapshot", session=session)
    if not after_fill.get("ok"):
        raise RuntimeError(f"Snapshot failed after fill: {after_fill}")
    write_snapshot_summary(after_fill["data"], output_dir / "after_fill_summary.tsv")

    add_ref = find_button_ref(after_fill["data"], "Add to chart")
    if not add_ref:
        raise RuntimeError("Could not find Add to chart button after filling Pine Editor.")

    print("Clicking Add to chart...")
    clicked = webbridge_command("click", {"selector": add_ref}, session=session)
    if not clicked.get("ok"):
        raise RuntimeError(f"Add to chart failed: {clicked}")
    time.sleep(wait_seconds)

    final_snapshot = webbridge_command("snapshot", session=session)
    if not final_snapshot.get("ok"):
        raise RuntimeError(f"Snapshot failed after Add to chart: {final_snapshot}")
    (output_dir / "after_add_snapshot.json").write_text(json.dumps(final_snapshot["data"], indent=2), encoding="utf-8")
    write_snapshot_summary(final_snapshot["data"], output_dir / "after_add_summary.tsv")
    final_image = save_current_screenshot(output_dir / "after_add_to_chart.png", session=session)
    print(f"After-fill screenshot: {output_dir / 'after_fill.png'}")
    print(f"After-add snapshot: {output_dir / 'after_add_snapshot.json'}")
    print(f"After-add summary: {output_dir / 'after_add_summary.tsv'}")
    print(f"After-add screenshot: {final_image}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture TradingView screenshots for SMC analysis")
    parser.add_argument(
        "--mode",
        choices=["capture", "probe-pine", "install-pine"],
        default="capture",
        help="Operation to run. capture collects chart screenshots; probe-pine opens Pine Editor; install-pine fills and adds an overlay.",
    )
    parser.add_argument("--instrument", help="Instrument symbol, e.g. BTCUSDT, XAUUSD, EURUSD, or BINANCE:BTCUSDT.P")
    parser.add_argument(
        "--exchange",
        help="TradingView exchange prefix. Binance futures pairs default to BINANCE:<SYMBOL>.P; BTCUSD/ETHUSD remain legacy BITSTAMP spot.",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="WebBridge session name (default: instrument-specific, so parallel runs do not collide)",
    )
    parser.add_argument("--output-dir", help="Override output directory")
    parser.add_argument("--pine-wait-seconds", type=float, default=8.0, help="Seconds to wait for the Pine panel to load in probe mode.")
    parser.add_argument("--pine-script", help="Path to a generated TradingView Pine script for install-pine mode.")
    args = parser.parse_args()

    if args.mode == "probe-pine":
        session = args.session or "smc-elite"
        output_dir = Path(args.output_dir) if args.output_dir else JOURNAL_ROOT / datetime.now(timezone.utc).strftime("%Y-%m-%d") / "pine_probe"
        probe_pine_panel(session=session, output_dir=output_dir.resolve(), wait_seconds=args.pine_wait_seconds)
        return 0

    if args.mode == "install-pine":
        if not args.pine_script:
            parser.error("--pine-script is required in install-pine mode")
        session = args.session or "smc-elite"
        output_dir = Path(args.output_dir) if args.output_dir else JOURNAL_ROOT / datetime.now(timezone.utc).strftime("%Y-%m-%d") / "pine_install"
        install_pine_overlay(
            session=session,
            pine_script=Path(args.pine_script).resolve(),
            output_dir=output_dir.resolve(),
            wait_seconds=args.pine_wait_seconds,
        )
        return 0

    if not args.instrument:
        parser.error("--instrument is required in capture mode")

    tradingview_symbol, instrument, exchange = normalize_tradingview_symbol(args.instrument, args.exchange)
    session = args.session or f"smc-elite-{instrument.lower()}"

    ensure_webbridge(session=session)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir = Path(args.output_dir) if args.output_dir else JOURNAL_ROOT / today / instrument
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    urls: dict[str, str] = {}
    urls["1D"] = build_chart_url(tradingview_symbol, "1D")
    open_chart(tradingview_symbol, session, timeframe="1D")

    screenshots: dict[str, Path] = {}
    for tf in ["1D", "4H", "1H", "15"]:
        if tf != "1D":
            urls[tf] = change_timeframe(tf, tradingview_symbol, session)
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S")
        path = output_dir / f"{instrument}_{tf}_{timestamp}.png"
        capture_valid_screenshot(tf, path, session, retry_url=urls[tf])
        screenshots[tf] = path.resolve()

    print("\nCaptured screenshots:")
    for tf, path in screenshots.items():
        print(f"  {tf}: {path}")

    # Write a small metadata file so the analyst can find the screenshots later.
    meta_path = output_dir / "screenshots.json"
    meta_path.write_text(
        json.dumps(
            {
                "instrument": instrument,
                "exchange": exchange,
                "tradingview_symbol": tradingview_symbol,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "urls": urls,
                "screenshots": {tf: str(path) for tf, path in screenshots.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nMetadata saved: {meta_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
