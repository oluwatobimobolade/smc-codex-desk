# Validation Plan

## Stage 1 - Development

Use chronological BTCUSDT data to debug event counts, geometry, costs, and data
defects. No final evidence claims.

## Stage 2 - Calibration

Use calibration period only for probability calibration, action thresholds, and
abstention policy. No strategy-definition changes.

## Stage 3 - Final Holdout

Do not use final holdout for threshold selection, feature selection, entry
changes, stop changes, regime definitions, or debugging.

## Stage 4 - Cross-Market Replication

After BTCUSDT rules are frozen, apply unchanged rules to ETHUSDT and SOLUSDT.
Do not tune separately before first replication report.

## Required Reports

- event count report;
- baseline comparison report;
- cost sensitivity report;
- walk-forward report;
- holdout report;
- replication report;
- calibration report;
- failure report.
