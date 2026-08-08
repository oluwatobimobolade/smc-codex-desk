#!/usr/bin/env python3
"""Sign or verify SMC evidence payloads with Ed25519/OpenSSL."""
from __future__ import annotations

import argparse
import json

from smc_desk.evaluation.evidence_signing import sign_evidence_payload, verify_evidence_envelope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    sign = subparsers.add_parser("sign")
    sign.add_argument("--payload", required=True)
    sign.add_argument("--envelope", required=True)
    sign.add_argument("--private-key", required=True)
    sign.add_argument("--evidence-type", required=True)
    sign.add_argument("--subject-id", required=True)
    sign.add_argument("--cohort-hash", required=True)
    sign.add_argument("--system-freeze-hash", required=True)
    sign.add_argument("--signer-id", required=True)
    sign.add_argument("--signer-role", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--envelope", required=True)
    verify.add_argument("--trust-registry", required=True)
    verify.add_argument("--allowed-role", action="append", required=True)
    verify.add_argument("--evidence-type", default=None)
    verify.add_argument("--subject-id", default=None)
    verify.add_argument("--cohort-hash", default=None)
    verify.add_argument("--system-freeze-hash", default=None)

    args = parser.parse_args()
    if args.command == "sign":
        result = sign_evidence_payload(
            payload_path=args.payload,
            envelope_path=args.envelope,
            private_key_path=args.private_key,
            evidence_type=args.evidence_type,
            subject_id=args.subject_id,
            cohort_content_sha256=args.cohort_hash,
            system_code_freeze_sha256=args.system_freeze_hash,
            signer_id=args.signer_id,
            signer_role=args.signer_role,
        )
    else:
        result = verify_evidence_envelope(
            args.envelope,
            trust_registry_path=args.trust_registry,
            allowed_roles=args.allowed_role,
            expected_evidence_type=args.evidence_type,
            expected_subject_id=args.subject_id,
            expected_cohort_content_sha256=args.cohort_hash,
            expected_system_code_freeze_sha256=args.system_freeze_hash,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status", "PASS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
