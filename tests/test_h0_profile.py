# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für den H0-Standardlastprofil-Synthesizer."""

from __future__ import annotations

from datetime import datetime

import pytest

from energietools.tools.h0_profile import synthesize_h0_consumption


def _one_year():
    return datetime(2025, 1, 1, 0, 0), datetime(2026, 1, 1, 0, 0)


def test_sum_equals_annual_kwh() -> None:
    start, end = _one_year()
    pts = synthesize_h0_consumption(3500.0, start, end)
    total = sum(p["kwh"] for p in pts)
    assert total == pytest.approx(3500.0, rel=1e-6)


def test_hourly_resolution() -> None:
    start, end = _one_year()
    pts = synthesize_h0_consumption(3500.0, start, end)
    # 2025 = 365 Tage × 24 h = 8760 Punkte
    assert len(pts) == 8760


def test_evening_higher_than_night() -> None:
    start, end = _one_year()
    pts = synthesize_h0_consumption(3500.0, start, end)

    def hours_sum(hours):
        return sum(p["kwh"] for p in pts if datetime.fromisoformat(p["timestamp"]).hour in hours)

    assert hours_sum((18, 19, 20)) > hours_sum((2, 3, 4)) * 1.5


def test_timestamps_iso_and_sorted() -> None:
    start, end = _one_year()
    pts = synthesize_h0_consumption(1000.0, start, end)
    ts = [datetime.fromisoformat(p["timestamp"]) for p in pts]
    assert ts == sorted(ts)
    assert all(p["kwh"] > 0 for p in pts)


def test_zero_consumption_raises() -> None:
    start, end = _one_year()
    with pytest.raises(ValueError):
        synthesize_h0_consumption(0.0, start, end)
