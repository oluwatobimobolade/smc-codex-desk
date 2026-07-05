#!/usr/bin/env python3
"""Import an external AI agent's response and run the full validation pipeline.

Usage:
    python tools/run_import_agent_response.py \\
        --packet-dir analysis_runs/AGENT_PACKET_BTCUSDT_*/ai_agent_packet \\
        --response-dir analysis_runs/AGENT_PACKET_BTCUSDT_*/ai_agent_response \\
        --output-dir analysis_runs/AGENT_PACKET_BTCUSDT_*/validation

The system:
1. Validates the response structure
2. Imports the decision JSON
3. Rebuilds the evidence pack from the packet
4. Runs the full consistency validator
5. Grounds levels in OHLCV
6. Renders the official chart
7. Writes the audit manifest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from smc_desk.brain.agent_handoff.agent_audit_manifest import (
    build_agent_audit_manifest,
    write_agent_audit_manifest,
)
from smc_desk.brain.agent_handoff.external_agent_provider import ExternalAIAgentProvider
from smc_desk.brain.agent_handoff.import_agent_response import (
    import_agent_response,
    validate_response_structure,
)
from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.colleague.orchestrator_v3 import _status
from smc_desk.brain.llm_provider import LLMCompletionRequest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-dir", required=True)
    parser.add_argument("--response-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    packet_dir = Path(args.packet_dir)
    response_dir = Path(args.response_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    errors = validate_response_structure(response_dir)
    if errors:
        raise SystemExit(f"Invalid response: {'; '.join(errors)}")

    packet_manifest = json.loads((packet_dir / "run_manifest.json").read_text(encoding="utf-8"))
    evidence_pack_path = packet_dir / "02_evidence_pack.json"
    evidence_pack = json.loads(evidence_pack_path.read_text(encoding="utf-8"))

    expected_hash = packet_manifest.get("evidence_pack_hash")
    imported = import_agent_response(response_dir, expected_packet_hash=expected_hash)
    decision = imported["decision"]
    decision_payload = imported["decision_payload"]

    chart_images = {}
    for tf in ("1d", "4h", "1h", "15m", "5m"):
        for filename in [f"0{4 + i}_clean_{tf}_chart.png" for i in range(4)] + [f"0{4}_clean_{tf}_chart.png"]:
            path = packet_dir / filename
            if path.exists():
                chart_images[tf] = {"path": str(path), "exists": True}

    provider = ExternalAIAgentProvider(
        decision_payload,
        agent_name=decision_payload.get("agent_identity", {}).get("agent_name", "unknown"),
        agent_model=decision_payload.get("agent_identity", {}).get("agent_model", "unknown"),
        packet_hash=expected_hash,
    )

    from smc_desk.brain.prompt_system import build_prompt_registry_manifest
    prompt = build_prompt_registry_manifest(include_text=True)
    request = LLMCompletionRequest(
        prompt=json.dumps(prompt, default=str),
        evidence_pack=evidence_pack,
        chart_images=chart_images,
    )
    provider_result = provider.complete(request)

    validation_result = validate_ai_smc_decision(decision, evidence_pack)
    status = _status(provider_result=provider_result, validation_result=validation_result)

    (output_dir / "validation_result.json").write_text(
        json.dumps(validation_result.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output_dir / "official_decision.json").write_text(
        json.dumps(decision.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output_dir / "provider_manifest.json").write_text(
        json.dumps(provider_result.audit_record(), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    final_decision_hash = hashlib.sha256(
        json.dumps(decision.model_dump(mode="json", by_alias=True), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    audit_manifest = build_agent_audit_manifest(
        symbol=decision.symbol,
        packet_dir=packet_dir,
        response_dir=response_dir,
        packet_manifest=packet_manifest,
        response_audit=imported["audit"],
        validation_status=validation_result.status,
        official_state=str(validation_result.official_decision.get("official_state", "")),
        final_decision_hash=final_decision_hash,
    )
    write_agent_audit_manifest(audit_manifest, output_dir / "agent_audit_manifest.json")

    summary = {
        "schema": "agent_response_import_v1",
        "symbol": decision.symbol,
        "status": status,
        "validation_result": validation_result.status,
        "official_state": validation_result.official_decision.get("official_state"),
        "provider_mode": provider_result.provider_mode,
        "agent_identity": decision_payload.get("agent_identity", {}),
        "packet_hash_match": imported["audit"]["packet_hash_match"],
        "output_dir": str(output_dir),
    }
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
