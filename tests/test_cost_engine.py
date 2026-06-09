# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Unified Cost Engine.

Eine Rechenlogik für Fix / Monatsfloater / Spot — nur die Arbeitspreis-Zeitreihe
unterscheidet sich. ``build_price_at`` ist modellfrei (Primitiven); Spotpreise
werden injiziert (kein Netzwerk).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from energietools.tools.cost_engine import build_price_at, compute_annual_cost
from energietools.tools.h0_profile import synthesize_h0_consumption


def _year_cons(annual_kwh=3500.0):
    return synthesize_h0_consumption(annual_kwh, datetime(2025, 1, 1), datetime(2026, 1, 1))


def _flat_epex(ct=10.0):
    start = datetime(2025, 1, 1)
    return [
        {"timestamp": (start + timedelta(hours=h)).isoformat(), "price_ct": ct}
        for h in range(8760)
    ]


# --- compute_annual_cost (der gemeinsame Kern) ------------------------------


def test_constant_price_energy_cost() -> None:
    cons = _year_cons(3500.0)
    res = compute_annual_cost(cons, lambda ts: 10.0, grundpreis_eur_monat=4.79)
    assert res["energie_netto_eur"] == pytest.approx(350.0, rel=1e-4)
    assert res["grund_netto_eur"] == pytest.approx(57.48, rel=1e-4)
    assert res["netto_gesamt_eur"] == pytest.approx(407.48, rel=1e-4)


def test_brutto_applies_ust_and_gab() -> None:
    cons = _year_cons(3500.0)
    res = compute_annual_cost(
        cons, lambda ts: 10.0, grundpreis_eur_monat=0.0, gab_rate=0.07,
    )
    assert res["brutto_gesamt_eur"] == pytest.approx(350.0 * 1.07 * 1.20, rel=1e-3)


def test_per_kwh_year1_discount() -> None:
    cons = _year_cons(3500.0)
    res = compute_annual_cost(
        cons, lambda ts: 12.0, grundpreis_eur_monat=0.0, discount_ct_kwh_jahr1=2.0,
    )
    assert res["rabatt_jahr1_eur"] == pytest.approx(70.0, rel=1e-3)
    assert res["brutto_jahr1_eur"] < res["brutto_gesamt_eur"]


def test_skips_unpriced_hours() -> None:
    cons = _year_cons(3500.0)
    res = compute_annual_cost(
        cons, lambda ts: 10.0 if ts.hour % 2 == 0 else None, grundpreis_eur_monat=0.0,
    )
    assert res["matched_kwh"] < 3500.0


# --- build_price_at: eine Preisreihe je Tarifart (modellfrei) ---------------


def test_fix_price_series_is_constant() -> None:
    price_at = build_price_at(
        tariftyp="Fixpreis", energiepreis_ct_kwh=11.5, epex_prices=_flat_epex(10.0),
    )
    assert price_at(datetime(2025, 6, 1, 3)) == pytest.approx(11.5)
    assert price_at(datetime(2025, 12, 24, 19)) == pytest.approx(11.5)


def test_spot_price_series_is_epex_plus_markup() -> None:
    price_at = build_price_at(
        tariftyp="Stundenfloater", spot_aufschlag_ct=1.5, epex_prices=_flat_epex(10.0),
    )
    assert price_at(datetime(2025, 3, 15, 8)) == pytest.approx(11.5)


def test_monthly_price_series_uses_month_mean() -> None:
    price_at = build_price_at(
        tariftyp="Monatsfloater", spot_aufschlag_ct=1.44, epex_prices=_flat_epex(10.0),
    )
    assert price_at(datetime(2025, 1, 5, 2)) == pytest.approx(11.44)
    assert price_at(datetime(2025, 1, 28, 20)) == pytest.approx(11.44)


def test_all_three_types_run_through_same_engine() -> None:
    cons = _year_cons(3500.0)
    epex = _flat_epex(10.0)

    def cost(tariftyp, **kw):
        price_at = build_price_at(tariftyp=tariftyp, epex_prices=epex, **kw)
        return compute_annual_cost(cons, price_at, grundpreis_eur_monat=4.79)["netto_gesamt_eur"]

    costs = {
        "fix": cost("Fixpreis", energiepreis_ct_kwh=11.5),
        "spot": cost("Stundenfloater", spot_aufschlag_ct=1.5),
        "monat": cost("Monatsfloater", spot_aufschlag_ct=1.5),
    }
    # Bei flachem EPEX 10 + Aufschlag 1,5 = 11,5 → alle drei identisch
    assert costs["fix"] == pytest.approx(costs["spot"], rel=1e-4)
    assert costs["fix"] == pytest.approx(costs["monat"], rel=1e-4)
