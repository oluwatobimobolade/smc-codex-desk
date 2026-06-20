#!/usr/bin/env bash
# Run the full 15m SMC research/training loop for the default Binance futures universe.
#
# Override examples:
#   SYMBOLS="BTCUSDT ETHUSDT" bash tools/train_binance_futures_universe.sh
#   START=2023-01-01 END=2026-06-20 bash tools/train_binance_futures_universe.sh
set -euo pipefail

ROOT="/Users/tobimobolade/smc-codex-desk"
cd "$ROOT"

DEFAULT_END="$(date -u +%Y-%m-%d)"
DEFAULT_START="$(python3 -c 'from datetime import date; today=date.today(); print(today.replace(year=today.year-4).isoformat())')"
START="${START:-$DEFAULT_START}"
END="${END:-$DEFAULT_END}"
SYMBOLS="${SYMBOLS:-BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT}"

read -r -a SYMBOL_LIST <<< "$SYMBOLS"

for raw_symbol in "${SYMBOL_LIST[@]}"; do
  symbol="$(python3 -c 'import sys; s=sys.argv[1].upper().replace("/", "").replace("-", ""); print((s[:-3] + "USDT") if s.endswith("USD") and not s.endswith("USDT") else s)' "$raw_symbol")"
  echo "== Training $symbol =="
  PROVIDER=binance_futures bash tools/train_pair.sh "$symbol" "$START" "$END"
done

echo "DONE: Binance futures research outputs are under backtests/research/ and backtests/calibration/."
