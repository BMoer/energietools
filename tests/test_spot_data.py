# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für den gebündelten EPEX-Spot-Snapshot-Loader (offline, fail-open)."""

from __future__ import annotations

from datetime import datetime

from energietools.capabilities.spot import data as spot_data
from energietools.capabilities.spot import load_epex_prices, load_spot_manifest


def test_snapshot_loads_nonempty() -> None:
    prices = load_epex_prices()
    assert len(prices) > 0
    first = prices[0]
    assert "timestamp" in first and "price_ct" in first
    # Timestamps sind ISO-parsebar
    datetime.fromisoformat(first["timestamp"])
    assert isinstance(first["price_ct"], (int, float))


def test_snapshot_is_immutable_tuple() -> None:
    assert isinstance(load_epex_prices(), tuple)


def test_manifest_has_provenance() -> None:
    manifest = load_spot_manifest()
    assert manifest.get("market") == "AT"
    assert "aWATTar" in manifest.get("provenance", "")
    assert manifest.get("price_count", 0) == len(load_epex_prices())


def test_read_data_fail_open_returns_none() -> None:
    # Fehlende Datei → None (fail-open), kein Crash.
    assert spot_data._read_data("does_not_exist.json") is None
