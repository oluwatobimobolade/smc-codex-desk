"""Prompt module contract for the AI SMC trader brain."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptModule:
    name: str
    version: str
    purpose: str
    text: str
    required_output_schema: str = "ai_smc_trader_decision_v1"

    @property
    def hash(self) -> str:
        payload = "\n".join(
            [
                self.name,
                self.version,
                self.purpose,
                self.required_output_schema,
                self.text,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "version": self.version,
            "purpose": self.purpose,
            "hash": self.hash,
            "required_output_schema": self.required_output_schema,
        }
        if include_text:
            payload["text"] = self.text
        return payload
