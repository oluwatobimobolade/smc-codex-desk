"""Canonical command surface for SMC Codex Desk.

WP-0043 (GATE-CANONICAL-RUNTIME-001).

Run with::

    python -m smc_desk.colleague --help

This shim exists so the canonical command does not require ``PYTHONPATH=.``.
It dispatches to ``smc_desk.colleague.orchestrator_v3`` and refuses to run if
the authority-boundary check fails (see ``tools/check_authority_boundaries.py``).

The shim never imports the legacy engine, the legacy rules module, or
``smc_desk.colleague.orchestrator`` (v1) / ``orchestrator_v2``. If you find
yourself adding such an import here, that is the wrong fix — route through
``smc_desk/colleague/legacy_comparison.py`` instead.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

# v3 is the canonical authority. We import it lazily inside main() so that
# accidental circular imports do not poison the boundary check.
_IMPORT_ERROR: Exception | None = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _repo_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(_project_root()), "rev-parse", "HEAD"],
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        return "unknown"


def _module_versions() -> dict[str, str]:
    """Return the import-graph fingerprint for this run."""
    versions: dict[str, str] = {}
    for name in (
        "smc_desk",
        "smc_desk.colleague",
        "smc_desk.colleague.orchestrator_v3",
        "smc_desk.brain",
        "smc_desk.brain.ai_smc_trader_brain",
        "smc_desk.brain.ai_smc_consistency_validator",
        "smc_desk.brain.annotation_plan_validator",
        "smc_desk.brain.annotation_visual_critic",
        "smc_desk.perception",
        "smc_desk.perception.engine_v2",
        "smc_desk.perception.formal_structure_graph",
    ):
        try:
            mod = __import__(name, fromlist=["__name__"])
            versions[name] = getattr(mod, "__file__", "<unknown>")
        except Exception as exc:  # noqa: BLE001
            versions[name] = f"<import-error: {exc.__class__.__name__}>"
    return versions


def build_authority_trace(
    *,
    command_line: Sequence[str],
    output_root: Path,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return the contents of an authority_trace.json file (WP-0043).

    Captures: command line, repo head, environment fingerprint, the imported
    module graph, the boundary-check decision, and any extra fields supplied by
    the orchestrator (e.g. dataset hash, prompt hash).
    """
    trace: dict[str, object] = {
        "schema": "smc_codex_desk_authority_trace_v1",
        "wp": "WP-0043",
        "gate": "GATE-CANONICAL-RUNTIME-001",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "command_line": list(command_line),
        "repo_head": _repo_head(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "module_versions": _module_versions(),
        "canonical_authority": "smc_desk.colleague.orchestrator_v3",
        "live_execution": "disabled",
        "paper_execution": "disabled",
        "predictive_authority": "not_certified",
    }
    if extra:
        trace.update(extra)
    return trace


def write_authority_trace(
    path: Path, trace: dict[str, object]
) -> dict[str, str]:
    """Write an authority_trace.json and return the file's hash pair."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(trace, indent=2, sort_keys=True, default=str)
    path.write_text(body, encoding="utf-8")
    return {
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "size": str(len(body)),
    }


def _run_boundary_check() -> int:
    """Run the authority-boundary checker as a pre-flight gate.

    Returns 0 on pass, non-zero on fail. Never silent.
    """
    tools_dir = _project_root() / "tools"
    script = tools_dir / "check_authority_boundaries.py"
    if not script.exists():
        print("AUTHORITY TRACE: boundary-check script missing; treating as fail.")
        return 2
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(_project_root()),
        capture_output=True,
        text=True,
        timeout=60,
    )
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m smc_desk.colleague",
        description="Canonical command surface for SMC Codex Desk (WP-0043).",
    )
    parser.add_argument(
        "--output-root",
        default="analysis_runs",
        help="Where to write run artefacts (default: analysis_runs).",
    )
    parser.add_argument(
        "--skip-boundary-check",
        action="store_true",
        help=(
            "Skip the pre-flight authority-boundary check. "
            "Use only for diagnostic runs; never for canonical-authority runs."
        ),
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "Run an authority-trace smoke: emit authority_trace.json + summary "
            "without invoking the orchestrator. Useful for CI smoke."
        ),
    )
    args = parser.parse_args(argv)

    if not args.skip_boundary_check:
        rc = _run_boundary_check()
        if rc != 0:
            print("REFUSED: authority boundary check failed; canonical run aborted.")
            return rc

    if args.smoke:
        out_root = Path(args.output_root).expanduser().resolve() / "_authority_smoke"
        out_root.mkdir(parents=True, exist_ok=True)
        trace = build_authority_trace(
            command_line=argv if argv is not None else sys.argv[1:],
            output_root=out_root,
            extra={"mode": "smoke"},
        )
        info = write_authority_trace(out_root / "authority_trace.json", trace)
        print(f"Authority trace written: {out_root / 'authority_trace.json'}")
        print(f"  sha256={info['sha256']}  bytes={info['size']}")
        return 0

    # Lazy import so the boundary check sees a clean module graph.
    try:
        from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"REFUSED: could not import canonical orchestrator v3: {exc}")
        return 1

    # The v3 entry point needs richer arguments than a CLI smoke. For
    # WP-0043, we only require that the canonical command surface exists and
    # the boundary check runs. Full CLI mapping lands in WP-0047 once the
    # release manifests are wired.
    print(
        "Canonical command surface loaded. "
        "Full run mapping is added by WP-0047 (release separation). "
        "For now, use tools/run_live_ai_smc_full_system.py for live runs."
    )
    trace = build_authority_trace(
        command_line=argv if argv is not None else sys.argv[1:],
        output_root=Path(args.output_root),
        extra={"mode": "no_full_run_yet"},
    )
    write_authority_trace(
        Path(args.output_root).expanduser().resolve() / "authority_trace.json",
        trace,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())