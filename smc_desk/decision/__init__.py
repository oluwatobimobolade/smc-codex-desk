"""SMC Decision — generic strategy-state engine and decision policy.

This package provides the trader decision machinery. It is strategy-neutral
and produces conservative output (ABSTAIN/OBSERVE/WATCH). No PAPER_EXECUTE
until a certified strategy runtime exists.

Modules:
- contracts.py: State, Decision, StrategyStateResult, ScenarioResult,
  DecisionEnvelope typed contracts.
- state_engine.py: Generic state-transition engine consuming event types
  and conditions. Strategy rules are external contracts.
- scenario_builder.py: Scenario evidence graph and decision policy.
"""
