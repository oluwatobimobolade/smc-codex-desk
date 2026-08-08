# Ontology Authority Split WP-0015 Report

WP-0015 created clean target contracts for perception detector configuration
and strategy execution configuration, plus an audit guard.

- Detector split: `specs/PERCEPTION_DETECTOR_CONFIG_V2.yaml`
- Strategy split: `specs/STRATEGY_EXECUTION_CONFIG_V1.yaml`
- Split manifest: `specs/AUTHORITY_CONFIG_SPLIT_WP0015.yaml`
- Audit JSON: `reports/current/ONTOLOGY_AUTHORITY_AUDIT_WP0015.json`
- Audit status: `split_contract_ready_code_migration_pending`

The current runtime monolith still contains strategy/risk terms, so runtime
migration remains blocked until a separate, tested config model is introduced.
