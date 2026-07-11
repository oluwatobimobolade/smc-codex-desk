"""Protected benchmark partitions and append-only access controls (BR-004)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from smc_desk.data.hashing import file_sha256, object_sha256


PartitionName = Literal[
    "doctrine_examples",
    "development_cases",
    "blind_validation_cases",
    "annotation_comprehension_cases",
]

REQUIRED_PARTITIONS = (
    "doctrine_examples",
    "development_cases",
    "blind_validation_cases",
    "annotation_comprehension_cases",
)
BLIND_PROHIBITED_ACTIONS = {
    "training",
    "tuning",
    "prompt_development",
    "case_generation",
    "case_memory_retrieval",
    "exploratory_analysis",
}


class BenchmarkCaseReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    partition: PartitionName
    symbol: str
    decision_start: str
    decision_end: str
    content_commitment_sha256: str = Field(min_length=64, max_length=64)
    chart_sha256: list[str] = Field(default_factory=list)
    case_memory_key: str | None = None
    public_metadata_only: bool = True

    @model_validator(mode="after")
    def validate_interval(self) -> "BenchmarkCaseReference":
        start = _timestamp(self.decision_start)
        end = _timestamp(self.decision_end)
        if end < start:
            raise ValueError("decision_end must be at or after decision_start")
        if self.partition == "blind_validation_cases" and not self.public_metadata_only:
            raise ValueError("Blind public manifests may contain commitments only.")
        return self


class BenchmarkPartition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: PartitionName
    status: Literal["READY", "UNPOPULATED", "LOCKED", "OPENED_FOR_FINAL_EVALUATION"]
    cases: list[BenchmarkCaseReference] = Field(default_factory=list)
    truth_status: Literal["NO_LABELS", "AI_WEAK_LABELS", "HUMAN_ADJUDICATED"] = "NO_LABELS"


class BenchmarkRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)
    schema_id: Literal["protected_benchmark_registry_v1"] = Field("protected_benchmark_registry_v1", alias="schema")
    registry_id: str
    partitions: dict[str, BenchmarkPartition]
    blind_storage_root: str | None = None
    access_ledger: str
    no_overlap_required: bool = True
    case_memory_exclusion_required: bool = True


def validate_benchmark_registry(registry: BenchmarkRegistry | dict[str, Any]) -> dict[str, Any]:
    model = registry if isinstance(registry, BenchmarkRegistry) else BenchmarkRegistry.model_validate(registry)
    issues: list[dict[str, Any]] = []
    missing = [name for name in REQUIRED_PARTITIONS if name not in model.partitions]
    if missing:
        issues.append({"code": "missing_partition", "partitions": missing})

    all_cases: list[BenchmarkCaseReference] = []
    for key, partition in model.partitions.items():
        if partition.name != key:
            issues.append({"code": "partition_name_mismatch", "key": key, "name": partition.name})
        all_cases.extend(partition.cases)

    case_ids: dict[str, str] = {}
    chart_hashes: dict[str, tuple[str, str]] = {}
    for case in all_cases:
        if case.case_id in case_ids:
            issues.append(
                {
                    "code": "duplicate_case_id",
                    "case_id": case.case_id,
                    "partitions": [case_ids[case.case_id], case.partition],
                }
            )
        case_ids[case.case_id] = case.partition
        for chart_hash in case.chart_sha256:
            if chart_hash in chart_hashes:
                prior_case, prior_partition = chart_hashes[chart_hash]
                issues.append(
                    {
                        "code": "duplicate_chart_across_partitions",
                        "sha256": chart_hash,
                        "cases": [prior_case, case.case_id],
                        "partitions": [prior_partition, case.partition],
                    }
                )
            chart_hashes[chart_hash] = (case.case_id, case.partition)

    development = model.partitions.get("development_cases")
    blind = model.partitions.get("blind_validation_cases")
    annotation = model.partitions.get("annotation_comprehension_cases")
    if development and blind:
        issues.extend(_interval_overlap_issues(development.cases, blind.cases, "development_blind_overlap"))
    if annotation and development:
        issues.extend(_interval_overlap_issues(annotation.cases, development.cases, "annotation_development_overlap"))
    if blind:
        for case in blind.cases:
            if case.case_memory_key:
                issues.append(
                    {
                        "code": "blind_case_memory_key_exposed",
                        "case_id": case.case_id,
                    }
                )

    return {
        "schema": "protected_benchmark_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "partition_counts": {
            name: len(partition.cases) for name, partition in model.partitions.items()
        },
        "blind_populated": bool(blind and blind.cases),
        "registry_sha256": object_sha256(model.model_dump(mode="json", by_alias=True)),
    }


def build_freeze_manifest(
    *,
    registry: BenchmarkRegistry,
    source_manifest_sha256: str,
    prompt_manifest_sha256: str,
    doctrine_manifest_sha256: str,
    provider_name: str,
    model_name: str,
) -> dict[str, Any]:
    validation = validate_benchmark_registry(registry)
    if validation["status"] != "PASS":
        raise ValueError("Cannot freeze an invalid benchmark registry.")
    payload = {
        "schema": "perception_benchmark_freeze_v1",
        "registry_id": registry.registry_id,
        "registry_sha256": validation["registry_sha256"],
        "source_manifest_sha256": source_manifest_sha256,
        "prompt_manifest_sha256": prompt_manifest_sha256,
        "doctrine_manifest_sha256": doctrine_manifest_sha256,
        "provider_name": provider_name,
        "model_name": model_name,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "blind_cases_may_open_only_for": "final_evaluation",
        "paper_execution": "disabled",
        "live_execution": "disabled",
    }
    payload["freeze_id"] = object_sha256(payload)
    return payload


class ProtectedBenchmarkStore:
    """Filesystem guard for blind data with a hash-chained access ledger."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.public_root = self.root / "public"
        self.private_root = self.root / "private_blind"
        self.ledger_path = self.root / "access_ledger.jsonl"
        self.public_root.mkdir(parents=True, exist_ok=True)
        self.private_root.mkdir(parents=True, exist_ok=True)

    def register(self, registry: BenchmarkRegistry) -> Path:
        validation = validate_benchmark_registry(registry)
        if validation["status"] != "PASS":
            raise ValueError(f"Invalid benchmark registry: {validation['issues']}")
        path = self.public_root / "benchmark_registry.json"
        _write_json(path, registry.model_dump(mode="json", by_alias=True))
        self._log("register_registry", "system", {"registry_sha256": validation["registry_sha256"]})
        return path

    def save_freeze(self, freeze: dict[str, Any]) -> Path:
        path = self.public_root / "freeze_manifest.json"
        _write_json(path, freeze)
        self._log("freeze", "system", {"freeze_id": freeze["freeze_id"]})
        return path

    def read_blind_case(
        self,
        case_id: str,
        *,
        actor: str,
        action: str,
        freeze_id: str,
    ) -> dict[str, Any]:
        normalized_action = action.strip().lower()
        freeze_path = self.public_root / "freeze_manifest.json"
        if normalized_action in BLIND_PROHIBITED_ACTIONS:
            self._log("blind_access_refused", actor, {"case_id": case_id, "action": normalized_action})
            raise PermissionError(f"Blind benchmark access forbidden for action: {normalized_action}")
        if normalized_action != "final_evaluation":
            self._log("blind_access_refused", actor, {"case_id": case_id, "action": normalized_action})
            raise PermissionError("Blind cases may open only for final_evaluation.")
        if not freeze_path.exists():
            raise PermissionError("Prompt/code/model/doctrine freeze must exist before blind access.")
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        if freeze.get("freeze_id") != freeze_id:
            raise PermissionError("freeze_id does not match the locked experiment.")
        path = self.private_root / case_id / "case.json"
        if not path.exists():
            raise FileNotFoundError(f"Blind case is not populated: {case_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._log(
            "blind_access_granted",
            actor,
            {"case_id": case_id, "action": normalized_action, "freeze_id": freeze_id, "case_sha256": file_sha256(path)},
        )
        return payload

    def _log(self, event: str, actor: str, detail: dict[str, Any]) -> None:
        previous_hash = "0" * 64
        if self.ledger_path.exists():
            lines = [line for line in self.ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if lines:
                previous_hash = json.loads(lines[-1])["entry_sha256"]
        entry = {
            "schema": "benchmark_access_ledger_entry_v1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "actor": actor,
            "detail": detail,
            "previous_entry_sha256": previous_hash,
        }
        entry["entry_sha256"] = object_sha256(entry)
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


def build_unpopulated_registry(root: str | Path) -> BenchmarkRegistry:
    return BenchmarkRegistry(
        registry_id="PERCEPTION_BENCHMARK_REGISTRY_V1",
        partitions={
            name: BenchmarkPartition(
                name=name,
                status="UNPOPULATED" if name == "blind_validation_cases" else "READY",
                cases=[],
                truth_status="NO_LABELS",
            )
            for name in REQUIRED_PARTITIONS
        },
        blind_storage_root=str((Path(root).expanduser().resolve() / "private_blind")),
        access_ledger=str((Path(root).expanduser().resolve() / "access_ledger.jsonl")),
    )


def build_public_case_reference_from_evidence_pack(
    evidence_pack_path: str | Path,
    *,
    partition: Literal["development_cases", "annotation_comprehension_cases"],
    context_hours: int = 24,
) -> BenchmarkCaseReference:
    """Commit one non-blind replay pack to a public benchmark partition.

    The pack itself remains a normal local research artefact.  The registry
    stores only its immutable hash, chart hashes, symbol, and bounded decision
    interval, keeping the blind-set contract separate from routine AI work.
    """
    if context_hours < 1:
        raise ValueError("context_hours must be at least one hour.")
    path = Path(evidence_pack_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    graph = payload.get("formal_structure_graph") or {}
    symbol = str(payload.get("symbol") or "").strip().upper()
    decision_time = graph.get("decision_time")
    if not symbol or not decision_time:
        raise ValueError("Evidence pack requires symbol and formal graph decision_time.")
    end = _timestamp(decision_time)
    start = end - pd.Timedelta(hours=context_hours)
    chart_hashes = sorted(
        {
            str(item.get("sha256"))
            for item in (payload.get("chart_images") or {}).values()
            if isinstance(item, dict) and item.get("sha256")
        }
    )
    if not chart_hashes:
        raise ValueError("Evidence pack has no chart sha256 commitments.")
    pack_sha256 = file_sha256(path)
    time_token = end.strftime("%Y%m%dT%H%M%SZ")
    return BenchmarkCaseReference(
        case_id=f"{partition}:{symbol}:{time_token}:{pack_sha256[:12]}",
        partition=partition,
        symbol=symbol,
        decision_start=start.isoformat().replace("+00:00", "Z"),
        decision_end=end.isoformat().replace("+00:00", "Z"),
        content_commitment_sha256=pack_sha256,
        chart_sha256=chart_hashes,
        case_memory_key=f"public:{partition}:{pack_sha256[:16]}",
        public_metadata_only=True,
    )


def build_public_benchmark_pilot(
    root: str | Path,
    *,
    development_evidence_pack: str | Path,
    annotation_evidence_pack: str | Path,
    context_hours: int = 24,
) -> BenchmarkRegistry:
    """Build the first usable public partitions while leaving blind validation empty.

    This intentionally does not populate ``private_blind``.  It gives AI
    research a reproducible development and annotation surface without
    weakening the future out-of-sample evaluation boundary.
    """
    registry = build_unpopulated_registry(root)
    development = build_public_case_reference_from_evidence_pack(
        development_evidence_pack,
        partition="development_cases",
        context_hours=context_hours,
    )
    annotation = build_public_case_reference_from_evidence_pack(
        annotation_evidence_pack,
        partition="annotation_comprehension_cases",
        context_hours=context_hours,
    )
    registry.partitions["development_cases"] = BenchmarkPartition(
        name="development_cases",
        status="READY",
        cases=[development],
        truth_status="AI_WEAK_LABELS",
    )
    registry.partitions["annotation_comprehension_cases"] = BenchmarkPartition(
        name="annotation_comprehension_cases",
        status="READY",
        cases=[annotation],
        truth_status="AI_WEAK_LABELS",
    )
    validation = validate_benchmark_registry(registry)
    if validation["status"] != "PASS":
        raise ValueError(f"Public benchmark pilot is invalid: {validation['issues']}")
    return registry


def _interval_overlap_issues(
    left: list[BenchmarkCaseReference],
    right: list[BenchmarkCaseReference],
    code: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for a in left:
        for b in right:
            if _symbol(a.symbol) != _symbol(b.symbol):
                continue
            if _timestamp(a.decision_start) <= _timestamp(b.decision_end) and _timestamp(a.decision_end) >= _timestamp(b.decision_start):
                issues.append({"code": code, "cases": [a.case_id, b.case_id], "symbol": _symbol(a.symbol)})
    return issues


def _timestamp(value: Any) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _symbol(value: str) -> str:
    return value.upper().replace("/", "").replace("-", "")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
