#!/usr/bin/env python3
"""Audit perception/strategy authority boundaries without changing runtime config."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.rules import RUNTIME_CONFIG_SOURCE, RuleConfig


MONOLITH_PATH = ROOT / "specs" / "PERCEPTION_ONTOLOGY_V2.yaml"
DETECTOR_SPLIT_PATH = ROOT / "specs" / "PERCEPTION_DETECTOR_CONFIG_V2.yaml"
STRATEGY_SPLIT_PATH = ROOT / "specs" / "STRATEGY_EXECUTION_CONFIG_V1.yaml"
SPLIT_MANIFEST_PATH = ROOT / "specs" / "AUTHORITY_CONFIG_SPLIT_WP0015.yaml"

MIXED_AUTHORITY_TERMS = {
    "confirmation_lookback",
    "max_zone_age_bars",
    "poi_proximity_atr",
    "htf_poi_watch_distance_atr",
    "htf_approach_lookback_bars",
    "min_poi_width_bps",
    "require_fresh_poi",
    "risk_reward_floor",
    "structural_stop_margin_bps",
    "stop_buffer_atr_mult",
    "allowed_poi_kinds",
    "capital_risk",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping.")
    return payload


def _flatten_keys(payload: Any, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_str = str(key)
            path = f"{prefix}.{key_str}" if prefix else key_str
            keys.add(key_str)
            keys.add(path)
            keys.update(_flatten_keys(value, path))
    elif isinstance(payload, list):
        for item in payload:
            keys.update(_flatten_keys(item, prefix))
    return keys


def audit_authority_split(
    *,
    monolith_path: Path = MONOLITH_PATH,
    detector_split_path: Path = DETECTOR_SPLIT_PATH,
    strategy_split_path: Path = STRATEGY_SPLIT_PATH,
    split_manifest_path: Path = SPLIT_MANIFEST_PATH,
) -> dict[str, Any]:
    monolith = _load_yaml(monolith_path)
    detector = _load_yaml(detector_split_path)
    strategy = _load_yaml(strategy_split_path)
    split_manifest = _load_yaml(split_manifest_path)

    monolith_keys = _flatten_keys(monolith)
    detector_keys = _flatten_keys(detector)
    strategy_keys = _flatten_keys(strategy)
    mixed_in_monolith = sorted(term for term in MIXED_AUTHORITY_TERMS if term in monolith_keys)
    mixed_in_detector = sorted(term for term in MIXED_AUTHORITY_TERMS if term in detector_keys)
    strategy_terms_present = sorted(term for term in MIXED_AUTHORITY_TERMS if term in strategy_keys)
    split_ready = bool(
        mixed_in_monolith
        and not mixed_in_detector
        and {"risk_reward_floor", "stop_buffer_atr_mult", "require_fresh_poi"}.issubset(strategy_terms_present)
    )
    runtime_config = RuleConfig()
    runtime_migrated = runtime_config.runtime_config_source == RUNTIME_CONFIG_SOURCE
    if split_ready and runtime_migrated:
        status = "runtime_config_migrated_to_split_contracts"
    elif split_ready:
        status = "split_contract_ready_code_migration_pending"
    else:
        status = "authority_split_failed"
    return {
        "audit_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "monolith": {
            "path": str(monolith_path),
            "mixed_authority_terms": mixed_in_monolith,
            "runtime_status": "still_runtime_source_for_backward_compatibility",
        },
        "detector_split": {
            "path": str(detector_split_path),
            "mixed_authority_terms": mixed_in_detector,
            "clean_for_detector_authority": not mixed_in_detector,
        },
        "strategy_split": {
            "path": str(strategy_split_path),
            "strategy_terms_present": strategy_terms_present,
        },
        "split_manifest": {
            "path": str(split_manifest_path),
            "status": split_manifest.get("status"),
        },
        "runtime_config": {
            "source": runtime_config.runtime_config_source,
            "detector_config_id": runtime_config.detector_config_id,
            "strategy_config_id": runtime_config.strategy_config_id,
            "migrated_to_split_contracts": runtime_migrated,
        },
        "promotion_status": "blocked_until_live_shadow_and_adjudicated_validation",
        "market_edge_claimed": False,
        "paper_execution_enabled": False,
        "live_execution_enabled": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Ontology Authority Audit",
        "",
        f"Status: `{report['status']}`",
        "",
        "## Monolith",
        "",
        f"- Runtime source: `{report['monolith']['path']}`",
        f"- Mixed authority terms: `{', '.join(report['monolith']['mixed_authority_terms'])}`",
        "",
        "## Detector Split",
        "",
        f"- Path: `{report['detector_split']['path']}`",
        f"- Clean for detector authority: `{report['detector_split']['clean_for_detector_authority']}`",
        "",
        "## Strategy Split",
        "",
        f"- Path: `{report['strategy_split']['path']}`",
        f"- Strategy terms present: `{', '.join(report['strategy_split']['strategy_terms_present'])}`",
        "",
        "## Boundary",
        "",
        f"- Runtime source: `{report['runtime_config']['source']}`",
        f"- Runtime migrated to split contracts: `{report['runtime_config']['migrated_to_split_contracts']}`",
        "- No market edge, paper execution, or live execution authority is created by this split.",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit ontology/strategy authority split.")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = audit_authority_split()
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    output_md.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output_json": str(output_json.resolve())}, indent=2))


if __name__ == "__main__":
    main()
