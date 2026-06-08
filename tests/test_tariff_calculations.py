# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für Tarifberechnungs-Logik: Rechenweg (separate-GAB-Block), GAB-Formel.

Verifiziert die korrekte Berechnung von Stromkosten nach österreichischem Recht
(ElWG, Gebrauchsabgabegesetz). Seit S4 ist die Gebrauchsabgabe ein EIGENER
Brutto-Block (nicht in brutto_jahreskosten_eur gefaltet); USt liegt nur auf
Energie+Grund nach Rabatt. Die Vergleichs-Logik (enrich) lebt im Produkt (gridbert).
"""

from __future__ import annotations

import pytest

from energietools.capabilities.tariffs.catalog import detect_tariftyp
from energietools.capabilities.tariffs.compare import kosten_rechenweg
from energietools.models import Rechenweg, Tariff

# =============================================================================
# 1. GAB-Gesamtkosten-Formel: netto × (1 + GAB) × 1.2 = Gesamt-Brutto (Energie+GAB)
# =============================================================================


class TestGABFormel:
    """Verifiziert die österreichische Energiekosten-Arithmetik (Gesamtwert)."""

    def test_wien_standard(self):
        """Wien: 25 ct/kWh brutto, 6 EUR/Mo brutto, 3200 kWh, 7% GAB."""
        netto_ep_ct = 25.0 / 1.2  # 20.8333
        netto_gg_eur = 6.0 / 1.2  # 5.0
        netto_e = 3200 * netto_ep_ct / 100  # 666.67
        netto_g = netto_gg_eur * 12  # 60.0
        netto = netto_e + netto_g  # 726.67
        gesamt_brutto = netto * 1.07 * 1.2  # 933.04 (Energie 872 + GAB-Block 61.04)

        assert round(netto_e, 2) == 666.67
        assert round(netto_g, 2) == 60.0
        assert round(netto, 2) == 726.67
        assert round(gesamt_brutto, 2) == 933.04
        # Separate-Block-Zerlegung: Energie-Brutto + GAB-Brutto == Gesamt.
        assert round(netto * 1.2, 2) == 872.0
        assert round(netto * 0.07 * 1.2, 2) == 61.04
        assert round(872.0 + 61.04, 2) == 933.04

    def test_keine_gebrauchsabgabe(self):
        """PLZ ohne GAB: brutto_jahreskosten = netto × 1.2."""
        netto = 726.67
        assert round(netto * 1.2, 2) == 872.0

    def test_netto_brutto_roundtrip(self):
        """Brutto → Netto → Brutto muss exakt sein (ohne GAB)."""
        brutto_ep = 25.0
        netto_ep = brutto_ep / 1.2
        assert abs(netto_ep * 1.2 - brutto_ep) < 0.001


# =============================================================================
# 2. Rechenweg Model + kosten_rechenweg (separate-GAB-Block)
# =============================================================================


class TestRechenweg:
    """Verifiziert das separate-Block-Rechenweg-Modell + kosten_rechenweg."""

    def test_kosten_rechenweg_separate_block(self):
        """Wien 3200 kWh, 7% GAB: Energie-Brutto 872, GAB eigener Brutto-Block 61.04."""
        rw = kosten_rechenweg(
            verbrauch_kwh=3200,
            netto_ep_ct=25.0 / 1.2,
            netto_gg_eur_monat=6.0 / 1.2,
            gebrauchsabgabe_rate=0.07,
        )
        assert rw.brutto_jahreskosten_eur == pytest.approx(872.0, abs=0.01)  # OHNE GAB
        assert rw.gebrauchsabgabe_eur == pytest.approx(61.04, abs=0.01)  # eigener Brutto-Block
        assert rw.ust_eur == pytest.approx(726.67 * 0.2, abs=0.01)  # USt nur auf Energie
        assert not hasattr(rw, "netto_inkl_gab_eur")

    def test_brutto_excludes_gab(self):
        """brutto_jahreskosten_eur ist bei rate=0 und rate=0.07 identisch (GAB ist außen)."""
        kwargs = dict(verbrauch_kwh=3200, netto_ep_ct=25.0 / 1.2, netto_gg_eur_monat=6.0 / 1.2)
        rw0 = kosten_rechenweg(gebrauchsabgabe_rate=0.0, **kwargs)
        rw7 = kosten_rechenweg(gebrauchsabgabe_rate=0.07, **kwargs)
        assert rw0.brutto_jahreskosten_eur == rw7.brutto_jahreskosten_eur
        assert rw0.gebrauchsabgabe_eur == 0.0
        assert rw7.gebrauchsabgabe_eur > 0.0

    def test_rechenweg_serialization(self):
        """Rechenweg muss JSON-serialisierbar sein."""
        rw = kosten_rechenweg(
            verbrauch_kwh=3200, netto_ep_ct=20.8333, netto_gg_eur_monat=5.0,
            gebrauchsabgabe_rate=0.07,
        )
        data = rw.model_dump()
        assert isinstance(data, dict)
        assert data["gebrauchsabgabe_rate"] == 0.07
        assert "netto_inkl_gab_eur" not in data
        reconstructed = Rechenweg(**data)
        assert reconstructed.brutto_jahreskosten_eur == rw.brutto_jahreskosten_eur


# =============================================================================
# 3. Tariftyp-Erkennung
# =============================================================================


class TestDetectTariftyp:
    """Testet die Erkennung von Tariftypen aus Produktnamen."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("VERBUND Strom Privat Fix", "Fixpreis"),
            ("Wien Energie Optima Entspannt", "Fixpreis"),
            ("aWATTar Monatsfloater", "Monatsfloater"),
            ("easy green flex", "Monatsfloater"),
            ("Tibber Spot Stundentarif", "Stundenfloater"),
            ("dynamisch hourly", "Stundenfloater"),
            ("Float-Tarif 2025", "Monatsfloater"),
        ],
    )
    def test_tariftyp_detection(self, name: str, expected: str):
        assert detect_tariftyp(name) == expected


# =============================================================================
# 4. Selbst-Validierung: Rechenweg schließt (separate-Block)
# =============================================================================


class TestSelbstValidierung:
    """Prüft dass der Rechenweg intern konsistent ist und zum Endwert passt."""

    def test_rechenweg_matches_jahreskosten(self):
        """Der Energie-Endwert (ohne GAB) muss zu jahreskosten_eur passen; GAB separat."""
        rw = kosten_rechenweg(
            verbrauch_kwh=3200, netto_ep_ct=25.0 / 1.2, netto_gg_eur_monat=6.0 / 1.2,
            gebrauchsabgabe_rate=0.07,
        )
        tariff = Tariff(
            lieferant="Test", tarif_name="Test",
            energiepreis_ct_kwh=25.0, grundgebuehr_eur_monat=6.0,
            jahreskosten_eur=rw.brutto_jahreskosten_eur,  # Energie ohne GAB
            gebrauchsabgabe_eur=rw.gebrauchsabgabe_eur,  # GAB eigener Block
            rechenweg=rw,
        )
        assert tariff.rechenweg.brutto_jahreskosten_eur == tariff.jahreskosten_eur
        assert abs(rw.netto_gesamt_eur - (rw.netto_energie_eur + rw.netto_grund_eur)) < 0.01
        # GAB-Block = netto × rate × 1.2 (brutto), NICHT in brutto_jahreskosten.
        erwartet_gab = rw.netto_gesamt_eur * rw.gebrauchsabgabe_rate * 1.2
        assert abs(rw.gebrauchsabgabe_eur - erwartet_gab) < 0.01
