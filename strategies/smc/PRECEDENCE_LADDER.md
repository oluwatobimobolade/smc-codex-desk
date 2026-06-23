# Precedence Ladder — Authored Tiebreakers for SMC Conflicts

This document defines the deterministic resolution order for every type of
conflict the SMC system can encounter. These rules are **authored**, not
extracted: the consensus method quarantined everything below 8/11 agreement,
so the academies give no tiebreakers to mine. These are the house edge.

## Purpose

When two valid signals disagree, the system must resolve the conflict
deterministically — not by averaging, not by confidence, but by a fixed
precedence that reflects how Smart Money Concepts actually works.

## The Ladder (highest to lowest)

### 1. No-leakage (absolute)

**Rule:** If any candle used in a decision closes after the decision time, the
decision is void. No exception, no override, no confidence threshold.

**Why:** A decision made with future information is not a decision — it is
cheating. Every downstream layer inherits this.

**Enforcement:** 40+ leakage tests in `test_mtf.py`, `test_fusion_leakage.py`,
`test_episode_narrative.py`.

---

### 2. Hard gates (binary vetoes)

**Rule:** The following conditions force `Pass` and cannot be overridden by any
confidence value, intent score, or fusion override:

- **R:R below floor** (default 3.0) — a trade that cannot pay 3:1 is not a trade.
- **POI fully mitigated** — a zone that has been consumed is no longer a POI.
- **News blackout** — no entries within the configured window around high-impact news.
- **Counter-Daily without exception** — if the Daily timeframe opposes the setup
  direction and no explicit exception (protected break) exists, the setup is void.

**Why:** These are disqualifiers, not deductions. A 0.99 confidence does not
rescue a 1.5 R:R setup.

**Enforcement:** `test_engine_hard_gates.py`, engine `if not has_rr: verdict = Pass`.

---

### 3. Source alignment (data integrity)

**Rule:** The data source must match the intended market. If the engine is
analysing Binance USD-M futures, the OHLCV must come from Binance USD-M
futures, not Bitstamp spot.

**Why:** Cross-source analysis produces phantom levels that do not exist on
the actual exchange.

**Enforcement:** `case_library.py` SHA256 provenance, `dual_lens.py` source-mismatch
penalty.

---

### 4. HTF bias hierarchy (Daily > 4H > 1H)

**Rule:** Higher timeframe bias takes precedence over lower timeframe bias.

- Daily opposition blocks 1H + 4H agreement (no execution against the Daily).
- Daily neutrality allows 1H + 4H agreement to stand.
- 1H alone cannot drive execution bias (needs 4H corroboration).

**Why:** The Daily timeframe is the institutional timeframe. A 15m CHoCH does
not flip the Daily. Internal structure is entry confirmation, not bias.

**Enforcement:** `test_mtf.py::HtfConsensusBiasTests`.

---

### 5. Structure scope (external > swing > internal)

**Rule:** When two structure events conflict:

- External (dealing range) breaks override swing breaks.
- Swing breaks override internal breaks.
- Internal CHoCH is entry confirmation only — it cannot flip HTF bias.

**Why:** The larger the structure, the more significant the event. A break of
the dealing range is a regime change; a break of an internal swing is noise.

**Enforcement:** `test_engine.py::test_bullish_choch_requires_protected_high_not_internal_high`.

---

### 6. POI quality (fresh > partial > approaching)

**Rule:** When two POIs compete for selection:

1. A fresh POI (unmitigated) beats a partially mitigated one.
2. A partial POI beats an approaching HTF POI (which is only a watchlist item).
3. A mapped HTF POI cannot override a `Pass` — it can only surface `Watch HTF POI`.

**Why:** A zone that has not been consumed is where price is most likely to
react. A mitigated zone is a spent level.

**Enforcement:** `test_engine.py::test_trade_plan_default_rejects_partial_poi`,
`test_mtf.py::HtfPoiWatchTests`.

---

### 7. Draw alignment (with-draw > against-draw)

**Rule:** A setup that aligns with the current draw (the direction price is
pulling liquidity) takes precedence over one that fights it.

- If price is drawing buy-side liquidity (rallying toward equal highs), a
  bullish setup that targets those highs is preferred over a bearish
  counter-trend setup.
- A bearish setup into a buy-side draw must clear a higher bar (stronger
  sweep, stronger displacement, better R:R).

**Why:** Smart money pulls liquidity before reversing. Trading with the draw
is trading with the institutional flow.

**Enforcement:** Engine POI selection weights `premium_discount_aligned` and
`liquidity_target` proximity.

---

### 8. Regime (trend_aligned > transitional > chop > trend_counter)

**Rule:** The regime label modulates confidence:

- `trend_aligned`: no penalty.
- `transitional`: no penalty (await clarity).
- `chop`: 0.7x confidence multiplier (trend-following setups are penalized).
- `trend_counter`: 0.8x confidence multiplier (setup fights HTF bias).

**Why:** The SMC edge is conditional. In chop, structure breaks are noise. In
trend-counter, the setup is fighting institutional flow.

**Enforcement:** `fusion_engine.py` regime penalty, `features.py::regime_features`.

---

### 9. Intent modulation (calibrated, log-only until calibrated)

**Rule:** Intent rules may only modulate confidence — they may never assert a
standalone direction. Until calibrated against a gold set (Brier ≤ 0.25),
intent runs in log-only mode and contributes nothing to the verdict.

**Why:** Intent is the most speculative layer. It is a story about *why* price
moved. Handing the most speculative layer veto power over the deterministic
engine is the narrative fallacy.

**Enforcement:** `fusion_engine.py::FusionEngineConfig.allow_intent_modulation = False`.

---

### 10. Dual-direction margin (contested → Watch)

**Rule:** When both bullish and bearish plans are candidates and neither wins
by a clear margin (default 15% of total score), the result is `contested` and
the verdict is `Watch`.

**Why:** If the system cannot distinguish between two competing hypotheses, it
should abstain. Confidence without clarity is dangerous.

**Enforcement:** `fusion_engine.py::FusionEngineConfig.contested_margin = 0.15`.

---

## Conflict Resolution Examples

| Conflict | Resolution | Ladder rung |
|----------|-----------|-------------|
| 15m CHoCH bullish vs Daily bearish | Daily wins; no execution | 4 |
| R:R 2.5 but every other signal perfect | Pass (hard gate) | 2 |
| Fresh bullish FVG vs partial bullish OB | Fresh FVG wins | 6 |
| Bullish setup into buy-side draw | Bullish setup preferred | 7 |
| Engine says Execute but intent says bull_trap | Engine wins (intent log-only) | 9 |
| Both directions score 0.45 vs 0.45 | Contested → Watch | 10 |
| Sweep + displacement on same bar | Both preserved (not either/or) | 5 |

## What This Document Is Not

- It is not a trading strategy. It is a conflict resolution protocol.
- It is not exhaustive. New conflict types will emerge; they must be added
  here with an explicit rule and a test.
- It is not negotiable at runtime. The ladder is fixed. If a rule is wrong,
  change the document and the test — do not add a runtime override.

## Maintenance

When a new conflict type is identified:

1. Add it to this document with a rule, a reason, and an enforcement test.
2. Add a regression test that fails if the rule is violated.
3. Update `FUSION_ARCHITECTURE.md` if the conflict affects the fusion layer.
