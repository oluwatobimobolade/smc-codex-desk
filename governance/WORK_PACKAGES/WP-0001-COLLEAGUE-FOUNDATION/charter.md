# WP-0001 - Colleague Foundation

## Problem

The repository contains strong components, but authority is scattered across
legacy strategy documents, research reports, engine code, perception scaffolds,
case-lab tooling, and recent market-colleague workflow work. The new project
plan requires one coherent foundation before further feature expansion.

## Reason It Matters

Without a core memory, current-state file, authority matrix, dataset registry,
and active strategy candidate, future agents can confuse old hopeful strategy
claims with current evidence-based authority.

## Project Goal Supported

Build a disciplined market colleague that can validate market data, reconstruct
multi-timeframe charts, inspect TradingView, perceive SMC state, construct
falsifiable scenarios, preserve failures, and abstain when evidence is weak.

## Current Behaviour

`tools/run_market_colleague_case.py` is a useful vertical slice, but the repo
does not yet have governance files, a single active strategy candidate folder,
or a complete repository authority map.

## Desired Behaviour

Every contributor can read governance files and know:

- the current certified scope;
- what is active, research-only, legacy, or unproven;
- what must not be claimed;
- which strategy candidate is active;
- which datasets are contaminated, protected, or workflow-only;
- which next actions are approved.

## In Scope

- `governance/`
- `strategies/active/REGIME_ALIGNED_SMC_CONTINUATION_V1/`
- `reports/current/`
- contract tests for governance/strategy artifacts

## Out Of Scope

- Destructive repository cleanup
- Moving legacy strategy files
- Live execution
- Forex expansion
- Tuning strategy parameters
- Claiming predictive or economic edge

## Authority Limits

This work may establish labels, contracts, and research scope. It may not grant
predictive, paper execution, or live execution authority.

## Dependencies

- `/Users/tobimobolade/Downloads/SMC Codex Desk.pdf`
- `/Users/tobimobolade/Downloads/Master Strategy Truth Audit.pdf`
- current repository tests

## Acceptance Gates

- Governance core files exist.
- Current state and authority limits are machine-readable.
- Active strategy candidate folder exists and is marked research-only.
- Open risks preserve known gaps.
- Tests verify required files and authority claims.
- Baseline test evidence is recorded.

## Rollback Plan

Remove the new governance, active strategy, and report/test files from this work
package. No existing strategy or engine files are moved or deleted by WP-0001.
