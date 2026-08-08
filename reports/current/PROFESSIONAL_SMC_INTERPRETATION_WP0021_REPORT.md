# Professional SMC Interpretation Repair - WP-0021

Status: `PASS_ACCEPTED_CORE_SLICE`

WP-0021 adds the missing trader-story layer above raw SMC event detection. The
system now separates external bias from internal retracement, enforces timeframe
roles, creates POI watch states, and writes a trader-grade thesis V2.

Most important BTCUSDT correction:

```text
Old read:
1H bullish vs 4H bearish -> INVALIDATE_ALL -> blunt NO_SIGNAL

New read:
4H external bearish
1H external bearish
1H internal bullish retracement
15M confirmation-only
WATCH_BEARISH_RETRACE_TO_1H_SUPPLY
final_action = NO_SIGNAL
```

Replay evidence:

`analysis_runs/WP0021_BTCUSDT_INTERPRETATION_REPLAY_20260627/`

Validation:

- Focused WP-0021: `4 passed`
- Affected regression set: `16 passed`
- Full pytest: `510 passed, 1 skipped`
- Compileall: passed
- Governance consistency: PASS

No edge, paper execution, live execution, or capital risk authority was created.
