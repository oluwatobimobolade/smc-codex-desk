# SMC Mastery System — Master Research Plan (Charter v1)

**Mission.** Build a fully systematic, emotion-free SMC trading engine that targets
**~3:1 reward-to-risk at a 65–70% win rate, reproducible across markets and asset
classes**, deployable on any instrument with sufficient data.

**Stance (drug-discovery discipline).** We do not fake the assay and we do not quit.
We engineer relentlessly toward the target *and* respect the physics of markets.
The number 65–70%@3:1 is the **north star**; the **deployable bar** is whatever
survives the validation gauntlet below. We push until we find the true ceiling, and
we report it honestly the whole way. A perfect *truth-machine* that finds the real
ceiling is the deliverable — not a fabricated edge.

---

## 1. First principles — what we are actually hunting

- **Gambler's ruin.** A driftless path hits +3R before −1R only ~**25%** of the time.
  67%@3:1 demands a **~2.7× forward-drift multiplier**: our entries must sit right
  before strong, directional, low-noise moves. The system is therefore a **rarity
  detector** — most of its job is *discarding* setups.
- **The iron triangle.** Win-rate × R:R × Frequency — pick two. We pick win-rate and
  R:R, so **frequency is sacrificed** (few, elite trades). Consequence: a rare edge is
  unprovable on one market, so **breadth is the measurement instrument**, not a luxury.
- **Where edge must come from.** Large players source liquidity at *meaningful* stop
  clusters (prior D/W highs-lows, multi-touch equal levels, round numbers, session
  extremes), then reverse. If a durable SMC edge exists, it lives in the **quality of
  the swept liquidity** + the **regime** + **execution precision** — not a secret rule.
- **Our true edge vs the retail SMC crowd** is *not* a different rulebook. It is
  flawless selection, identical sizing, 24/7 breadth, regime timing, and exact
  measurement — the parts humans can't do. We never claim a magic rule.
- **The objective is consistent compounding**, not a win-rate fetish:
  maximize `expectancy × frequency × stability × survival`. 55%@3:1 across 20
  regime-gated markets with a circuit breaker can out-earn a fragile 67% on one.

---

## 2. The team (workstreams & mandates)

| Role | Owns | Core question |
|---|---|---|
| **Principal Investigator** | the bar, the phase gates, kill/pivot calls | "Does this clear the gauntlet, yes/no?" |
| **Quant / Statistician** | edge math, the frontier, sample-size, multiple-testing control | "Is this signal or noise?" |
| **Microstructure / Execution** | fills, maker/taker fees, funding, stop slippage, venue | "Would this trade actually fill at this price?" |
| **SMC Domain Expert** | setup definitions, liquidity significance, entry triggers, regime semantics | "Is this a real institutional footprint?" |
| **ML Engineer** | selection/scoring model, probability calibration, leakage control | "Does the model rank setups better than the rules, out of sample?" |
| **Risk Manager** | sizing, drawdown limits, circuit breakers, survival | "Can this blow up? When do we stop?" |
| **Validation / Epistemology (Skeptic)** | walk-forward, out-of-distribution tests, the locked holdout, red-team | "How are we fooling ourselves?" |
| **Systems / Infra** | data pipeline, engine speed, reproducible harness, live monitoring | "Is it fast, deterministic, and observable?" |

---

## 3. The reframed strategy hypothesis (what we now believe)

1. **Exits target real liquidity, not a fixed 3R.** Target the next liquidity pool the
   engine computes; **3:1 becomes an entry *filter*** (only take setups whose natural
   liquidity target is ≥3:1 away). More SMC-authentic; should raise the hit rate.
2. **The edge is regime-conditional.** It exists in trend/expansion, dies in chop. A
   **regime gate** is the primary lever for out-of-sample *stability*.
3. **Liquidity significance is under-weighted.** Rank setups by the importance of the
   swept level (HTF level, touch count, round number, age, session).
4. **Entry precision matters.** Require the post-sweep **internal CHoCH/displacement
   confirmation**, not merely "price at POI."
5. **Reproducibility comes from normalization.** One parameter set, all distances in
   ATR/percentile/session-relative terms, so the identical rule reads BTC and gold alike.

---

## 4. Phased program (each phase has a hard GO/NO-GO gate)

### Phase 0 — Foundation ✅ DONE
Deterministic no-look-ahead engine; dual-lens (engine+vision); Binance-futures data
(5 pairs, repaired); vectorized engine (~25× faster, golden-identical); leakage-safe
research harness with **exact-cost logging**; honest ML pipeline + walk-forward; the
anti-self-deception docs. We can iterate fast and we can't fool ourselves easily.

### Phase 1 — Reframe the edge (no new data needed)
- **E1. Liquidity-targeted exits + 3:1 filter** (replace fixed 3R).
- **E2. Regime-conditional test:** build a regime classifier (ADX, ATR-percentile,
  HTF-structure); run **within-regime walk-forward**.
- **E3. Realistic fills:** maker fee at the POI limit + funding + **explicit stop
  slippage**; re-evaluate the existing selection.
- **GATE 1 (go/no-go):** within a favorable regime, the liquidity-targeted setup shows
  **net-positive after realistic costs on ≥3 pairs** and **≥3/5 walk-forward folds
  positive.** If E2 shows the "good regime" itself drifts unpredictably → escalate to
  PI for a pivot (edge may be regime-*fragile*).

### Phase 2 — Find / sharpen the edge (within the gated regime)
- **E4. Liquidity-significance feature** (HTF level / touch-count / round-number / age).
- **E5. Entry-trigger precision** (sweep → displacement → internal CHoCH).
- **E6. Selection model** (calibrated probability; take only P ≥ target) on the gated,
  liquidity-targeted, realistic-cost data. Linear first (honest); trees only if linear
  clears the bar, under identical validation.
- **GATE 2:** net after-cost **expectancy ≥ +0.5R/trade (or net PF ≥ 1.3)**, **WF ≥ 4/6**,
  on crypto. Win-rate@achieved-R reported vs the 65–70% north star.

### Phase 3 — Prove reproducibility (the real test)
- **E7. Out-of-distribution:** wire **FX majors + gold + an index**; run the *frozen*
  Phase-2 rule/model with **one parameter set, zero per-market tuning.**
- **E8. The locked single-touch holdout:** the most-recent 6 months across all markets
  + entire untouched instruments — opened **exactly once.**
- **GATE 3:** clears the bar on **≥4 markets including ≥1 non-crypto asset class**, on
  data it was never tuned on. This is the near-proof of a behavioral invariant.

### Phase 4 — Forward validation
- **E9. Paper trade live** through the dual-lens + WebBridge, logging every trade.
- **E10. Circuit breaker + live-vs-backtest tracking error.**
- **GATE 4:** live win-rate and expectancy within tolerance of backtest over ≥3 months.

### Phase 5 — Capital deployment
Tiny size → scale on confirmation. Strict per-trade risk (≤1%), portfolio heat caps,
hard kill-switch. Never scale faster than the evidence.

---

## 5. The validation gauntlet (the promotion bar — non-negotiable)
A candidate is "real" only if **all** hold simultaneously:
1. **Net-positive after realistic costs** (maker fee + funding + stop slippage), not 4bps fantasy.
2. **Walk-forward ≥ 4/6 expanding windows positive** (stability, not one lucky window).
3. **Reproducible:** positive on **≥4 markets incl. ≥1 non-crypto**, **one parameter set**.
4. **Sample:** ≥100 trades in validation; report confidence intervals.
5. **Survives the locked single-touch holdout** (opened once).
No shortcuts, no goalpost-moving to a win-rate number. The gauntlet *is* the assay.

---

## 6. Experiment backlog (hypothesis → method → success → what it falsifies)

- **E1 Liquidity-targeted exit.** *H:* targeting real liquidity (not 3R) raises win-rate at
  ≥3:1. *M:* exit at engine's next liquidity pool; filter for ≥3:1; re-run. *Win:* higher
  net win-rate vs fixed-3R baseline. *Falsifies:* "3R is fine."
- **E2 Regime fork.** *H:* edge is trend-conditional. *M:* gate to regime; within-regime WF.
  *Win:* WF flips positive in-regime. *Falsifies:* "no fixed rule works" (→ fragile).
- **E3 Realistic fills.** *H:* edge survives true costs. *M:* maker+funding+stop-slippage.
  *Win:* net expectancy > 0. *Falsifies:* "the edge is a cost artifact."
- **E4 Liquidity significance.** *H:* sweeping *major* liquidity predicts reversal. *M:* rank
  swept-level importance; condition on it. *Win:* monotone expectancy by significance.
- **E5 Entry trigger.** *H:* requiring post-sweep CHoCH raises win-rate. *M:* add confirmation
  gate. *Win:* higher win-rate, acceptable frequency loss.
- **E6 Calibrated selection model.** *H:* a calibrated scorer beats the rules OOS. *M:* Platt/
  isotonic + threshold-on-train. *Win:* selected after-cost beats baseline, WF≥4/6.
- **E7 OOD reproducibility.** *H:* the edge is a behavioral invariant. *M:* frozen rule on
  FX/gold/index. *Win:* clears bar on non-crypto. *Falsifies:* "it was crypto-regime overfit."

---

## 7. KPIs & the frontier dashboard
Track every run: **net expectancy/trade (R)**, **net PF**, **win-rate @ achieved R:R**,
**WF fold consistency (x/6)**, **per-market spread**, **max drawdown (R)**, **trade
frequency**, **live-vs-backtest tracking error**. Plot the **win-rate ↔ R:R frontier**
for selected setups; the distance from our curve to the **(3.0, 0.67)** target is the
single honest progress metric. "Pushing till we get there" = that gap shrinking,
measurably, run over run.

---

## 8. Risk, survival & consistency engineering
- Fixed fractional risk ≤1%/trade; portfolio heat cap; correlation-aware (don't take 5
  correlated crypto longs as "5 trades").
- **Circuit breaker:** halt if rolling live win-rate/expectancy drops below floor.
- **Kill criteria:** if a deployed edge decays past tolerance, stand down and re-research.
- Edge decays; the *system noticing* is what makes it consistent.

---

## 9. Reproducibility protocol
Normalized features only (ATR / percentile / session-relative); **one parameter set
across all markets**; deterministic pipeline (seeded, golden-tested); every result
reproducible from a single command; data provenance + hashes logged.

## 10. Decision rules
- **Scale** only after a phase gate passes.
- **Pivot** if E2 shows regime-fragility (move to online/adaptive, or narrow scope).
- **Kill** any candidate that fails the gauntlet — even a beautiful backtest.
- **Honest ceiling:** if the durable, multi-market, after-cost number tops out below
  65–70%@3:1, we deploy the best *real* version (e.g., 55–60%@3:1) — still elite — and
  say so plainly. We never ship the north star as if it were the result.

## 11. What we have vs what we still need
- **Have:** fast deterministic engine, dual-lens, 5-pair crypto data, exact-cost harness,
  honest ML + walk-forward, anti-overfit discipline.
- **Need:** (a) **regime classifier module**; (b) **liquidity-targeted exit + 3:1 filter**;
  (c) **realistic fill/fee/funding/slippage model**; (d) **liquidity-significance feature**;
  (e) **non-crypto data feed (FX/gold/index)** — the one hard external dependency.

## 12. Anti-self-deception charter (signed by the whole team)
Locked single-touch holdout. One parameter set. No per-market tuning. No goalpost-moving.
Realistic costs always. Walk-forward + OOD before belief. The Skeptic can veto any
promotion. Optimistic docs get quarantined. The truth-machine outranks the hopeful self.
