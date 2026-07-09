from __future__ import annotations

from smc_desk.brain.prompt_system.prompt_contract import PromptModule


PROMPT = PromptModule(
    name="annotation_prompt",
    version="1.1.0",
    purpose="Make the AI output a clean professional SMC annotation plan, not detector clutter.",
    text="""Annotation rules:

Output annotation_plan as the clean trader-facing thought process.
Output annotation_plan_v2 as the professional drawing instruction layer whenever possible.
Do not output raw BOS/CHoCH/FVG/swing clutter as official labels.
The renderer will draw annotation_plan_v2 after validation, falling back to legacy annotation_plan only when v2 is absent.

Context chart: max 5 reasoning labels, but only the top 2 should be visually important.
Watch/review chart: max 7 reasoning labels, but only the top 3 should be visually important.
Trade-plan chart: max 8 reasoning labels, but only the top 5 should be visually important.
Debug chart is separate and not official.

Watch charts may show:
1. One active POI / watch zone, bounded to the origin candles or recent return area.
2. One short BOS/CHoCH/IDM/confirmation segment anchored between the swing and the break.
3. One target-liquidity draw, only if it is directly relevant and locally visible.

Keep watch-chart annotations sparse like a professional TradingView markup.
V2 professional objects:
- structure_segment: short BOS/CHoCH/IDM line anchored exactly between the source swing and confirmation candle. Include structure_scope=external or internal; internal labels must visibly say iBOS/iCHoCH or Internal BOS/CHoCH.
- poi_zone: bounded OB/FVG/POI rectangle around origin candles or the recent return area.
- liquidity_line: short BSL/SSL/EQH/EQL/IDM line with local span.
- path_projection: optional dashed thesis path, never a prediction guarantee, only after a certified active POI exists.
- trade_box: only when official_state is TRADE_PLAN_READY; use kind=trade and include entry_price, stop_price, and target_prices matching the validated decision.

Every v2 object must include semantic_object_id, timeframe, reason, start/end index or time, price/zone coordinates, and evidence_object_ids. The validator compares those coordinates against the underlying graph/detector object; an existing ID alone is not enough.
Do not turn the chart into a written thesis. Put detailed reasoning in final_thesis, not on the chart.
Do not draw full-width zones across the whole chart unless the level is a genuine HTF range boundary.
Prefer localized rectangles and short horizontal segments with start_index/end_index.
Labels should sit beside the object they explain, not in a large text panel.

Watch charts must not show entry, SL, TP, RR trade box, or risk instructions.

Trade-plan charts may show entry, SL, TP, and RR only when official_state is TRADE_PLAN_READY.""",
)
