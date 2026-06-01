# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Netz-Capabilities (Open-Data-Netzkosten + Abgaben, offline)."""

from __future__ import annotations

import pytest

from energietools.capabilities.netz.capability import (
    GesamtkostenCapability,
    NetzkostenCapability,
    VerfuegbarkeitCapability,
)
from energietools.capabilities.netz.resolve import (
    gebrauchsabgabe_rate,
    netzkosten_brutto_eur,
    resolve_netzbetreiber,
)
from energietools.capabilities.registry import default_registry


def test_netzkosten_wien_1010() -> None:
    """Wien (Wiener Netze), 3500 kWh → brutto ≈ 440.42 EUR/Jahr."""
    brutto, name = netzkosten_brutto_eur("1010", 3500)
    assert name == "Wiener Netze GmbH"
    assert brutto == pytest.approx(440.42, abs=0.5)


def test_netzkosten_steiermark_8530() -> None:
    """Deutschlandsberg (Energienetze Steiermark, keine Graz-Enklave) → ≈ 502.42."""
    brutto, name = netzkosten_brutto_eur("8530", 3500)
    assert name == "Energienetze Steiermark GmbH"
    assert brutto == pytest.approx(502.42, abs=0.5)


def test_netzkosten_capability_wien() -> None:
    """Capability-Envelope für Wien liefert VNB + Brutto-Betrag + Rechenweg."""
    result = NetzkostenCapability().run(plz="1010", verbrauch_kwh=3500)
    assert result.ok is True
    assert result.data["netzbetreiber"] == "Wiener Netze GmbH"
    assert result.data["netzkosten_eur_jahr_brutto"] == pytest.approx(440.42, abs=0.5)
    assert result.data["rechenweg"]["komponenten"]["brutto_eur_jahr"] == pytest.approx(
        440.42, abs=0.5
    )


def test_unbekannte_plz_fail_open() -> None:
    """Unbekannte PLZ → fail-open: kein VNB, Netzkosten 0."""
    assert resolve_netzbetreiber("99999") is None
    brutto, name = netzkosten_brutto_eur("99999", 3500)
    assert brutto == 0.0
    assert name == ""

    result = NetzkostenCapability().run(plz="99999", verbrauch_kwh=3500)
    assert result.ok is True
    assert result.data["netzbetreiber"] is None
    assert result.data["netzkosten_eur_jahr_brutto"] == 0.0


def test_gebrauchsabgabe_rate() -> None:
    """Wien 7 %, Eisenstadt (Burgenland) 0 %, unbekannte PLZ 0 %."""
    assert gebrauchsabgabe_rate("1010") == 0.07
    assert gebrauchsabgabe_rate("7000") == 0.0
    assert gebrauchsabgabe_rate("99999") == 0.0


def test_gesamtkosten_plausibel() -> None:
    """Gesamtkosten Wien (20 ct/kWh netto, 10 EUR/Monat netto Grund) > 0 und plausibel."""
    result = GesamtkostenCapability().run(
        plz="1010",
        verbrauch_kwh=3500,
        energiepreis_netto_ct_kwh=20.0,
        grundgebuehr_netto_eur_monat=10.0,
    )
    assert result.ok is True
    gesamt = result.data["gesamtkosten_eur_jahr_brutto"]
    # Energie netto 700 + Grund 120 = 820, +7% GAB nur auf Energie, ×1.20 + Netz ~440.
    assert gesamt > 0
    assert 1300 < gesamt < 1600


def test_verfuegbarkeit() -> None:
    """'AT' immer verfügbar; Bundesland-Match aus PLZ; unbekannte PLZ fail-open True."""
    assert VerfuegbarkeitCapability().run(service_area="AT", plz="1010").data["verfuegbar"] is True
    wien = VerfuegbarkeitCapability().run(service_area="Wien", plz="1010").data
    assert wien["verfuegbar"] is True
    assert wien["bundesland"] == "Wien"
    assert (
        VerfuegbarkeitCapability().run(service_area="Tirol", plz="1010").data["verfuegbar"] is False
    )
    assert (
        VerfuegbarkeitCapability().run(service_area="Tirol", plz="99999").data["verfuegbar"] is True
    )


def test_default_registry_enthaelt_netz_capabilities() -> None:
    """Die 4 neuen Netz-Capabilities sind in der Default-Registry registriert."""
    namen = set(default_registry().names)
    assert {
        "netzkosten",
        "gesamtkosten",
        "netz_verfuegbar",
        "tarifvergleich_inkl_netz",
    } <= namen
