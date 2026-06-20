#!/usr/bin/env bash
# Train one futures pair: pull 4yr 15m Binance USD-M perpetual candles, build
# the research datasets (open baseline + locked combo at 4bps and 10bps), then
# calibrate. Bitstamp spot remains available as explicit legacy mode.
#
# Usage:
#   bash tools/train_pair.sh BTCUSDT
#   bash tools/train_pair.sh SOLUSDT 2022-06-20 2026-06-20
#   PROVIDER=bitstamp bash tools/train_pair.sh solusd SOLUSD 2022-06-19 2026-06-19
set -euo pipefail
ROOT="/Users/tobimobolade/smc-codex-desk"
cd "$ROOT"
source .venv/bin/activate 2>/dev/null || true

PROVIDER="${PROVIDER:-binance_futures}"
DEFAULT_END="$(date -u +%Y-%m-%d)"
DEFAULT_START="$(python3 -c 'from datetime import date; today=date.today(); print(today.replace(year=today.year-4).isoformat())')"

if [[ "$PROVIDER" == "bitstamp" ]]; then
  MARKET="${1:?Usage: PROVIDER=bitstamp bash tools/train_pair.sh <market> <SYMBOL> [start] [end]}"
  SYM="${2:?Usage: PROVIDER=bitstamp bash tools/train_pair.sh <market> <SYMBOL> [start] [end]}"
  START="${3:-$DEFAULT_START}"
  END="${4:-$DEFAULT_END}"
  DATA="data/ohlcv/bitstamp/$SYM/${SYM}_15m_4year.csv"
  if [[ -s "$DATA" && "${FORCE:-0}" != "1" ]]; then
    echo "== [1/5] reuse existing Bitstamp spot data: $DATA =="
  else
    echo "== [1/5] pull 4yr 15m Bitstamp spot ($MARKET $START..$END) =="
    python3 tools/download_bitstamp_ohlcv.py --market "$MARKET" --step 900 --start "$START" --end "$END" --output "$DATA" \
      --sleep 0.05 --retries 12 --retry-delay 2
  fi
elif [[ "$PROVIDER" == "binance_futures" ]]; then
  SYM="${1:?Usage: bash tools/train_pair.sh <BINANCE_USDM_SYMBOL> [start] [end]}"
  SYM="$(python3 -c 'import sys; s=sys.argv[1].upper().replace("/", "").replace("-", ""); print((s[:-3] + "USDT") if s.endswith("USD") and not s.endswith("USDT") else s)' "$SYM")"
  START="${2:-$DEFAULT_START}"
  END="${3:-$DEFAULT_END}"
  DATA="data/ohlcv/binance_futures/$SYM/${SYM}_15m_4year.csv"
  if [[ -s "$DATA" && "${FORCE:-0}" != "1" ]]; then
    echo "== [1/5] reuse existing Binance USD-M futures data: $DATA =="
  else
    echo "== [1/5] pull 4yr 15m Binance USD-M futures ($SYM $START..$END) =="
    python3 tools/download_binance_futures_ohlcv.py --symbol "$SYM" --interval 15m --start "$START" --end "$END" --output "$DATA" \
      --sleep 0.03 --retries 8 --retry-delay 2 --allow-missing
  fi
else
  echo "Unknown PROVIDER=$PROVIDER (expected binance_futures or bitstamp)" >&2
  exit 2
fi

R="backtests/research"
OPEN_DATA="$R/${SYM}_4yr_open.csv"
COMBO_DATA="$R/${SYM}_4yr_combo.csv"
COST10_DATA="$R/${SYM}_4yr_combo_cost10.csv"
CAL_DIR="backtests/calibration/${SYM}_4yr"

echo "== [2/5] research: OPEN (baseline + width ladder + fresh/partial) =="
if [[ -s "$OPEN_DATA" && "${FORCE:-0}" != "1" ]]; then
  echo "reuse existing OPEN research: $OPEN_DATA"
else
  python3 tools/build_research_dataset.py --ohlcv "$DATA" --symbol "$SYM" --rules strategies/smc/rules_open.json \
    --output "$OPEN_DATA" --warmup-bars 400 --decision-step 120
fi

echo "== [3/5] research: LOCKED combo (width>=0.25% + fresh) @4bps =="
if [[ -s "$COMBO_DATA" && "${FORCE:-0}" != "1" ]]; then
  echo "reuse existing LOCKED combo research: $COMBO_DATA"
else
  python3 tools/build_research_dataset.py --ohlcv "$DATA" --symbol "$SYM" --rules strategies/smc/rules_widthfloor.json \
    --output "$COMBO_DATA" --warmup-bars 400 --decision-step 120
fi

echo "== [4/5] research: LOCKED combo @10bps (cost test) =="
if [[ -s "$COST10_DATA" && "${FORCE:-0}" != "1" ]]; then
  echo "reuse existing LOCKED combo cost10 research: $COST10_DATA"
else
  python3 tools/build_research_dataset.py --ohlcv "$DATA" --symbol "$SYM" --rules strategies/smc/rules_widthfloor.json \
    --cost-bps 10 --output "$COST10_DATA" --warmup-bars 400 --decision-step 120
fi

echo "== [5/5] calibrate (open dataset) =="
if [[ -s "$CAL_DIR/calibration.json" && "${FORCE:-0}" != "1" ]]; then
  echo "reuse existing calibration: $CAL_DIR"
else
  python3 tools/calibrate_from_research.py --research "$OPEN_DATA" --output-dir "$CAL_DIR"
fi

echo "DONE: $SYM trained. Datasets in $R/${SYM}_4yr_*.csv ; calibration in $CAL_DIR/"
