from __future__ import annotations

from typing import Any


TIMEFRAME_CHAIN = ("1d", "4h", "1h", "15m")


def _swing_price(swing: dict[str, Any]) -> float:
    direction = swing.get("direction")
    value = swing.get("price_high") if direction == "bearish" else swing.get("price_low")
    return float(value)


def _latest_swings(payload: dict[str, Any], direction: str, limit: int = 3) -> list[dict[str, Any]]:
    swings = []
    for scale_items in (payload.get("swings") or {}).values():
        for swing in scale_items:
            if swing.get("direction") == direction:
                swings.append(swing)
    return sorted(swings, key=lambda item: str(item.get("confirmed_at") or item.get("candidate_at") or item.get("pivot_time")), reverse=True)[:limit]


def _latest_break(payload: dict[str, Any]) -> dict[str, Any] | None:
    breaks = payload.get("structure_breaks") or []
    if not breaks:
        return None
    return sorted(breaks, key=lambda item: str(item.get("confirmed_at") or item.get("candidate_at") or item.get("pivot_time")))[-1]


def build_semantic_overlay(
    *,
    perception_by_tf: dict[str, dict[str, Any]],
    mtf_snapshot: dict[str, Any],
    legacy_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build explicit but conservative SMC semantic candidates.

    These are reasoning aids, not adjudicated gold labels. Names use
    ``candidate`` or ``proxy`` where the current PerceptionEngineV2 object set
    cannot prove the richer SMC object directly.
    """

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    execution_consensus = mtf_snapshot.get("execution_consensus")
    plan = (legacy_analysis or {}).get("trade_plan", {})
    selected_poi = plan.get("selected_poi")

    for tf in TIMEFRAME_CHAIN:
        payload = perception_by_tf.get(tf, {})
        for side, direction in (("buy_side", "bearish"), ("sell_side", "bullish")):
            for rank, swing in enumerate(_latest_swings(payload, direction, limit=2), start=1):
                node_id = f"liquidity:{tf}:{side}:{rank}"
                nodes.append(
                    {
                        "node_id": node_id,
                        "object_type": "liquidity_pool_candidate",
                        "timeframe": tf,
                        "side": side,
                        "direction": "bullish" if side == "buy_side" else "bearish",
                        "price": _swing_price(swing),
                        "source_object_id": swing.get("object_id"),
                        "confirmed_at": swing.get("confirmed_at"),
                        "confidence": min(0.85, float(swing.get("confidence") or 0.5)),
                        "authority": "candidate_from_confirmed_swing",
                    }
                )
                edges.append({"from": f"timeframe:{tf}", "to": node_id, "relationship": "HAS_LIQUIDITY_POOL"})

        latest = _latest_break(payload)
        if latest and latest.get("break_type") == "CHOCH":
            node_id = f"breaker_candidate:{tf}:{latest.get('object_id')}"
            nodes.append(
                {
                    "node_id": node_id,
                    "object_type": "breaker_candidate",
                    "timeframe": tf,
                    "direction": latest.get("direction"),
                    "source_break_id": latest.get("object_id"),
                    "confirmed_at": latest.get("confirmed_at"),
                    "authority": "candidate_from_choch_requires_review",
                }
            )
            edges.append({"from": f"structure_break:{tf}:{latest.get('object_id')}", "to": node_id, "relationship": "MAY_CREATE_BREAKER_CONTEXT"})

        for fvg in (payload.get("fvgs") or [])[-2:]:
            if fvg.get("confirmation_status") != "confirmed" or fvg.get("mitigation_status") == "full":
                continue
            node_id = f"ob_proxy:{tf}:{fvg.get('object_id')}"
            nodes.append(
                {
                    "node_id": node_id,
                    "object_type": "order_block_proxy",
                    "timeframe": tf,
                    "direction": fvg.get("direction"),
                    "price_low": fvg.get("price_low"),
                    "price_high": fvg.get("price_high"),
                    "source_fvg_id": fvg.get("object_id"),
                    "authority": "proxy_from_fvg_origin_not_certified_ob",
                }
            )
            edges.append({"from": f"fvg:{tf}:{fvg.get('object_id')}", "to": node_id, "relationship": "MAY_SHARE_IMBALANCE_ORIGIN"})

    if execution_consensus in {"bullish", "bearish"}:
        inducement_side = "sell_side" if execution_consensus == "bullish" else "buy_side"
        for node in list(nodes):
            if node.get("object_type") == "liquidity_pool_candidate" and node.get("timeframe") == "15m" and node.get("side") == inducement_side:
                induced_id = f"inducement:{node['node_id']}"
                nodes.append(
                    {
                        "node_id": induced_id,
                        "object_type": "inducement_candidate",
                        "timeframe": "15m",
                        "direction": execution_consensus,
                        "liquidity_side": inducement_side,
                        "price": node.get("price"),
                        "source_liquidity_id": node["node_id"],
                        "authority": "candidate_requires_sweep_displacement_confirmation",
                    }
                )
                edges.append({"from": node["node_id"], "to": induced_id, "relationship": "MAY_ACT_AS_INDUCEMENT_FOR"})
                break

    if selected_poi:
        poi_node_id = "poi:selected_15m"
        nodes.append(
            {
                "node_id": poi_node_id,
                "object_type": "selected_execution_poi",
                "timeframe": "15m",
                "kind": selected_poi.get("kind"),
                "direction": selected_poi.get("direction"),
                "price_low": selected_poi.get("low"),
                "price_high": selected_poi.get("high"),
                "status": selected_poi.get("status"),
                "authority": "legacy_comparison_selected_poi",
            }
        )
        edges.append({"from": poi_node_id, "to": "decision:current", "relationship": "PROPOSED_EXECUTION_AREA"})

    counts: dict[str, int] = {}
    for node in nodes:
        counts[node["object_type"]] = counts.get(node["object_type"], 0) + 1
    return {
        "semantic_version": "0.1",
        "authority": "candidate_semantics_not_gold_truth",
        "nodes": nodes,
        "edges": edges,
        "summary": counts,
    }
