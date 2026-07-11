"""Multi-scale candidate atlas generators (programme §4).

Public surface:
* schema     -- canonical SwingCandidate + generator identifiers
* indicators -- ATR, realised volatility, body ratio, FVG, runs of direction
* fractal    -- DataFrame-native fractal detector
* directional_change -- volatility-adaptive directional change
* prominence -- protrusion + survival
* changepoint -- CUSUM-style mean shift detection
* displacement -- impulse origin tracing
* atlas      -- fusion across generators
"""
from smc_desk.perception.candidates import atlas as atlas_mod
from smc_desk.perception.candidates import changepoint as changepoint
from smc_desk.perception.candidates import directional_change as directional_change
from smc_desk.perception.candidates import displacement as displacement
from smc_desk.perception.candidates import fractal as fractal
from smc_desk.perception.candidates import indicators as indicators
from smc_desk.perception.candidates import prominence as prominence
from smc_desk.perception.candidates import schema as schema
from smc_desk.perception.candidates.atlas import AtlasBuildResult, AtlasConfig, build_for_timeframe
from smc_desk.perception.candidates.schema import ALL_GENERATORS, SwingCandidate, candidate_id

__all__ = [
    "ALL_GENERATORS",
    "AtlasBuildResult",
    "AtlasConfig",
    "SwingCandidate",
    "atlas_mod",
    "build_for_timeframe",
    "candidate_id",
    "changepoint",
    "directional_change",
    "displacement",
    "fractal",
    "indicators",
    "prominence",
    "schema",
]