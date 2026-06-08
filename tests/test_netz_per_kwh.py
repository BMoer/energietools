# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die per-kWh-Netzentgelt-Schicht (operator-/länderparametrisiert, fail-open).

Diese Schicht hieß früher ``grid_fees`` und ist seit S0 Teil des ``netz``-Pakets
(``netz/per_kwh.py`` + ``netz/per_kwh_capability.py``); der öffentliche
Capability-Name ``"grid_fees"`` bleibt. Die österreichischen Zahlen kommen aus dem
auditierten data/netz-Snapshot — diese Tests prüfen die Auflösung, das
§16b-Verhalten, die Fail-open-Semantik, die Konsistenz mit der netz-Layer-
Komposition und dass der Merge (S0) sauber ist (Paket weg, Surface unter netz,
Capability-Name erhalten).
"""

from __future__ import annotations

import importlib

import pytest

from energietools.capabilities.netz import (
    DEFAULT_OPERATOR_AT,
    GridFeesCapability,
    charging_fee_ct_kwh,
    consumption_fee_ct_kwh,
    default_network_fee_ct_kwh,
    network_fee_ct_kwh,
    resolve_operator,
)


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


# --- S0-Merge-Guards: das grid_fees-Paket ist weg, das Surface lebt unter netz ----


def test_grid_fees_package_removed() -> None:
    """Das eigenständige grid_fees-Paket existiert nach S0 nicht mehr (Delete-Evidence)."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("energietools.capabilities.grid_fees")


def test_per_kwh_surface_exported_from_netz() -> None:
    """Alle per-kWh-Symbole + die Capability sind über das netz-Paket erreichbar."""
    netz = importlib.import_module("energietools.capabilities.netz")
    for name in (
        "DEFAULT_OPERATOR_AT",
        "GridFeesCapability",
        "charging_fee_ct_kwh",
        "consumption_fee_ct_kwh",
        "default_network_fee_ct_kwh",
        "network_fee_ct_kwh",
        "resolve_operator",
        "total_fee_breakdown",
    ):
        assert hasattr(netz, name), f"netz exportiert {name} nicht"


def test_grid_fees_capability_name_kept() -> None:
    """Der öffentliche Capability-Name bleibt 'grid_fees' (CLI-/LLM-Tool-Name)."""
    from energietools.capabilities.registry import default_registry

    assert "grid_fees" in default_registry().names
