# State-Machine Observability Protocol

**Status:** Research instrumentation only. This is not an entry-rule change,
backtest promotion, or live-trading authorization.

## Purpose

Measure whether a deterministic sequence of aligned HTF bias -> liquidity
sweep -> displacement -> frozen POI revisit -> confirmation produces enough
valid, reproducible attempts to justify a separately pre-registered entry
experiment.

## Locked Phase-1 Semantics

1. A setup begins only on a closed 15m candle with aligned HTF direction and a
   same-direction deterministic liquidity sweep.
2. The displacement must occur within three closed bars after that sweep.
3. An FVG or order-block POI must be selected on the displacement candle. It
   cannot be replaced later by a more attractive retrospective zone.
4. Retrace deadline: 48 closed bars after displacement.
5. Confirmation deadline: 24 closed bars after the first POI touch.
6. A broken sweep extreme or fully mitigated POI records `INVALIDATED`; timeout
   records `EXPIRED`. The terminal event is logged before the system returns
   to `WATCHING`.
7. The phase emits no `TradePlan` and places no capital or paper order.

## Explicit Non-Claims

- Displacement remains part of the frozen baseline. It is not removed here.
- Aggregate OHLCV bar volume is not labelled institutional absorption or wick
  volume. That requires a separately defined proxy or actual trade-level data.
- Session, retrace-speed, volatility, pin-bar, engulfing, and FVG-confirmation
  filters are not active in this phase.
- Human annotations can become evidence cases; they cannot override an engine
  entry or manufacture a trade.

## Promotion Gate

Only after replay has shown deterministic, no-lookahead state transitions and
after momentum signatures have exact definitions can a separate entry branch
be pre-registered. That later protocol must use Binance USD-M `BTCUSDT` and
`ETHUSDT`, a training/selection period distinct from the held-out final year,
10 bps costs, per-pair reporting, a minimum outcome count, and the existing
chronological walk-forward gates.
