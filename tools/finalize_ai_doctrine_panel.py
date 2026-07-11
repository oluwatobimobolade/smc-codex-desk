#!/usr/bin/env python3
"""Validate all AI doctrine-role outputs and write a certification-pending result."""
from __future__ import annotations

import argparse
import json

from smc_desk.brain.doctrine_panel import finalize_doctrine_panel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", required=True, help="Directory exported by init_ai_perception_readiness.py")
    args = parser.parse_args()
    result = finalize_doctrine_panel(args.panel)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
