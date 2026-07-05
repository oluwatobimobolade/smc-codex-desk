"""Audit manifest for external AI agent handoff.

Logs the full chain of custody for an external AI agent review:

  - When the packet was exported
  - What files were in the packet
  - Packet hash (evidence pack hash)
  - File hashes for each packet file
  - When the response was imported
  - Agent identity (name, model, version)
  - Response hash
  - Packet hash match (did the agent review the right packet?)
  - Validation result
  - Final decision status
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_agent_audit_manifest(
    *,
    symbol: str,
    packet_dir: Path,
    response_dir: Path,
    packet_manifest: Mapping[str, Any],
    response_audit: Mapping[str, Any],
    validation_status: str,
    official_state: str,
    final_decision_hash: str | None = None,
) -> dict[str, Any]:
    """Build the complete audit manifest for the handoff."""
    return {
        "schema": "ai_smc_agent_audit_v1",
        "symbol": symbol,
        "packet": {
            "dir": str(packet_dir),
            "manifest": dict(packet_manifest),
        },
        "response": {
            "dir": str(response_dir),
            "audit": dict(response_audit),
        },
        "validation": {
            "validation_status": validation_status,
            "official_state": official_state,
        },
        "final_decision_hash": final_decision_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_agent_audit_manifest(manifest: Mapping[str, Any], output_path: Path) -> None:
    """Write the audit manifest to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
