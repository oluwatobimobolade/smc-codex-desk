from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class AnalysisPackageWriter:
    root: Path
    files: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, relative: str) -> Path:
        return self.root / relative

    def write_json(self, relative: str, payload: Any) -> Path:
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        self.files[relative] = {"path": str(path.resolve()), "sha256": file_sha256(path)}
        return path

    def write_text(self, relative: str, text: str) -> Path:
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.files[relative] = {"path": str(path.resolve()), "sha256": file_sha256(path)}
        return path

    def write_csv(self, relative: str, df: pd.DataFrame) -> Path:
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        self.files[relative] = {"path": str(path.resolve()), "sha256": file_sha256(path), "rows": int(len(df))}
        return path

    def register_existing(self, relative: str, path: Path) -> None:
        self.files[relative] = {"path": str(path.resolve()), "sha256": file_sha256(path)}

    def build_manifest_file_index(self) -> dict[str, dict[str, Any]]:
        return dict(sorted(self.files.items()))
