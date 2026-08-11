from __future__ import annotations

import json
import subprocess

import pandas as pd
import pytest
import requests

from tools import run_live_ai_smc_full_system as live_runner
from tools.run_live_ai_smc_full_system import resample_ohlcv


def _hourly(periods: int) -> pd.DataFrame:
    timestamps = pd.date_range("2026-07-13 00:00", periods=periods, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + index for index in range(periods)],
            "high": [101.0 + index for index in range(periods)],
            "low": [99.0 + index for index in range(periods)],
            "close": [100.5 + index for index in range(periods)],
            "volume": [10.0] * periods,
        }
    )


def test_resample_excludes_forming_four_hour_bucket() -> None:
    # Closed source candles run through 10:00-11:00. The 08:00-12:00
    # four-hour bucket is still forming at the 11:00 decision cutoff.
    result = resample_ohlcv(_hourly(11), "4h", decision_time="2026-07-13T11:00:00Z")

    assert list(result["timestamp"]) == [
        pd.Timestamp("2026-07-13T00:00:00Z"),
        pd.Timestamp("2026-07-13T04:00:00Z"),
    ]


def test_resample_includes_bucket_closing_exactly_at_cutoff() -> None:
    result = resample_ohlcv(_hourly(12), "4h", decision_time="2026-07-13T12:00:00Z")

    assert pd.Timestamp("2026-07-13T08:00:00Z") in set(result["timestamp"])
    assert (pd.to_datetime(result["timestamp"]) + pd.Timedelta("4h") <= pd.Timestamp("2026-07-13T12:00:00Z")).all()


def test_http_json_uses_tls_verified_public_dns_fallback_only_after_resolution_failure(monkeypatch) -> None:
    live_runner.DNS_FALLBACK_AUDIT.clear()

    def fail_dns(*_args, **_kwargs):
        raise requests.ConnectionError("NameResolutionError: Failed to resolve fapi.binance.com")

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"serverTime": 123}), stderr="")

    monkeypatch.setattr(live_runner.requests, "get", fail_dns)
    monkeypatch.setattr(live_runner, "_resolve_public_ipv4", lambda _host: ("1.1.1.1", ["203.0.113.10"]))
    monkeypatch.setattr(live_runner.subprocess, "run", fake_run)

    payload = live_runner.http_get_json("https://fapi.binance.com/fapi/v1/time", {}, timeout=4)

    assert payload == {"serverTime": 123}
    command = captured["command"]
    assert "--resolve" in command
    assert "fapi.binance.com:443:203.0.113.10" in command
    assert "--insecure" not in command and "-k" not in command
    assert live_runner.DNS_FALLBACK_AUDIT[-1]["tls_hostname_verification"] is True


def test_http_json_does_not_mask_non_dns_connection_failures(monkeypatch) -> None:
    def fail_connection(*_args, **_kwargs):
        raise requests.ConnectionError("connection reset by peer")

    monkeypatch.setattr(live_runner.requests, "get", fail_connection)
    monkeypatch.setattr(
        live_runner,
        "_http_get_json_via_public_dns",
        lambda *_args, **_kwargs: pytest.fail("fallback must not run for non-DNS failure"),
    )

    with pytest.raises(requests.ConnectionError, match="connection reset"):
        live_runner.http_get_json("https://fapi.binance.com/fapi/v1/time", {})


def test_public_dns_resolution_is_restricted_to_approved_hosts() -> None:
    with pytest.raises(RuntimeError, match="not approved"):
        live_runner._resolve_public_ipv4("example.com")
