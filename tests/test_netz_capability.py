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
    akzeptierte_vnb_namen,
    gebrauchsabgabe_rate,
    netzkosten_brutto_eur,
    resolve_netzbetreiber,
    vnb_name_akzeptiert,
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
    assert wien["bundeslaender"] == ["Wien"]
    assert (
        VerfuegbarkeitCapability().run(service_area="Tirol", plz="1010").data["verfuegbar"] is False
    )
    assert (
        VerfuegbarkeitCapability().run(service_area="Tirol", plz="99999").data["verfuegbar"] is True
    )


def test_stadt_netzbereiche_loesen_inklusion_first() -> None:
    """Single-Gemeinde-Stadt-PLZ lösen via Inklusion auf ihren eigenen VNB auf."""
    assert resolve_netzbetreiber("8020").key == "stromnetz_graz"  # Graz (eine Gemeinde)
    assert resolve_netzbetreiber("4030").key == "linz_netz"  # Linz (eine Gemeinde)


def test_geteilte_plz_fail_open_none() -> None:
    """Geteilte PLZ (mehrere Gemeinden über mehrere VNB) → fail-open None (Schema v2)."""
    # 6020 = Innsbruck (IKB) + Mutters/Natters/... (TINETZ); 8605 = Kapfenberg + St. Lorenzen.
    assert resolve_netzbetreiber("6020") is None
    assert resolve_netzbetreiber("8605") is None
    assert netzkosten_brutto_eur("8605", 3500) == (0.0, "")


def test_kleinwalsertal_evk_hoechster_tarif() -> None:
    """Kleinwalsertal (Mittelberg, 6991) → EVK, höchster NE7-Tarif Österreichs."""
    brutto, name = netzkosten_brutto_eur("6991", 3500)
    assert resolve_netzbetreiber("6991").key == "evk"
    assert name.startswith("Energieversorgung Kleinwalsertal")
    # AP 17,73 ist mit Abstand der höchste → deutlich teurer als jeder Landes-VNB.
    assert brutto > 800


def test_attribution_feldkirch_realer_name_vorarlberg_tarif() -> None:
    """Feldkirch (6800) → realer Name 'Stadtwerke Feldkirch', Tarif = Vorarlberg.

    (8605 Kapfenberg ist im Voll-Schema eine geteilte PLZ; 6800 Feldkirch ist die
    verbleibende Single-Gemeinde-Attributions-PLZ.)
    """
    brutto, name = netzkosten_brutto_eur("6800", 3500)
    assert name == "Stadtwerke Feldkirch"  # realer Betreiber, nicht der Landes-VNB
    # Kosten exakt wie ein Vorarlberg-Landes-Anschluss (Bürs 6706).
    landes_brutto, _ = netzkosten_brutto_eur("6706", 3500)
    assert brutto == pytest.approx(landes_brutto)


def test_aequivalenz_beide_namen_akzeptiert() -> None:
    """An einer Feldkirch-PLZ gelten realer Name UND Netzbereich-Name."""
    assert akzeptierte_vnb_namen("6800") == {
        "Stadtwerke Feldkirch",
        "Vorarlberger Energienetze GmbH",
    }
    assert vnb_name_akzeptiert("6800", "Stadtwerke Feldkirch")
    assert vnb_name_akzeptiert("6800", "Vorarlberger Energienetze")  # ohne GmbH
    assert vnb_name_akzeptiert("6800", "vorarlberger energienetze gmbh")  # tolerant
    assert not vnb_name_akzeptiert("6800", "Wiener Netze")  # fremder VNB


def test_attribution_capability_rechenweg_korrekt() -> None:
    """Capability zeigt realen Namen + korrekten (referenzierten) Rechenweg."""
    result = NetzkostenCapability().run(plz="6800", verbrauch_kwh=3500)
    assert result.ok is True
    assert result.data["netzbetreiber"] == "Stadtwerke Feldkirch"
    assert result.data["netzbereich"] == "Vorarlberger Energienetze GmbH"  # Tarif-Herkunft
    # Rechenweg-AP ist der Vorarlberg-Tarif (4,96), NICHT 0 (Attributions-VNB).
    komp = result.data["rechenweg"]["komponenten"]
    assert komp["netznutzung_arbeitspreis_ct_kwh"] == pytest.approx(4.96, abs=1e-3)
    assert result.data["netzkosten_eur_jahr_brutto"] == pytest.approx(342.69, abs=0.5)


def test_default_registry_enthaelt_netz_capabilities() -> None:
    """Die Netz-Capabilities sind registriert; die Vergleichs-Capability ist entfernt (S4)."""
    namen = set(default_registry().names)
    assert {"netzkosten", "gesamtkosten", "netz_verfuegbar"} <= namen
    assert "tarifvergleich_inkl_netz" not in namen
