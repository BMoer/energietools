# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die grid_fees-Capability (operator-/länderparametrisiert, fail-open).

Die österreichischen Zahlen kommen aus dem auditierten data/netz-Snapshot —
diese Tests prüfen die Auflösung, das §16b-Verhalten, die Fail-open-Semantik und
dass der per-kWh-Wert mit der netz-Layer-Komposition konsistent ist.
"""

from __future__ import annotations

from energietools.capabilities.grid_fees import (
    DEFAULT_OPERATOR_AT,
    charging_fee_ct_kwh,
    consumption_fee_ct_kwh,
    default_network_fee_ct_kwh,
    network_fee_ct_kwh,
    resolve_operator,
)
from energietools.capabilities.grid_fees.capability import GridFeesCapability


def test_resolve_default_operator_at() -> None:
    e = resolve_operator(None, "AT")
    assert e is not None
    assert e.key == DEFAULT_OPERATOR_AT
    # Sourced NE7 numbers from data/netz (Energienetze Steiermark, Stand 2026-04-01).
    assert e.netznutzung_arbeitspreis_ct_kwh == 8.82
    assert e.netzverlust_ct_kwh == 0.336


def test_resolve_by_name_is_case_insensitive() -> None:
    by_key = resolve_operator("wiener_netze", "AT")
    by_name = resolve_operator("WIENER NETZE GMBH", "AT")
    assert by_key is not None and by_name is not None
    assert by_key.key == by_name.key == "wiener_netze"


def test_network_fee_is_netznutzung_plus_verlust() -> None:
    # Pure network component (no federal levies), net.
    fee = network_fee_ct_kwh("energienetze_steiermark", "AT", brutto=False)
    assert fee == round(8.82 + 0.336, 4)


def test_consumption_fee_includes_federal_levies_and_vat() -> None:
    net = consumption_fee_ct_kwh("energienetze_steiermark", "AT", brutto=False)
    brutto = consumption_fee_ct_kwh("energienetze_steiermark", "AT", brutto=True)
    # net = AP + Verlust + EAG_AP + EAG_Verlust + Elektrizitätsabgabe
    assert net == round(8.82 + 0.336 + 0.583 + 0.037 + 0.1, 4)
    assert brutto == round(net * 1.20, 4)


def test_charging_fee_storage_exemption_is_zero() -> None:
    assert charging_fee_ct_kwh("energienetze_steiermark", "AT", storage_exemption=True) == 0.0
    assert charging_fee_ct_kwh("energienetze_steiermark", "AT", storage_exemption=False) > 0.0


def test_foreign_country_fails_open_to_none() -> None:
    assert resolve_operator("energienetze_steiermark", "DE") is None
    assert network_fee_ct_kwh("energienetze_steiermark", "DE") is None
    assert consumption_fee_ct_kwh(None, "CH") is None


def test_default_network_fee_is_sourced_not_magic() -> None:
    # Replaces the old DEFAULT_NETZ_CT = 3.5 magic number with a sourced value.
    assert default_network_fee_ct_kwh("AT") == round(8.82 + 0.336, 4)


def test_capability_annual_and_rechenweg() -> None:
    res = GridFeesCapability().run(verbrauch_kwh=3500, operator="energienetze_steiermark")
    assert res.ok
    data = res.data
    assert data["operator"] == "Energienetze Steiermark GmbH"
    assert data["grid_fee_eur_jahr_brutto"] > 0
    # Rechenweg is auditable: components + UST factor + source present.
    komp = data["rechenweg"]["komponenten"]
    assert komp["ust_faktor"] == 1.20
    assert data["quelle"]  # source URL/regulation present


def test_capability_unknown_operator_fails_open() -> None:
    res = GridFeesCapability().run(verbrauch_kwh=3500, operator="gibtsnicht")
    assert res.ok  # fail-open, not an error
    assert res.data["operator"] is None
    assert res.data["grid_fee_eur_jahr_brutto"] == 0.0


def test_capability_requires_positive_verbrauch() -> None:
    res = GridFeesCapability().run(verbrauch_kwh=0)
    assert not res.ok
    assert "verbrauch_kwh" in (res.error or "")
