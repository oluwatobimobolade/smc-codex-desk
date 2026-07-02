# Regime-Aligned SMC Continuation V1

Short name: `RASC-SMC-V1`

Status: `RESEARCH_CANDIDATE`

Authority: `LIVE_SHADOW_ONLY`

Capital risk: `0%`

## Purpose

This is the only active strategy research candidate during its official
evaluation. It is not a validated trading system. It is a fully specified,
falsifiable candidate designed to answer one question:

Does an SMC confirmation sequence add incremental economic value beyond
objective trend and one-hour FVG location?

## Certified Initial Scope

- Venue: Binance USD-M
- Instrument: BTCUSDT perpetual
- Canonical timeframe: 15m
- Derived timeframes: 1H, 4H, 1D from canonical 15m
- Chart type: standard candles
- Price scale: linear
- Timezone: UTC
- Decision data: completed candles only

## Strategy Shape

Market Truth -> Objective regime and trend -> SMC structural context -> SMC
location -> SMC confirmation -> Execution and risk -> Outcome measurement.

SMC is not allowed to define direction by itself in V1. Direction starts from a
measurable 4H regime, with Daily acting as a veto.

## Authority Warning

This folder is a strategy contract, not proof of edge. Promotion requires
baselines, chronological validation, cost stress, holdout performance,
calibration, replication, and live-shadow evidence.
