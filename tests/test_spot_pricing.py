# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für das Spot-Tarif-Pricing (EPEX + Aufschlag → effektiver Preis).

Spotpreise werden injiziert (kein Netzwerk), damit die Rechnung deterministisch ist.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from energietools.capabilities.tariffs.models import CatalogTariff
from energietools.tools.spot_pricing import (
    compute_monthly_floater_effective,
    compute_spot_breakdown,
    compute_spot_effective,
    effective_for_tariff,
)


def _flat_prices(ct: float, hours: int = 8760):
    start = datetime(2025, 1, 1, 0, 0)
    return [
        {"timestamp": (start + timedelta(hours=h)).isoformat(), "price_ct": ct}
        for h in range(hours)
    ]


def _cheap_night_prices(hours: int = 8760):
    """Nachts billig (5 ct), abends teuer (30 ct) — H0-Haushalt zahlt überdurchschnittlich."""
    start = datetime(2025, 1, 1, 0, 0)
    out = []
    for h in range(hours):
        ts = start + timedelta(hours=h)
        price = 30.0 if ts.hour in (18, 19, 20, 21) else (5.0 if ts.hour in (1, 2, 3, 4) else 12.0)
        out.append({"timestamp": ts.isoformat(), "price_ct": price})
    return out


def _spot_tariff(tariftyp: str, aufschlag: float) -> CatalogTariff:
    return CatalogTariff(
        key="x", lieferant="x", tarif_name="t", tariftyp=tariftyp, spot_aufschlag_ct=aufschlag,
    )


def test_flat_spot_effective_equals_spot_plus_markup() -> None:
    res = compute_spot_effective(3500.0, aufschlag_ct=1.5, spot_prices=_flat_prices(10.0))
    assert res["effektiver_arbeitspreis_netto_ct"] == pytest.approx(11.5, abs=0.05)


def test_household_profile_costs_more_than_flat() -> None:
    res = compute_spot_effective(3500.0, aufschlag_ct=1.5, spot_prices=_cheap_night_prices())
    assert res["avg_spot_volumengewichtet_ct"] > res["avg_spot_zeitgewichtet_ct"]
    assert res["profilkostenfaktor_pct"] > 0


def test_returns_jahreskosten_band() -> None:
    res = compute_spot_effective(3500.0, aufschlag_ct=1.5, spot_prices=_flat_prices(10.0))
    assert res["jahreskosten_energie_netto_eur"] == pytest.approx(402.5, rel=0.02)
    assert res["basis"] == "H0-Standardlastprofil"


def test_explicit_consumption_data_used_over_h0() -> None:
    spot = _cheap_night_prices()
    cons = [
        {"timestamp": datetime(2025, 1, 1, 2, 0).isoformat(), "kwh": 1.0},
        {"timestamp": datetime(2025, 1, 1, 3, 0).isoformat(), "kwh": 1.0},
    ]
    res = compute_spot_effective(2.0, aufschlag_ct=1.5, spot_prices=spot, consumption_data=cons)
    assert res["avg_spot_volumengewichtet_ct"] == pytest.approx(5.0, abs=0.1)
    assert res["basis"] == "eigene Verbrauchsdaten"


def test_empty_spot_prices_raises() -> None:
    with pytest.raises(ValueError):
        compute_spot_effective(3500.0, aufschlag_ct=1.5, spot_prices=[])


# --- Monatsfloater (monthly spot) -------------------------------------------


def test_monthly_floater_ignores_hour_of_day() -> None:
    res = compute_monthly_floater_effective(
        3500.0, aufschlag_ct=1.44, spot_prices=_cheap_night_prices(),
    )
    assert res["spot_typ"] == "monatsfloater"
    assert res["profilkostenfaktor_pct"] == pytest.approx(0.0, abs=0.5)


def test_monthly_effective_is_month_mean_plus_markup() -> None:
    res = compute_monthly_floater_effective(
        3500.0, aufschlag_ct=1.5, spot_prices=_flat_prices(10.0),
    )
    assert res["effektiver_arbeitspreis_netto_ct"] == pytest.approx(11.5, abs=0.05)


# --- Dispatcher nach tariftyp -----------------------------------------------


def test_dispatcher_routes_by_tariftyp() -> None:
    stunden = _spot_tariff("Stundenfloater", 1.5)
    monat = _spot_tariff("Monatsfloater", 1.44)

    spot = _cheap_night_prices()
    r_h = effective_for_tariff(stunden, 3500.0, spot)
    r_m = effective_for_tariff(monat, 3500.0, spot)

    assert r_h["spot_typ"] == "stundenfloater"
    assert r_m["spot_typ"] == "monatsfloater"
    assert r_h["profilkostenfaktor_pct"] > r_m["profilkostenfaktor_pct"]


# --- Mehrjahres-Breakdown (pro Jahr + Mittel) -------------------------------


def _year_flat(year: int, ct: float):
    start = datetime(year, 1, 1, 0, 0)
    return [
        {"timestamp": (start + timedelta(hours=h)).isoformat(), "price_ct": ct}
        for h in range(8760)
    ]


def test_breakdown_per_year_and_mean() -> None:
    t = _spot_tariff("Stundenfloater", 1.5)
    prices = _year_flat(2024, 10.0) + _year_flat(2025, 20.0)
    res = compute_spot_breakdown(t, 3500.0, prices)

    jahre = {j["jahr"]: j for j in res["jahre"]}
    assert set(jahre) == {2024, 2025}
    assert jahre[2024]["effektiver_arbeitspreis_netto_ct"] == pytest.approx(11.5, abs=0.05)
    assert jahre[2025]["effektiver_arbeitspreis_netto_ct"] == pytest.approx(21.5, abs=0.05)
    assert res["mittel_arbeitspreis_netto_ct"] == pytest.approx(16.5, abs=0.05)
