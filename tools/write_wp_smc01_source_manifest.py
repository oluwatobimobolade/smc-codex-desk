"""Write the WP-SMC-01 source manifest for the exact current repository state."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path


DEFAULT_OUTPUT = Path(
    "governance/WORK_PACKAGES/WP-SMC-01-VERIFIED-REPOSITORY-TRUTH/"
    "BASELINE_SOURCE_MANIFEST.tsv"
)
INCLUDED_SUFFIXES = {
    ".json",
    ".lock",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}
EXCLUDED_PREFIXES = (
    ".git/",
    ".venv/",
    "analysis_runs/",
    "backtests/",
    "case_library/",
    "data/",
    "evidence/",
    "foundation_programme/",
    "governance/",
    "reports/",
)


def _git_paths(root: Path, *args: str) -> set[str]:
    output = subprocess.check_output(["git", *args], cwd=root, text=True)
    return {line for line in output.splitlines() if line}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(root: Path, output: Path) -> int:
    tracked = _git_paths(root, "ls-files")
    untracked = _git_paths(root, "ls-files", "--others", "--exclude-standard")
    output_rel = output.relative_to(root).as_posix()
    output_dir_rel = output.parent.relative_to(root).as_posix().rstrip("/") + "/"
    rows: list[tuple[str, str, int, str]] = []
    for rel in sorted(tracked | untracked):
        path = root / rel
        if rel == output_rel or rel.startswith(output_dir_rel) or not path.is_file():
            continue
        if rel.startswith(EXCLUDED_PREFIXES) or path.suffix.lower() not in INCLUDED_SUFFIXES:
            continue
        state = "tracked" if rel in tracked else "untracked"
        rows.append((state, _sha256(path), path.stat().st_size, rel))
    output.parent.mkdir(parents=True, exist_ok=True)
    body = ["state\tsha256\tsize_bytes\tpath"]
    body.extend(f"{state}\t{digest}\t{size}\t{rel}" for state, digest, size, rel in rows)
    output.write_text("\n".join(body) + "\n", encoding="utf-8")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1], type=Path)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    count = write_manifest(root, output)
    print(f"Wrote {count} source records to {output}")


if __name__ == "__main__":
    main()
