"""Market Colleague orchestration package.

This package is the migration target for the operator-facing desk workflow.
PerceptionEngineV2 is the primary perception source; legacy engine output is
kept as comparison evidence only.

Import the orchestrator functions directly from their submodules to avoid
eagerly loading legacy rendering dependencies:

    from smc_desk.colleague.orchestrator import run_colleague_analysis
    from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3
"""

from .request_contract import ColleagueRunRequest, default_ohlcv_path, normalize_symbol

__all__ = ["ColleagueRunRequest", "default_ohlcv_path", "normalize_symbol"]
