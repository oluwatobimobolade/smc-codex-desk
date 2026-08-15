"""Fail-closed market-source identity checks.

Price geometry is not portable between instruments.  A related futures,
token, CFD, or index series may be useful diagnostic context, but it cannot be
treated as candle authority for the requested market unless that substitution
is explicitly modelled and validated elsewhere.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


def assess_source_identity(
    requested_symbol: str,
    source_manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Certify that a source manifest describes the requested instrument.

    Missing manifests remain ``UNVERIFIED`` for backwards-compatible offline
    research.  Explicit proxies and contradictory symbols fail closed.
    """
    manifest = source_manifest if isinstance(source_manifest, Mapping) else {}
    requested = _canonical_symbol(requested_symbol)
    declared_raw = str(manifest.get("symbol") or "")
    provider_raw = str(manifest.get("provider_symbol") or "")
    market_type = str(manifest.get("market_type") or "")
    proxy_note = str(manifest.get("proxy_note") or "")
    declared = _canonical_symbol(declared_raw)
    provider = _canonical_symbol(provider_raw)

    explicit_proxy = bool(proxy_note.strip()) or bool(manifest.get("is_proxy")) or bool(
        re.search(r"\b(?:futures?|token|index|cfd)\s+proxy\b", market_type, flags=re.IGNORECASE)
    )
    failures: list[str] = []
    if explicit_proxy:
        failures.append(
            f"explicit proxy cannot certify requested instrument: provider={provider_raw or 'unspecified'}, "
            f"requested={requested_symbol}"
        )
    if declared and declared != requested:
        failures.append(f"manifest symbol {declared_raw} does not match requested symbol {requested_symbol}")
    if provider and provider != requested and not explicit_proxy:
        failures.append(f"provider symbol {provider_raw} does not match requested symbol {requested_symbol}")

    if failures:
        status = "MISMATCH_PROXY" if explicit_proxy else "MISMATCH"
    elif not manifest:
        status = "UNVERIFIED"
    elif not declared and not provider:
        status = "UNVERIFIED"
    else:
        status = "VERIFIED"

    return {
        "schema": "market_source_identity_certificate_v1",
        "requested_symbol": requested_symbol,
        "requested_symbol_canonical": requested,
        "manifest_symbol": declared_raw or None,
        "provider_symbol": provider_raw or None,
        "provider_symbol_canonical": provider or None,
        "market_type": market_type or None,
        "explicit_proxy": explicit_proxy,
        "status": status,
        "failures": failures,
        "candle_authority_allowed": status in {"VERIFIED", "UNVERIFIED"},
        "trade_promotion_allowed": status == "VERIFIED",
        "policy": (
            "Related-market proxies may be retained for diagnostics but cannot create structure, POI, "
            "entry, stop, target, or annotated-chart authority for another instrument."
        ),
    }


def _canonical_symbol(value: str) -> str:
    raw = str(value or "").strip().upper()
    if ":" in raw:
        raw = raw.rsplit(":", 1)[-1]
    for suffix in ("=X", ".P"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
    return re.sub(r"[^A-Z0-9]", "", raw)


__all__ = ["assess_source_identity"]
