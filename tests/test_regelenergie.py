# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
"""Regelenergie — Golden-Tests (Balancing-Summary) + FCR-Kapazitäts-Erlös."""

from datetime import datetime

import pytest

from energietools.tools.regelenergie import (
    reserve_capacity_revenue,
    summarise_balancing_prices,
)

TS = [
    datetime(2025, 3, 1, 0), datetime(2025, 3, 1, 4),
    datetime(2025, 3, 2, 0), datetime(2025, 3, 2, 4),
    datetime(2025, 3, 3, 0),
]
PRICES = [12.0, 80.0, 5.0, 120.0, 40.0]


def test_summary_matches_pvtool():
    s = summarise_balancing_prices(PRICES, TS)
    assert s == {
        "days": 3, "count": 5, "mean_eur_mwh": 51.4, "median_eur_mwh": 40.0,
        "min_eur_mwh": 5.0, "max_eur_mwh": 120.0, "std_eur_mwh": 48.37,
    }


def test_summary_empty():
    assert summarise_balancing_prices([], []) == {"days": 0, "count": 0}


def test_summary_length_mismatch():
    with pytest.raises(ValueError, match="gleich lang"):
        summarise_balancing_prices([1.0, 2.0], TS)


def test_fcr_capacity_revenue():
    # 10 kWh-Speicher, c_rate 0.5 → 5 kW; FCR 80 EUR/kW/Jahr, Verfügbarkeit 0,85
    assert reserve_capacity_revenue(5.0, 80.0, 0.85) == pytest.approx(340.0)
    assert reserve_capacity_revenue(0.0, 80.0) == 0.0


def test_fcr_revenue_validation():
    with pytest.raises(ValueError, match="availability"):
        reserve_capacity_revenue(5.0, 80.0, availability=1.5)
    with pytest.raises(ValueError, match="negativ"):
        reserve_capacity_revenue(-1.0, 80.0)
