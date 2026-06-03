# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für Tarifberechnungs-Logik: Rechenweg, GAB-Formel, Netto/Brutto-Konvertierung.

Diese Tests verifizieren die korrekte Berechnung von Stromkosten nach
österreichischem Recht (ElWG, Gebrauchsabgabegesetz) ohne API-Abhängigkeit.
"""

from __future__ import annotations

import pytest

from energietools.capabilities.tariffs.catalog import detect_tariftyp
from energietools.models import Rechenweg, Tariff, TariffComparison

# =============================================================================
# 1. GAB-Formel: netto × (1 + GAB) × 1.2 = brutto
# =============================================================================


class TestGABFormel:
    """Verifiziert die österreichische Energiekosten-Formel."""

    def test_wien_standard(self):
        """Wien: 25 ct/kWh brutto, 6 EUR/Mo brutto, 3200 kWh, 7% GAB."""
        netto_ep_ct = 25.0 / 1.2  # 20.8333
        netto_gg_eur = 6.0 / 1.2  # 5.0
        netto_e = 3200 * netto_ep_ct / 100  # 666.67
        netto_g = netto_gg_eur * 12  # 60.0
        netto = netto_e + netto_g  # 726.67
        brutto = netto * 1.07 * 1.2  # 933.04

        assert round(netto_e, 2) == 666.67
        assert round(netto_g, 2) == 60.0
        assert round(netto, 2) == 726.67
        assert round(brutto, 2) == 933.04

    def test_keine_gebrauchsabgabe(self):
        """PLZ ohne GAB: netto × 1.0 × 1.2 = netto × 1.2."""
        netto = 726.67
        brutto = netto * 1.0 * 1.2
        assert round(brutto, 2) == 872.0

    def test_gebrauchsabgabe_5_prozent(self):
        """5% GAB (typisch NÖ)."""
        netto = 726.67
        brutto = netto * 1.05 * 1.2
        assert round(brutto, 2) == 915.60

    def test_netto_brutto_roundtrip(self):
        """Brutto → Netto → Brutto muss exakt sein (ohne GAB)."""
        brutto_ep = 25.0
        netto_ep = brutto_ep / 1.2
        back_to_brutto = netto_ep * 1.2
        assert abs(back_to_brutto - brutto_ep) < 0.001

    def test_taschenrechner_vs_gab(self):
        """Ein User rechnet: 25 ct × 3200 / 100 + 6 × 12 = 872 EUR.
        Die korrekte Berechnung inkl. 7% GAB ist 933.04 EUR.
        Differenz = 61.04 EUR (die GAB)."""
        taschenrechner = 3200 * 25.0 / 100 + 6.0 * 12  # 872.0
        gab_formel = (3200 * (25.0 / 1.2) / 100 + (6.0 / 1.2) * 12) * 1.07 * 1.2  # 933.04
        assert round(taschenrechner, 2) == 872.0
        assert round(gab_formel, 2) == 933.04
        assert round(gab_formel - taschenrechner, 2) == 61.04


# =============================================================================
# 2. Rechenweg Model
# =============================================================================


class TestRechenweg:
    """Verifiziert das Rechenweg-Datenmodell."""

    def _make_rechenweg(self, gab: float = 0.07) -> Rechenweg:
        netto_e = 666.67
        netto_g = 60.0
        netto = netto_e + netto_g
        gab_eur = netto * gab
        netto_inkl = netto + gab_eur
        ust = netto_inkl * 0.2
        return Rechenweg(
            energiepreis_netto_ct_kwh=20.8333,
            grundgebuehr_netto_eur_monat=5.0,
            netto_energie_eur=netto_e,
            netto_grund_eur=netto_g,
            netto_gesamt_eur=netto,
            gebrauchsabgabe_rate=gab,
            gebrauchsabgabe_eur=round(gab_eur, 2),
            netto_inkl_gab_eur=round(netto_inkl, 2),
            ust_eur=round(ust, 2),
            brutto_jahreskosten_eur=round(netto_inkl * 1.2, 2),
            quelle="berechnet",
        )

    def test_rechenweg_consistency(self):
        """Rechenwerte müssen intern konsistent sein."""
        rw = self._make_rechenweg()
        assert rw.netto_gesamt_eur == rw.netto_energie_eur + rw.netto_grund_eur
        assert abs(rw.gebrauchsabgabe_eur - rw.netto_gesamt_eur * rw.gebrauchsabgabe_rate) < 0.01
        assert abs(rw.netto_inkl_gab_eur - (rw.netto_gesamt_eur + rw.gebrauchsabgabe_eur)) < 0.01
        assert abs(rw.ust_eur - rw.netto_inkl_gab_eur * 0.2) < 0.01
        assert abs(rw.brutto_jahreskosten_eur - rw.netto_inkl_gab_eur * 1.2) < 0.01

    def test_rechenweg_serialization(self):
        """Rechenweg muss JSON-serialisierbar sein."""
        rw = self._make_rechenweg()
        data = rw.model_dump()
        assert isinstance(data, dict)
        assert data["gebrauchsabgabe_rate"] == 0.07
        reconstructed = Rechenweg(**data)
        assert reconstructed.brutto_jahreskosten_eur == rw.brutto_jahreskosten_eur


# =============================================================================
# 4. TariffComparison.enrich()
# =============================================================================


class TestTariffComparisonEnrich:
    """Testet die Anreicherung mit Ersparnis und Kategorien."""

    def _make_comparison(self) -> TariffComparison:
        aktuell = Tariff(
            lieferant="Wien Energie",
            tarif_name="Aktueller Tarif",
            energiepreis_ct_kwh=25.0,
            grundgebuehr_eur_monat=6.0,
            jahreskosten_eur=933.04,
        )
        alt1 = Tariff(
            lieferant="Billigstrom",
            tarif_name="Fix Billig",
            energiepreis_ct_kwh=18.0,
            grundgebuehr_eur_monat=3.0,
            jahreskosten_eur=650.0,
            tariftyp="Fixpreis",
        )
        alt2 = Tariff(
            lieferant="Floater AG",
            tarif_name="Monatsfloater Plus",
            energiepreis_ct_kwh=17.0,
            grundgebuehr_eur_monat=4.0,
            jahreskosten_eur=620.0,
            tariftyp="Monatsfloater",
            ist_oekostrom=True,
        )
        return TariffComparison(
            aktueller_tarif=aktuell,
            alternativen=[alt1, alt2],
            plz="1060",
            jahresverbrauch_kwh=3200,
            netzkosten_eur_jahr=473.51,
            netzbetreiber="Wiener Netze",
            gebrauchsabgabe_rate=0.07,
        )

    def test_ersparnis_berechnung(self):
        """Ersparnis = aktuell.jahreskosten - alternative.jahreskosten."""
        result = self._make_comparison().enrich()
        assert result.beste_fix[0].ersparnis_eur == round(933.04 - 650.0, 2)

    def test_gesamtkosten_berechnung(self):
        """Gesamtkosten = jahreskosten + netzkosten."""
        result = self._make_comparison().enrich()
        assert result.beste_fix[0].gesamtkosten_eur == round(650.0 + 473.51, 2)
        assert result.aktueller_tarif.gesamtkosten_eur == round(933.04 + 473.51, 2)

    def test_kategorisierung(self):
        """Fixpreis → 'fix', Monatsfloater → 'floater'."""
        result = self._make_comparison().enrich()
        assert len(result.beste_fix) == 1
        assert result.beste_fix[0].kategorie == "fix"
        assert len(result.beste_floater) == 1
        assert result.beste_floater[0].kategorie == "floater"

    def test_gruen_kategorie(self):
        """Ökostrom-Tarife in beste_gruen."""
        result = self._make_comparison().enrich()
        assert len(result.beste_gruen) == 1
        assert result.beste_gruen[0].ist_oekostrom is True

    def test_max_ersparnis(self):
        """max_ersparnis = aktuell - günstigster."""
        result = self._make_comparison().enrich()
        assert result.max_ersparnis_eur == round(933.04 - 620.0, 2)

    def test_gebrauchsabgabe_rate_propagated(self):
        """GAB-Rate wird durch enrich() durchgereicht."""
        result = self._make_comparison().enrich()
        assert result.gebrauchsabgabe_rate == 0.07


# =============================================================================
# 5. Tariftyp-Erkennung
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
# 6. Selbst-Validierung: Rechenweg-Konsistenz
# =============================================================================


class TestSelbstValidierung:
    """Prüft dass der Rechenweg intern konsistent ist und zum Endwert passt."""

    def test_rechenweg_matches_jahreskosten(self):
        """Der Rechenweg muss zum gleichen Ergebnis wie jahreskosten_eur kommen."""
        rw = Rechenweg(
            energiepreis_netto_ct_kwh=20.8333,
            grundgebuehr_netto_eur_monat=5.0,
            netto_energie_eur=666.67,
            netto_grund_eur=60.0,
            netto_gesamt_eur=726.67,
            gebrauchsabgabe_rate=0.07,
            gebrauchsabgabe_eur=50.87,
            netto_inkl_gab_eur=777.53,
            ust_eur=155.51,
            brutto_jahreskosten_eur=933.04,
            quelle="berechnet",
        )
        tariff = Tariff(
            lieferant="Test",
            tarif_name="Test",
            energiepreis_ct_kwh=25.0,
            grundgebuehr_eur_monat=6.0,
            jahreskosten_eur=933.04,
            rechenweg=rw,
        )
        # Validate: rechenweg.brutto == jahreskosten
        assert tariff.rechenweg.brutto_jahreskosten_eur == tariff.jahreskosten_eur
        # Validate: internal consistency
        assert abs(rw.netto_gesamt_eur - (rw.netto_energie_eur + rw.netto_grund_eur)) < 0.01
        assert abs(rw.gebrauchsabgabe_eur - rw.netto_gesamt_eur * rw.gebrauchsabgabe_rate) < 0.01
        assert abs(rw.netto_inkl_gab_eur - (rw.netto_gesamt_eur + rw.gebrauchsabgabe_eur)) < 0.01
