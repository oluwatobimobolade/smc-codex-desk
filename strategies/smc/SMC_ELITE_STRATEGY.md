# SMC Elite Strategy

**Version:** 2.0 (The MTF Cascade Update)
**Purpose:** A high-confluence, intraday Smart Money Concepts system built from the consensus overlap of academy material, open SMC tools, and our own backtests.
**Timeframes:** Daily / 4H / 1H for context; 15m & 5m for execution.
**Risk:** 1% default; 2% only on A+ setups.
**Minimum R:R:** 1:3.
**Entry style:** System decides — 15M standard aggressive entry, 5M confirmation entry, or no trade.

---

## Philosophy

This strategy is built from:
- **HCNFXACADEMY** (Happiness Hanson): confluence-based SMC, valid order blocks, aggressive vs confirmation entries, inducement.
- **The Trading Savant**: full market structure course.
- **KiraForex**: simple FVG/imbalance approach.
- **Verified Reddit trader experiences** from r/Forex, r/Daytrading, r/RealDayTrading.

The core idea is not to predict the market. It is to **wait for the market to show its hand**, building a sequential filter where a trade must survive a rigorous Top-Down Multi-Timeframe gauntlet before execution is authorized.

This system does **not** promise good trades or guaranteed profitability. Its job is to filter aggressively, define invalidation clearly, and keep the journal honest enough that the edge can be measured over a real sample.

> "Pick one setup, backtest it, deploy it, and focus on 1 setup, 1 pair, 1 session. Only trade the A+++ setup. If it doesn't form all week, that is still part of the setup." — r/Forex

---

## Consensus Rule

Only repeated ideas become core rules. The current consensus research is in `CONSENSUS_SMC_RESEARCH.md`.

**Core rules now:** MTF context, protected swing structure, internal execution structure, liquidity sweeps, displacement, FVG/OB POIs, fresh-zone preference, structural stops, executable stop buffers, and liquidity targets.

**Research modules:** exact killzones, mandatory 5m confirmation, mandatory OB+FVG overlap, breaker blocks, news filters, and strict macro premium/discount gates. These may be useful, but they must earn their place through tests and reviewed cases.

---

## The 3 Pillars

Every trade must answer three questions:

1. **Bias** — What is the higher-timeframe macro narrative and dealing range?
2. **Point of Interest (POI)** — Where will I look for an entry, and has the market swept inducement first?
3. **Confirmation** — What micro timeframe behavior must happen before I enter?

If any pillar is missing or weak, there is no trade.

---

## Phase 1: Bias & Macro-Narrative — Daily & 4H

You cannot trade the micro without understanding the macro. The daily and 4-hour charts exist purely to dictate your bias.

### The Macro Bias (Daily / 1D)
* The Daily timeframe defines macro context and major dealing range.
* If Daily actively opposes the 1H/4H idea, the setup is blocked or downgraded.
* If Daily is neutral, 1H and 4H agreement can still produce a research-grade execution bias.

### External Structure Bias (4H)
* The 4H timeframe determines the **External Structure** (major swing highs and lows).
* The 4H bias must align with the 1H execution narrative.
* **Current engine rule:** 1H and 4H must agree; Daily must agree or be neutral before HTF bias is fed into execution.
* **Research filter:** macro premium/discount should be used to reduce confidence until full Daily dealing-range enforcement is built.

### Structure: Strong vs. Weak
Structure is a map of institutional protection.
- **Strong Low:** A low that successfully breaks a previous high (causing a new Higher High). Institutions have committed capital here and will actively defend it.
- **Weak High:** A high that fails to break a previous low. This high is unprotected and serves as a liquidity target.

---

## Phase 2: Point of Interest & Liquidity — 1H

A valid POI must be:
1. Aligned with HTF bias.
2. Fresh or only partially mitigated.
3. In premium (for sells) or discount (for buys).
4. Near a logical liquidity sweep point.

### The Liquidity Law
Price moves to rebalance an imbalance or seek liquidity. The system explicitly tracks two forms of liquidity:
* **External Range Liquidity (ERL):** The resting stop-losses above/below major 4H/Daily swing points. This acts as the ultimate take profit.
* **Internal Range Liquidity (IRL):** The minor swing highs/lows inside the current dealing range. 

> *The market will almost always sweep Internal Range Liquidity (IRL) before expanding to attack External Range Liquidity (ERL).*

### Validating the 1H POI

Not all Order Blocks are valid. To prevent premature entries, the strategy ranks 1H POIs by structure, freshness, displacement, liquidity, and premium/discount context.

1. **The 3-Candle Imbalance Rule:** An Order Block with an immediate FVG is higher quality. This is an A/A+ filter, not yet a universal engine hard gate.
2. **The Inducement Rule:** A POI is weaker unless nearby IRL/inducement has been swept before confirmation.
3. **The Freshness Rule:** Fresh POIs are default. Partial POIs are research opt-in. Fully mitigated POIs are invalid.

---

## Phase 3: Execution Matrix — 15m & 5m

Once the 1H POI is tapped and the inducement is swept, the terminal calculates precise execution parameters.

### Required Conditions (ALL must be present)
1. **IRL Sweep:** Price sweeps a nearby internal liquidity pool (Inducement) before or during the POI tap.
2. **Displacement:** A strong candle body moves in the intended direction after the sweep.
3. **Price at or entering the 1H POI.**

### Execution Models

#### Model 1: The 15M Standard Entry
* **Trigger:** Price taps the 1H POI and the 15M timeframe prints a valid Order Block with displacement.
* **Execution:** Limit order placed at the 15M OB.
* **Invalidation (SL):** Stop loss is securely placed behind the overarching 1H structural wick.

#### Model 2: The 5M Confirmation Entry
* **Trigger:** Price taps the 1H/15M POI and prints an internal Change of Character (CHoCH) on the 5M timeframe.
* **Execution:** Limit order placed at the fresh 5M OB.
* **Invalidation (SL):** The 5M OB can refine the entry, but the executable SL must still pass structural and ATR-buffer checks. Do not use a tight 5M stop if normal volatility can invalidate it.

---

## Phase 4: Stop Loss & Take Profit

### Stop Loss
Place SL at the point that proves the setup wrong:
- **For 15M Standard:** Behind the 1H POI / major sweep low.
- **For 5M Confirmation:** Tightly behind the 5M structural CHoCH extreme.
Never move SL to break even too early. Let price breathe.

### Take Profit
Target the next logical liquidity pool in the trade direction:
- **TP1 (Internal):** Prior session high/low, equal highs/lows (lock in partial profit).
- **TP2 (External):** Major swing ERL from 4H / Daily.

### Risk/Reward
- Minimum acceptable: **1:3**.
- If the setup cannot deliver 1:3 with logical SL and TP, **no trade**.

---

## Phase 5: Setup Grading

| Grade | Criteria | Risk Allowed |
|---|---|---|
| **A+** | 1D/4H aligned + IRL swept + 3-candle FVG POI + 5m CHoCH inside + 1:3+ R:R + inside Killzone + no news | 2% |
| **A** | All confluences present but slightly less clean (e.g. 15m entry instead of 5m, or marginal R:R) | 1% |
| **B** | Missing one minor confluence or ambiguous 15m structure | No trade |
| **C** | Against bias, mitigated POI, no IRL sweep, or poor R:R | No trade |

Only A+ and A setups are taken.

### Engine Quality Gate
The deterministic engine grades setups with the current hard checklist. If any core execution item is missing, output is **Watch**, **Watch Retrace**, or **Pass** with **0% risk**:

- HTF consensus bias exists: 1H and 4H agree; Daily agrees or is neutral.
- POI is fresh by default.
- POI sits in the correct side of the current dealing range.
- Liquidity sweep appears in the intended direction.
- BOS/CHoCH includes candle-body displacement.
- Sweep occurs before the confirming break.
- Price is at or near the POI.
- Execution SL has structural/ATR buffer.
- Projected R:R is at least 1:3.

Pending research gates: strict OB+FVG overlap, exact 5m model, killzones, news filters, breaker blocks, and full Daily macro premium/discount enforcement.

---

## Phase 6: Algorithmic Killzones & Fundamental Filter

Time is just as crucial as price. Execute only during specific, highly-liquid windows.

### Algorithmic Killzones (EST)
* **London Killzone:** 2:00 AM - 5:00 AM EST
* **New York Killzone:** 7:00 AM - 10:00 AM EST
These windows are a research filter, not a current hard gate. They should be tracked and tested before becoming mandatory.

### Fundamental Rules
Before entering, check:
1. **Economic calendar** for the pair/asset.
2. **High-impact news** in the next 4 hours.
* **Research rule:** No new entries 30 minutes before and 1 hour after high-impact news. This needs a live calendar integration before the engine can enforce it.

---

## Step 7: Psychology & Discipline

From verified trader experiences:
- **Fixed risk per trade.** Do not vary lot size based on confidence.
- **Less is more.** 1–3 high-quality trades per week is enough.
- **Every day is independent.** Do not revenge trade after a loss.
- **Losing streaks happen.** A 60%+ win rate can still produce 5 losses in a row.
- **Stay boring.** If it feels exciting, you are probably drifting from the system.
- **Journal every trade.** Edge is proven over 30–50 trades, not 5.

---

## Quick Reference Checklist

Before every trade, answer:
- [ ] What is the 1D / 4H bias and Dealing Range?
- [ ] Is the 4H external bias aligned with the 1D trend?
- [ ] Is price in a Discount (for buys) or Premium (for sells)?
- [ ] What is the 1H internal structure and POI?
- [ ] Does the 1H POI have a clean 3-candle FVG imbalance?
- [ ] Was Internal Range Liquidity (IRL) swept just before the 1H POI?
- [ ] Are we inside the London or NY Killzone?
- [ ] Did the 15m print a BOS or did the 5m print a CHoCH inside the POI?
- [ ] Where is SL? Where is TP (ERL)? Is R:R at least 1:3?
- [ ] Are there any high-impact news events?
- [ ] What is the setup grade (A+ / A / B / C)?

If all A/A+ boxes are checked, execute. Otherwise, wait.

---

## What This Strategy Is NOT
- It is not a prediction machine.
- It does not trade every day.
- It does not chase price.
- It does not guarantee profit.
- It is not "set and forget" — manage the trade.

---

## Sources
- HCNFXACADEMY YouTube channel (Happiness Hanson)
- The Trading Savant — FULL Smart Money Concepts Trading Course
- KiraForex — Simple Forex Strategy / Imbalances & FVGs
- Liquidity Inducement Masterclass
- Photon Trading — Structure Mapping
- r/Forex, r/Daytrading, r/RealDayTrading verified trader experiences

---
*This strategy is a living document. Update it only after reviewing journal data — never based on a single trade outcome.*
