# Master Build Brief

Build a local Smart Money Concepts chart-analysis workstation in Codex called `smc-codex-desk`.

## Objective

Create a three-layer analyst system, not a trading bot.

## Layers

1. Chart intake layer
Accept TradingView screenshots now, with a clean upgrade path for browser capture and direct market-data feeds later.

2. SMC analysis layer
Detect and label market structure, dealing range, BOS, CHoCH, liquidity pools, equal highs/lows, FVGs, order blocks, session highs/lows, premium/discount, entry zones, invalidation levels, and target scenarios.

3. Output layer
Produce:
- a written trade thesis
- an annotated chart image
- a structured JSON trade plan for storage in a journal or dashboard

## Technical Requirements

- Use Python 3.11+
- Support both screenshot input and OHLCV input
- Use a modular architecture so browser access or broker or data-feed integrations can be added later
- Do not include trade execution or order placement
- Prefer deterministic chart rendering and overlays over generative image output

## Repo Structure

- `prompts/`
- `strategies/smc/`
- `tools/`
- `outputs/`
- `mcp/` for future browser or broker tooling

## Core Modules

- `analyze_chart.py`
- `detect_smc_zones.py`
- `annotate_chart.py`
- `build_trade_plan.py`
- `compare_my_bias_vs_model.py`
- `session_context.py`

## Output Artifacts

- `analysis.json`
- `annotated_chart.png`
- `bias_comparison.png`
- `trade_plan.md`

## Important Constraint

This system is for analysis only. Do not place trades, connect execution logic, or simulate autonomous trading.

If assumptions are needed, make reasonable defaults and document them clearly.
