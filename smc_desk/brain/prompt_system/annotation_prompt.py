from __future__ import annotations

from smc_desk.brain.prompt_system.prompt_contract import PromptModule


PROMPT = PromptModule(
    name="annotation_prompt",
    version="1.5.0",
    purpose="Make the AI output a clean professional SMC annotation plan, not detector clutter.",
    text="""Annotation rules:

Output annotation_plan as the clean trader-facing thought process.
Output annotation_plan_v2 as the professional drawing instruction layer whenever possible.
Design the chart from formal_causal_episode_graph.current_story, not by selecting isolated detector labels. Every visible object must have a role in the same causal episode.
Do not output raw BOS/CHoCH/FVG/swing clutter as official labels.
The renderer will draw annotation_plan_v2 after validation, falling back to legacy annotation_plan only when v2 is absent.

Context chart: max 5 reasoning labels, but only the top 2 should be visually important.
Watch/review chart: max 7 reasoning labels, but only the top 3 should be visually important.
Trade-plan chart: max 8 reasoning labels, but only the top 5 should be visually important.
Debug chart is separate and not official.

Watch charts may show:
1. One causal_poi_authority-selected active POI / watch zone, bounded to its traced origin cluster. A subordinate execution refinement may be added only when it overlaps the parent POI.
2. One short BOS/CHoCH/IDM/confirmation segment anchored between the swing and the break.
3. One target-liquidity draw, only if it is directly relevant and locally visible.

Across the native MTF chart pack, preserve scope rather than forcing every mark onto 15m:
- 4H: parent external episode, protected origin/range, HTF POI, external liquidity.
- 1H: controlling setup episode, internal pullback, sweep/inducement, primary and secondary POI roles.
- 15m: execution confirmation only: local sweep, displacement, internal CHoCH/BOS, and active refinement.

After selecting the active setup, audit annotation_context_authority. A zone
that lost active-entry authority after a later opposing external break may
still be material context. Retain it only when the deterministic atlas supplies
a requirement_id. Cite that requirement in context_exception_requests, keep
the exact sealed geometry, mark the drawing context-only, and set
active_entry_authority=false. This exception changes visibility only: it may
not alter bias, the active POI, trade state, entry, stop, target, or trade box.

Keep watch-chart annotations sparse like a professional TradingView markup.
V2 professional objects:
- structure_segment: short BOS/CHoCH/IDM line anchored exactly between the source swing and confirmation candle. Include structure_scope=external or internal; internal labels must visibly say iBOS/iCHoCH or Internal BOS/CHoCH.
- poi_zone: bounded OB/FVG/POI rectangle around origin candles or the recent return area.
- liquidity_line: short BSL/SSL/EQH/EQL/IDM line with local span.
- path_projection: optional dashed thesis path, never a prediction guarantee, only after a certified active POI exists.
- trade_box: only when official_state is TRADE_PLAN_READY; use kind=trade and include entry_price, stop_price, and target_prices matching the validated decision.

Every v2 object must include semantic_object_id, timeframe, reason, evidence_object_ids, evidence_contract_ids, immutable evidence_geometry, and separately derived display_geometry. Context objects must also include display_role, control_status, active_entry_authority=false, and context_requirement_id. Display clipping may shorten only the horizontal presentation span and must preserve prices and the confirmation anchor. The validator reconstructs both geometries; an existing ID alone is not enough.
Do not turn the chart into a written thesis. Put detailed reasoning in final_thesis, not on the chart.
Do not draw full-width zones across the whole chart unless the level is a genuine HTF range boundary.
Prefer localized rectangles and short horizontal segments with start_index/end_index.
Labels should sit beside the object they explain, not in a large text panel.

Watch charts must not show entry, SL, TP, RR trade box, or risk instructions.

Trade-plan charts may show entry, SL, TP, and RR only when official_state is TRADE_PLAN_READY.""",
)
