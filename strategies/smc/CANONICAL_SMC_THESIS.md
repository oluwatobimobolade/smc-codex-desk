# The Canonical SMC Thesis (v1) — One System for Reading the Market

**Purpose.** A single, internally consistent, machine-checkable definition of every
SMC primitive, so the deterministic engine, a numeric-LLM expert, and a vision expert
all label the *same* objects the same way — and so the result is defensible to any
professional trader. This is the ground-truth **spec** the perception panel implements
and is certified against (see `PERCEPTION_ACCURACY_PROTOCOL.md`).

**Epistemic stance.**
- Where the field agrees, we state the consensus.
- Where educators disagree (noted as **[CONTESTED]**), we choose the most coherent rule
  and justify it. Disagreement is resolved by *one explicit rule*, not by vibes.
- Every primitive has (a) a plain definition, (b) exact machine-checkable criteria,
  (c) states/variants, (d) confidence + **abstention** rule. An expert that says
  "unclear" on a genuinely ambiguous chart is behaving correctly.
- Nothing here claims predictive edge. This is about *perceiving* the chart correctly.

---

## 0. Foundations

- **Candle anatomy.** body = |close−open|; range = high−low. A candle is *displacement*
  when body ≥ `displacement_body_factor` × (mean body of prior 20) **and**
  range ≥ 0.9 × (mean range of prior 20). Displacement = institutional intent.
- **Timeframe fractality.** Structure is read top-down: HTF (1D/4H) sets bias and the
  *draw on liquidity*; LTF (15m) is for entry confirmation. The same definitions apply
  at every timeframe; only the role changes.
- **Two structure scopes.**
  - **Swing (external) structure** = major swing highs/lows (wider pivot window).
  - **Internal structure** = minor highs/lows *between* two swing points (narrower pivot).
  Confusing the two is the #1 perception error; every structure object MUST carry a
  scope tag (`internal` | `swing` | `external`).

---

## 1. Swing points

- **Definition.** A swing high is a candle whose high is the local maximum over a pivot
  window of N candles each side; swing low symmetric.
- **Criteria.** `high[i] >= max(high[i-N : i+N+1])` (swing N = `swing_pivot_window`,
  internal N = `internal_pivot_window`, narrower).
- **Confidence/abstain.** High when strictly greater than neighbours; *low/abstain* on
  flat plateaus (equal highs) — those are liquidity, not a clean single pivot.

## 2. Break of Structure (BOS) — continuation

- **Definition.** Price continues the prevailing trend by breaking the most recent
  *protected* swing in the trend direction. Confirms trend continuation.
- **Criteria (body-close, the strict standard [CONTESTED: some use wick]):**
  bullish BOS = `close > swing_high × (1 + structure_break_min_pct)` **and** the breaking
  candle is displacement. Bearish symmetric on a swing low. Trend at the time is
  `neutral`/with-trend → label **BOS**.
- **Why body-close:** wick breaks are routinely liquidity sweeps, not structural breaks.
  Requiring a close removes the most common false BOS.
- **State/scope:** tag `internal` vs `swing`. Internal BOS ≠ swing BOS in meaning.
- **Confidence:** high if displacement strong + clean close beyond; low if marginal close
  within `structure_break_min_pct` band → abstain or mark `low`.

## 3. Change of Character (CHoCH) — first counter-trend break

- **Definition.** The *first* break of structure against the prevailing trend: breaks the
  most recent **protected** swing (the swing that confirmed the last leg). Signals a
  potential trend change — *character*, not yet confirmed reversal.
- **Criteria:** same break test as BOS, but the broken swing is the protected
  counter-trend swing and prevailing trend is opposite → label **CHoCH**. The engine's
  protected-swing logic encodes this.
- **[CONTESTED] CHoCH vs BOS:** some call any counter-trend break "CHoCH," others reserve
  it for breaks of the *major* swing. **Our rule:** CHoCH = break of the protected swing
  that created the current leg; a break of a minor internal counter-swing is an
  *internal CHoCH* (tagged scope=internal), not a swing CHoCH.
- **Confidence/abstain:** abstain when trend is itself unclear (no clean prior leg).

## 4. Liquidity (the fuel)

- **Definition.** Resting orders the market is drawn to. **Buy-side liquidity (BSL)** sits
  *above* highs (buy stops); **sell-side (SSL)** *below* lows (sell stops).
- **Forms (ranked by significance):** prior **week/day** high-low > **session** high-low >
  **equal highs/lows** (multi-touch cluster) > obvious single swing extreme > trendline
  liquidity. Significance = how many participants' stops likely rest there.
- **Criteria:** equal highs/lows = ≥ `equal_level_min_touches` swings within
  `equal_level_tolerance_pct`. Prior D/W/M = the high/low of the prior calendar period.
- **Draw on liquidity:** the nearest *unmitigated* opposing pool is the likely target.

## 5. Liquidity Sweep / Raid (stop hunt)

- **Definition.** Price wicks beyond a liquidity pool to trigger stops, then closes back
  inside — taking liquidity without accepting price. The engine of reversals.
- **Criteria:** bearish sweep of BSL = `high > level × (1 + ε)` **and** `close < level`.
  Bullish sweep of SSL = `low < level × (1 − ε)` **and** `close > level`. ε = half
  `structure_break_min_pct`.
- **States:** `swept` (taken, not reclaimed) vs `reclaimed`/`failed`. A sweep that is
  *immediately followed by displacement + structure break* is high-quality.
- **Confidence:** high when the swept pool is significant (D/W high, equal highs) AND a
  displacement follows; low when it sweeps a minor wiggle.
- **[REFINEMENT — validated by vision⇄engine adjudication, 2026-06-22].** The close MUST
  reclaim the level (close back on the origin side) for a *strict* sweep. A candle that
  wicks beyond a level but **closes beyond it** (accepting price beyond) is a BOS/continuation,
  NOT a sweep — even if it later reverses. A deep wick that recovers far off its low but still
  closes beyond the level is a separate **deep-wick rejection** variant, flagged only at LOW
  confidence. Rationale: on real BTC, a vision *gestalt* over-called two reversals as "sweeps"
  while the engine's close-based rule was correct. Engine owns precise wick-vs-close
  classification; vision owns gestalt/context. Do not relabel a correct BOS as a sweep to
  match an eye read.

## 6. Inducement (IDM) — [CONTESTED, defined explicitly]

- **Definition (our rule).** Inducement is the **minor opposing liquidity that sits
  between current price and the real POI**, which lures early entries; smart money sweeps
  the IDM *before* tapping the genuine POI. Concretely: in a bullish leg toward a demand
  POI, the IDM is the **nearest minor swing low above the POI** (the most recent internal
  pullback low) whose sweep precedes the move into the POI.
- **Criteria (machine):** given a selected POI and trend direction, IDM = the closest
  internal swing (opposite extreme) located strictly between price and the POI, with at
  least a minimal protrusion. A POI is only "valid for entry" once its IDM has been swept.
- **Why it matters:** distinguishes a *clean* POI (IDM already taken) from a *trap* POI
  (IDM still resting → expect a deeper move first).
- **Confidence/abstain:** abstain when no clear single minor pool exists between price and
  POI (genuinely common — do not invent an IDM).

## 7. Imbalance / Fair Value Gap (FVG)

- **Definition.** A 3-candle inefficiency where price moved so fast it left an untraded
  gap. Bullish FVG (BISI) = gap between candle-1 high and candle-3 low with a candle-2
  displacement up; bearish (SIBI) symmetric.
- **Criteria:** bullish: `low[i] − high[i-2] > 0`, gap/price ≥ `fvg_min_gap_pct`,
  candle `i-1` is displacement. Zone = `[high[i-2], low[i]]`.
- **States:** `fresh` (unfilled) → `partial` (wicked into) → `mitigated` (filled to far
  edge). Track `mitigation_pct`.
- **Confidence:** scales with displacement size; abstain on sub-threshold micro-gaps.

## 8. Order Block (OB)

- **Definition.** The last opposite-color candle before a displacement move that **breaks
  structure**. Bullish OB = last down candle before an up-move that makes a BOS/CHoCH.
- **Criteria:** within `ob_lookback` before the breaking event, the last opposite candle
  with body ≥ `ob_min_body_factor` × avg-body. Zone = that candle's [low, high].
- **[CONTESTED] last vs last-significant candle:** if the literal last opposite candle is
  tiny, some take the last *significant* one. **Our rule:** the OB is the last opposite
  candle whose body clears `ob_min_body_factor`; if none clears, abstain (no clean OB).
- **Quality:** strongest when the OB created displacement + an FVG + broke structure +
  sits in discount/premium correctly.

## 9. Breaker & Mitigation blocks — [to be added to engine]

- **Breaker block.** A failed OB: an OB that price violates, then *re-uses from the other
  side* after structure flips. Bullish breaker = a bearish OB that gets broken upward and
  then supports price.
- **Mitigation block.** Forms from a failure swing where price returns to the origin of a
  failed move. Distinguished from OB by the *preceding failure*.
- **Status:** these are engine gaps today; the panel must abstain (not guess) until the
  detectors exist.

## 10. Supply & Demand zones — [to be added as first-class]

- **Definition.** The origin (base) of an impulsive move: **demand** = base before a
  strong rally; **supply** = base before a strong drop. Broader than a single OB candle.
- **Relationship to OB:** the OB is the refined, last-candle version inside the S/D base.
  We emit both: S/D = the base region; OB = the precise candle. Direction: demand=bullish,
  supply=bearish.

## 11. Premium / Discount / Equilibrium

- **Dealing range.** The current swing range (low→high of the active leg).
- **Equilibrium** = 50% of the range. **Discount** = below 50% (buy zone in bullish bias);
  **Premium** = above 50% (sell zone in bearish bias).
- **OTE (optimal trade entry)** = the 0.62–0.79 retracement band of the leg — the premium
  of a discount / discount of a premium where A+ entries cluster.

## 12. Market-state synthesis (what it MEANS at that moment)

Reading = composing primitives into one narrative, e.g.:
> "HTF bias bullish. Price swept SSL (prior-day low) → displacement up → internal CHoCH.
> A fresh bullish FVG + OB sit in discount, IDM already taken. Draw on liquidity = BSL at
> equal highs above. Expectation: retrace into FVG/OB, continuation toward BSL; invalid if
> close back below the OB low."

The system must output this state with each call: bias, dealing-range location, last
event, active POIs, the draw on liquidity, and the invalidation — or abstain on any part
that is unclear.

## 13. Confidence & abstention (the heart of "expert")

- Every object emits `confidence ∈ {high, medium, low}` from explicit criteria above.
- **Abstention is mandatory** when criteria are marginal or context is unclear. A high
  false-positive rate on chop is a failure; principled silence is success.
- "Perfect" operationally = **high precision on confident calls + abstain on the rest**,
  measured on the certified gold set — never a bare point estimate.

## 14. Machine-checkable criteria index (thesis → implementation)

| Primitive | Type | Exact test | Engine status |
|---|---|---|---|
| swing | pivot | local extreme over pivot window | ✅ |
| BOS | event | body close beyond protected swing + displacement | ✅ |
| CHoCH | event | first counter-trend protected-swing break + displacement | ✅ |
| liquidity (equal H/L) | zone | ≥ N swings within tolerance | ✅ |
| prior D/W/M liquidity | level | prior period high/low | ❌ add |
| liquidity sweep | event | wick beyond level + close back inside | ✅ |
| inducement | event/level | nearest minor opposing pool between price & POI | ❌ add |
| FVG | zone | 3-candle gap + displacement | ✅ |
| order block | zone | last significant opposite candle before BOS/CHoCH | ✅ |
| breaker block | zone | failed OB re-used from other side | ❌ add |
| mitigation block | zone | failure-swing origin | ❌ add |
| supply/demand | zone | base before impulsive move | ❌ add (OB proxy today) |
| premium/discount | state | range location vs 50% | ✅ |
| OTE | state | 0.62–0.79 retracement band | ❌ add |

**Next:** implement the ❌ rows, then have three independent experts (engine, numeric-LLM,
vision) label per this thesis; promote high-confidence agreement to draft-gold; adjudicate
the disagreement pile against this document; certify, then automate.
