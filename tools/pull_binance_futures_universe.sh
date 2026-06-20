#!/usr/bin/env bash
# Pull Binance USD-M perpetual OHLCV for the core crypto futures universe.
#
# Defaults:
#   symbols:   BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT
#   intervals: 15m 1h 4h 1d
#   range:     last 4 UTC years, end date exclusive
#
# Override examples:
#   START=2023-01-01 END=2026-06-20 bash tools/pull_binance_futures_universe.sh
#   SYMBOLS="BTCUSDT SOLUSDT" INTERVALS="15m 1h" bash tools/pull_binance_futures_universe.sh
set -euo pipefail

ROOT="/Users/tobimobolade/smc-codex-desk"
cd "$ROOT"
source .venv/bin/activate 2>/dev/null || true

DEFAULT_END="$(date -u +%Y-%m-%d)"
DEFAULT_START="$(python3 -c 'from datetime import date; today=date.today(); print(today.replace(year=today.year-4).isoformat())')"
START="${START:-$DEFAULT_START}"
END="${END:-$DEFAULT_END}"
SYMBOLS="${SYMBOLS:-BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT}"
INTERVALS="${INTERVALS:-15m 1h 4h 1d}"
REPAIR_DAILY="${REPAIR_DAILY:-1}"
DERIVE_HTF="${DERIVE_HTF:-1}"
QUALITY_SUMMARY="${QUALITY_SUMMARY:-1}"
KNOWN_REPAIR_DATES="${KNOWN_REPAIR_DATES:-2023-11-10 2024-10-28 2025-01-29}"

read -r -a SYMBOL_LIST <<< "$SYMBOLS"
read -r -a INTERVAL_LIST <<< "$INTERVALS"

for raw_symbol in "${SYMBOL_LIST[@]}"; do
  symbol="$(python3 -c 'import sys; s=sys.argv[1].upper().replace("/", "").replace("-", ""); print((s[:-3] + "USDT") if s.endswith("USD") and not s.endswith("USDT") else s)' "$raw_symbol")"
  for interval in "${INTERVAL_LIST[@]}"; do
    output="data/ohlcv/binance_futures/$symbol/${symbol}_${interval}_4year.csv"
    if [[ -s "$output" && "${FORCE:-0}" != "1" ]]; then
      echo "== Skipping $symbol $interval; exists at $output =="
      continue
    fi
    echo "== Pulling $symbol $interval Binance USD-M futures ($START..$END) =="
    python3 tools/download_binance_futures_ohlcv.py \
      --symbol "$symbol" \
      --interval "$interval" \
      --start "$START" \
      --end "$END" \
      --output "$output" \
      --sleep 0.03 \
      --retries 8 \
      --retry-delay 2 \
      --allow-missing
  done
done

if [[ " $INTERVALS " == *" 15m "* && "$REPAIR_DAILY" == "1" ]]; then
  echo "== Repairing known Binance 15m archive anomalies from daily files =="
  python3 tools/repair_binance_futures_15m_from_daily.py \
    --symbols "${SYMBOL_LIST[@]}" \
    --dates $KNOWN_REPAIR_DATES \
    --output-report data/ohlcv/binance_futures/DAILY_REPAIR_REPORT.json
fi

if [[ " $INTERVALS " == *" 15m "* && "$DERIVE_HTF" == "1" ]]; then
  echo "== Deriving 1h/4h/1d from canonical repaired 15m files =="
  python3 tools/derive_htf_from_15m.py --symbols "${SYMBOL_LIST[@]}"
fi

if [[ "$QUALITY_SUMMARY" == "1" ]]; then
  echo "== Writing OHLCV quality summary =="
  python3 tools/summarize_ohlcv_quality.py \
    --symbols "${SYMBOL_LIST[@]}" \
    --json-output data/ohlcv/binance_futures/DATA_QUALITY_SUMMARY.json
fi

echo "DONE: Binance futures universe data written under data/ohlcv/binance_futures/"
