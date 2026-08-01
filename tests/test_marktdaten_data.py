# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für den Solar/Speicher-Marktdaten-Loader (offline, kein Capability-Envelope).

Rein informative Daten (siehe METHODIK.md §9) — keine eigene Capability, daher
kein CapabilityResult-Envelope zu testen, nur der Loader selbst.
"""

from __future__ import annotations

from energietools.capabilities.marktdaten.data import load_manifest, load_solar_speicher


def test_manifest_konsistenz() -> None:
    manifest = load_manifest()
    assert manifest.license == "MIT"
    daten = load_solar_speicher()
    assert manifest.coverage["vermittler"] == len(daten.vermittler) == 3
    assert manifest.coverage["hersteller_haendler_speicher"] == len(
        daten.hersteller_haendler_speicher
    )


def test_golden_case_ausgeschlossene_anbieter() -> None:
    """EET (Insolvenz) ist mit Begründung als ausgeschlossen geführt, nicht verschwiegen."""
    daten = load_solar_speicher()
    namen = {e["name"] for e in daten.ausgeschlossen}
    assert any("EET" in n for n in namen)
    eet = next(e for e in daten.ausgeschlossen if "EET" in e["name"])
    assert "Insolven" in eet["grund"]


def test_speicherpreis_referenz_hat_quelle() -> None:
    daten = load_solar_speicher()
    ref = daten.speicherpreis_referenz
    assert ref["wert"] == "445 €/kWh"
    assert ref["quelle"]["url"]


def test_balkonkraftwerk_800w_regel() -> None:
    daten = load_solar_speicher()
    grenze = daten.balkonkraftwerk_regeln["leistungsgrenze"]
    assert "0,8 kW" in grenze["wert"]


def test_snapshot_ist_immutable() -> None:
    daten = load_solar_speicher()
    assert isinstance(daten.vermittler, tuple)
    assert isinstance(daten.ausgeschlossen, tuple)
