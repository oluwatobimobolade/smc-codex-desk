# SMC Perception Annotation Manual V1.0.0

This manual provides strict instructions for annotating structures on raw 15m charts. Your annotations act as the definitive Gold standard for testing machine perception algorithms.

Do not assume what the chart *ought* to have done based on subsequent action. You must label only what geometrically exists up to the *decision candle* (the very last candle on the chart).

## Global Rules

1. **Information Horizon:** You cannot use information that occurs after the rightmost candle.
2. **Ambiguity:** If a structure is poorly formed or unclear, mark it `AMBIGUOUS`.
3. **Insufficient Context:** If the left side of the chart does not contain enough data to make a definitive structural call, mark `INSUFFICIENT_CONTEXT`. Do not guess.

---

## 1. Swings

A **Swing** is a structural pivot.

*   **Local Swing:** A raw pivot point (High or Low) formed by a minimum of 3 candles (e.g., lower-high, highest-high, lower-high).
*   **Internal Swing:** A swing that causes a break of sub-structure (minor pivots) but does not result in a new macro high/low.
*   **External Swing:** The absolute extreme (highest high or lowest low) within the dominant dealing range.
*   **Equal Highs/Lows:** If two adjacent candles have the exact same high/low, the first candle in time is the pivot.
*   **Nested Swings:** If an internal swing occurs within the leg of an external swing, both can exist simultaneously. Annotate their scope appropriately.

**Examples:**
*   **Positive:** A clear 5-candle fractal top (2 lower highs on left, 2 on right).
*   **Negative:** A high candle that is immediately broken by the next candle (not a valid swing).

---

## 2. Protected Structure

A **Protected Point** is the origin swing of a move that successfully broke significant structure (BOS or CHoCH).

*   **Selection:** The lowest point before a bullish structural break, or the highest point before a bearish structural break.
*   **Wick vs. Body:** A protected point is invalidated **only** by a body close beyond its price extreme. A wick probing past the protected point is a liquidity sweep, not a break of structure.
*   **Internal vs. External:** A protected point is external if it originates a major BOS. It is internal if it only originates an internal sub-structure break.

**Examples:**
*   **Positive:** The absolute lowest wick before a massive bullish impulse that causes a BOS.
*   **Ambiguous:** The origin point is a messy cluster of wicks with no clear singular origin candle.

---

## 3. Break of Structure (BOS)

A **BOS** is the continuation of the existing structural trend.

*   **Direction:** Must align with the prior structural break (e.g., a bullish BOS following a bullish BOS/CHoCH).
*   **Broken Swing:** The BOS must break the most recent valid external (or internal, depending on scope) swing.
*   **Wick vs. Body:** A valid BOS **must** feature a body closing beyond the extreme wick of the broken swing. A wick-only break is a sweep.
*   **Confirmation:** The exact candle whose body closes beyond the level is the confirmation candle.

**Examples:**
*   **Positive:** Price forms a swing high, retraces, then pushes up, and a 15m candle closes completely above the swing high's wick.
*   **Negative:** Price pushes above the swing high but closes back below it (Liquidity Sweep).

---

## 4. Change of Character (CHoCH)

A **CHoCH** is the first break of structure against the prevailing trend, indicating a potential reversal.

*   **Broken Swing:** A bearish CHoCH occurs when the most recent **bullish protected low** is broken. A bullish CHoCH occurs when the most recent **bearish protected high** is broken.
*   **Confirmation:** Like a BOS, a CHoCH requires a body close beyond the protected point's wick.
*   **Context:** If the prior trend is entirely unclear due to insufficient leftward data, you must mark `INSUFFICIENT_CONTEXT` rather than guessing if a break is a CHoCH or BOS.

**Examples:**
*   **Positive:** An uptrend produces a protected low. Price reverses and a candle closes below the wick of that protected low.
*   **Negative:** Price breaks a minor internal low, but the external protected low remains intact. (This is an internal structural shift, not an external CHoCH).

---

## 5. Fair Value Gaps (FVG)

An **FVG** is a 3-candle imbalance.

*   **Geometry:**
    *   **Bullish FVG:** The low of Candle 3 is strictly higher than the high of Candle 1.
    *   **Bearish FVG:** The high of Candle 3 is strictly lower than the low of Candle 1.
*   **Equality:** If High(1) == Low(3), there is no gap. It is a perfectly balanced price action. The gap must be > 0.
*   **Mitigation State:**
    *   **Unmitigated:** No subsequent candle has entered the gap region.
    *   **Partially Mitigated:** A subsequent wick has entered the gap, but not completely filled it.
    *   **Fully Mitigated / Invalidated:** A subsequent wick has completely overlapped the gap, or a body has closed entirely beyond the gap.

**Examples:**
*   **Positive:** Candle 1 high is 100. Candle 2 is a massive green body. Candle 3 low is 105. The FVG exists between 100 and 105.
*   **Negative:** Candle 1 high is 100. Candle 3 low is 99. No FVG.
