#!/usr/bin/env python3
"""Audit SMC case folders and generate a case-library index."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.case_audit import audit_case_library, write_case_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit SMC case-library case.json files.")
    parser.add_argument("--root", default="case_library", help="Case library root folder.")
    parser.add_argument("--output-dir", help="Where to write index.json and index.md. Defaults to --root.")
    parser.add_argument("--print-summary", action="store_true", help="Print summary JSON after writing files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    output_dir = Path(args.output_dir) if args.output_dir else root
    paths = write_case_index(root, output_dir=output_dir)
    audit = audit_case_library(root)
    print(f"Wrote case-library index: {paths['index_md']}")
    print(f"Wrote case-library JSON: {paths['index_json']}")
    if args.print_summary:
        print(json.dumps(audit["summary"], indent=2))


if __name__ == "__main__":
    main()
