#!/usr/bin/env python3
"""Provision independent public keys and pin them to an interrogation cohort."""
from __future__ import annotations

import argparse
import json

from smc_desk.evaluation.trust_registry import provision_cohort_trust_registry


def _signer(value: str) -> dict[str, str]:
    parts = value.split(":", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("Signer must be SIGNER_ID:ROLE:PUBLIC_KEY_PATH")
    return {"signer_id": parts[0], "role": parts[1], "public_key_path": parts[2]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort_root")
    parser.add_argument("--signer", action="append", type=_signer, required=True)
    args = parser.parse_args()
    result = provision_cohort_trust_registry(args.cohort_root, args.signer)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
