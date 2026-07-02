# WP-0015 Ontology Authority Split - Final Report

Date: 2026-06-26

## Objective

Stop pretending the monolithic perception ontology is clean. Create split
authority contracts and an audit guard without breaking runtime compatibility.

## Implementation

- Added `specs/PERCEPTION_DETECTOR_CONFIG_V2.yaml`.
- Added `specs/STRATEGY_EXECUTION_CONFIG_V1.yaml`.
- Added `specs/AUTHORITY_CONFIG_SPLIT_WP0015.yaml`.
- Added `tools/audit_ontology_authority.py`.
- Added tests proving:
  - the current monolith still contains mixed strategy/risk fields;
  - the detector split is clean;
  - promotion remains blocked until runtime config migration and validation.

## Audit Result

Output:

- `reports/current/ONTOLOGY_AUTHORITY_AUDIT_WP0015.json`
- `reports/current/ONTOLOGY_AUTHORITY_AUDIT_WP0015.md`

Status:

- `split_contract_ready_code_migration_pending`

## Honest Interpretation

WP-0015 creates the split contract and guard. It does not migrate runtime config
yet. `RuleConfig` still loads `PERCEPTION_ONTOLOGY_V2.yaml` for backward
compatibility.

## Next Required Migration

- Introduce separate runtime config models.
- Keep a compatibility adapter for old rule files.
- Prove full test suite before switching the default runtime source.
