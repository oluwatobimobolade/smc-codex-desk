"""Decision-facing POI selection API.

The POI objects are built in ``smc_desk.perception.poi_lifecycle`` because
validity depends on perceived structure.  This thin decision module gives the
watch-state layer a stable import path for the protected-range selector.
"""
from __future__ import annotations

from smc_desk.perception.poi_lifecycle import (
    build_poi_selection,
    rank_poi_candidates,
    select_active_poi,
)

__all__ = ["build_poi_selection", "rank_poi_candidates", "select_active_poi"]
