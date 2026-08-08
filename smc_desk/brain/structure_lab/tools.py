"""On-demand retrieval tools for the structure-lab AI roles (programme §4.6).

The retriever (``context_retriever``) keeps the compact context anchor-preserving
but necessarily drops some candidates from the fill set. The AI must still be
able to reach any candidate by id or attribute. These four deterministic
functions implement the programme's mandated tool surface:

    get_candidate(candidate_id)
    search_candidates(type, timeframe, price_range, time_range)
    get_parent_chain(candidate_id)
    get_break_origin(event_id)

They are pure functions over the candidate pool and the formal structure graph.
The role harness calls them on the model's behalf (the model emits a tool-use
request; the harness returns the JSON). No tool ever reads future data; they
operate on the same as-of slice the role already has.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from smc_desk.perception.programme_schema import (
    canonical_object_id,
    candidate_price_bounds,
    candidate_time,
    candidate_type,
)


class RetrievalTools:
    """Bound a candidate pool and a graph once, then answer tool calls.

    The pool is the *full* as-of candidate set (not the compacted context).
    The graph is the certified ``formal_structure_graph`` for the case.
    """

    def __init__(
        self,
        candidate_pool: Sequence[Mapping[str, Any]],
        graph: Mapping[str, Any] | None = None,
    ) -> None:
        self._by_id: dict[str, Mapping[str, Any]] = {}
        for c in candidate_pool:
            cid = canonical_object_id(c)
            if cid:
                self._by_id[cid] = c
        self._pool: list[Mapping[str, Any]] = list(candidate_pool)
        self._graph: Mapping[str, Any] = graph or {}

    # -- public tool surface -------------------------------------------------

    def get_candidate(self, candidate_id: str) -> dict[str, Any]:
        """Return the full record for ``candidate_id`` or an explicit not_found."""
        rec = self._by_id.get(candidate_id)
        if rec is None:
            return {"object_id": candidate_id, "found": False}
        out = dict(rec)
        out["found"] = True
        return out

    def search_candidates(
        self,
        *,
        type: str | None = None,
        timeframe: str | None = None,
        price_range: tuple[float, float] | None = None,
        time_range: tuple[str, str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Filter the pool by the four optional axes. All filters are AND."""
        results: list[dict[str, Any]] = []
        for c in self._pool:
            if type is not None and candidate_type(c) != type:
                continue
            if timeframe is not None and str(c.get("timeframe") or "") != timeframe:
                continue
            if price_range is not None:
                lo, hi = price_range
                bounds = candidate_price_bounds(c)
                if bounds is None or bounds[1] < lo or bounds[0] > hi:
                    continue
            if time_range is not None:
                t = _candidate_time(c)
                if not (time_range[0] <= t <= time_range[1]):
                    continue
            rec = dict(c)
            rec["found"] = True
            results.append(rec)
            if len(results) >= limit:
                break
        return results

    def get_parent_chain(self, candidate_id: str) -> list[dict[str, Any]]:
        """Walk parent_candidate_ids / parent object links to the root.

        Cycles are guarded: a candidate seen once is not revisited.
        """
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        current = candidate_id
        while current and current not in seen:
            seen.add(current)
            rec = self._by_id.get(current)
            if rec is None:
                chain.append({"object_id": current, "found": False})
                break
            chain.append({"object_id": current, "found": True, **_link_fields(rec)})
            parents = rec.get("parent_candidate_ids") or rec.get("parent_ids") or []
            if not isinstance(parents, list) or not parents:
                break
            current = str(parents[0])
        return chain

    def get_break_origin(self, event_id: str) -> dict[str, Any]:
        """Return the causal origin candidate(s) for a structural break event.

        Looks up accepted_breaks in the graph by object_id and resolves the
        origin_object_id back to its full candidate record.
        """
        breaks = list(self._graph.get("accepted_breaks") or [])
        for node in (self._graph.get("timeframes") or {}).values():
            if isinstance(node, Mapping):
                for key in ("latest_external_break", "latest_internal_break"):
                    event = node.get(key)
                    if isinstance(event, Mapping):
                        breaks.append(event)
        target = None
        for br in breaks:
            if not isinstance(br, Mapping):
                continue
            if str(br.get("object_id") or br.get("event_id") or "") == event_id:
                target = br
                break
        if target is None:
            return {"event_id": event_id, "found": False}
        origin_id = str(target.get("origin_object_id") or "")
        origin = self.get_candidate(origin_id) if origin_id else {"found": False}
        return {
            "event_id": event_id,
            "found": True,
            "break": dict(target),
            "origin": origin,
        }

    # -- introspection -------------------------------------------------------

    def available_ids(self) -> list[str]:
        return list(self._by_id)

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any] | list[dict[str, Any]]:
        """Dispatch a model-emitted tool-use request to the right function.

        Returns a dict with ``tool``, ``ok`` and the result payload. The role
        harness serialises this for the model.
        """
        name = str(request.get("tool") or request.get("name") or "")
        args = request.get("arguments") or request.get("args") or {}
        if not isinstance(args, Mapping):
            args = {}
        try:
            if name == "get_candidate":
                return {"tool": name, "ok": True, "result": self.get_candidate(str(args.get("candidate_id", "")))}
            if name == "search_candidates":
                pr = args.get("price_range")
                tr = args.get("time_range")
                return {
                    "tool": name,
                    "ok": True,
                    "result": self.search_candidates(
                        type=args.get("type"),
                        timeframe=args.get("timeframe"),
                        price_range=(float(pr[0]), float(pr[1])) if isinstance(pr, (list, tuple)) and len(pr) == 2 else None,
                        time_range=(str(tr[0]), str(tr[1])) if isinstance(tr, (list, tuple)) and len(tr) == 2 else None,
                        limit=int(args.get("limit", 50)),
                    ),
                }
            if name == "get_parent_chain":
                return {"tool": name, "ok": True, "result": self.get_parent_chain(str(args.get("candidate_id", "")))}
            if name == "get_break_origin":
                return {"tool": name, "ok": True, "result": self.get_break_origin(str(args.get("event_id", "")))}
            return {"tool": name, "ok": False, "error": "unknown_tool"}
        except Exception as exc:  # surface tool errors to the model, not crash
            return {"tool": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


# Tool schema the role harness advertises to the model.
TOOL_DEFINITIONS = [
    {
        "name": "get_candidate",
        "description": "Fetch the full record for one candidate_id not present in the compact context.",
        "parameters": {"candidate_id": {"type": "string", "required": True}},
    },
    {
        "name": "search_candidates",
        "description": "Filter the full candidate atlas by type/timeframe/price_range/time_range.",
        "parameters": {
            "type": {"type": "string"},
            "timeframe": {"type": "string"},
            "price_range": {"type": "array", "items": "number", "length": 2},
            "time_range": {"type": "array", "items": "string", "length": 2},
            "limit": {"type": "integer"},
        },
    },
    {
        "name": "get_parent_chain",
        "description": "Walk parent links from a candidate up to the structural root.",
        "parameters": {"candidate_id": {"type": "string", "required": True}},
    },
    {
        "name": "get_break_origin",
        "description": "Resolve the causal origin candidate for a structural break event_id.",
        "parameters": {"event_id": {"type": "string", "required": True}},
    },
]


def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _candidate_time(c: Mapping[str, Any]) -> str:
    return candidate_time(c)


def _link_fields(rec: Mapping[str, Any]) -> dict[str, Any]:
    """Compact subset for parent-chain entries."""
    out: dict[str, Any] = {}
    for k in ("object_id", "timeframe", "pivot_type", "pivot_price", "pivot_time", "lifecycle", "parent_candidate_ids"):
        if k in rec:
            out[k] = rec[k]
    return out


__all__ = ["RetrievalTools", "TOOL_DEFINITIONS"]
