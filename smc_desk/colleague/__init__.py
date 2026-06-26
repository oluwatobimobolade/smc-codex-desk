"""Market Colleague orchestration package.

This package is the migration target for the operator-facing desk workflow.
PerceptionEngineV2 is the primary perception source; legacy engine output is
kept as comparison evidence only.
"""

from .orchestrator import run_colleague_analysis
from .request_contract import ColleagueRunRequest, default_ohlcv_path, normalize_symbol

__all__ = ["ColleagueRunRequest", "default_ohlcv_path", "normalize_symbol", "run_colleague_analysis"]
