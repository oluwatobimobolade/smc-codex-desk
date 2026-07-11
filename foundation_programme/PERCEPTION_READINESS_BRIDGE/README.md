# Perception Readiness Bridge

Supported research runtime: **CPython 3.14.5**.

Clean local installation:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-perception.lock
.venv/bin/python -m pip install -e . --no-deps
```

Deterministic baseline experiment:

```bash
.venv/bin/python tools/run_perception_experiment.py baseline \
  --symbol BTCUSDT \
  --source data/ohlcv/binance_futures/BTCUSDT/BTCUSDT_15m_4year.csv \
  --decision-time 2026-06-20T00:00:00Z \
  --out analysis_runs/PERCEPTION_BRIDGE_BASELINE
```

The baseline command is observe-only. It writes certified market truth,
source/environment/input manifests, deterministic PerceptionEngineV2 output,
an AI role trace, an empty pre-annotation plan, and validation hashes. It does
not call an AI provider, judge SMC accuracy, render a trade, or authorize a
signal.

AI role execution, professional annotation evaluation, blind benchmark
opening, and human adjudication are BR-004 through BR-006 work. Their gates
remain closed until their independent controls and cases exist.
