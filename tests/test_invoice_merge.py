# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für den B.4-Merge: die Produkt-Exklusiva sind in finalize_invoice
zurückgeführt (EVU-Prognose ±30 %, jahreskosten_brutto_eur, Adress-Extraktion,
Zählpunkt-Kanon, Kombi-per-Energie-Override, warnings).

Fixtures sind synthetisch (keine echten Kundendaten/PII).
"""

from __future__ import annotations

import pytest

from energietools.models.invoice import Invoice
from energietools.tools.invoice_parser import (
    _extract_address_from_text,
    _extract_deterministic_from_text,
    _is_address_incomplete,
    finalize_invoice,
)
from energietools.tools.zaehlpunkt import canonical_zaehlpunkt, is_valid, validate


def _basis_raw(**overrides) -> dict:
    raw = {
        "lieferant": "Testenergie",
        "arbeitspreis_ct_kwh": 15.0,
        "arbeitspreis_ist_netto": True,
        "verbrauch_kwh": 1750.0,
        "plz": "1060",
        "zeitraum_von": "01.01.2025",
        "zeitraum_bis": "01.07.2025",  # 181 Tage → Hochrechnung
    }
    raw.update(overrides)
    return raw


# =============================================================================
# 1. EVU-Prognose ±30%-Fenster
# =============================================================================


class TestPrognoseFenster:
    def test_plausible_prognose_uebernimmt_hochrechnung(self):
        # Hochrechnung: 1750 × 365/181 ≈ 3529 kWh; Prognose 3300 liegt im Fenster.
        result = finalize_invoice(_basis_raw(jahresverbrauch_prognose_kwh=3300.0))
        assert result["ist_hochgerechnet"] is True
        assert result["jahresverbrauch_kwh"] == 3300.0
        assert result["jahresverbrauch_prognose_kwh"] == 3300.0

    def test_implausible_prognose_wird_ignoriert(self):
        # Prognose 9000 kWh liegt >30 % über der Hochrechnung → deterministischer Wert.
        result = finalize_invoice(_basis_raw(jahresverbrauch_prognose_kwh=9000.0))
        assert result["jahresverbrauch_kwh"] == pytest.approx(1750.0 * 365 / 181, abs=0.1)
        assert "jahresverbrauch_prognose_kwh" not in result or not result.get(
            "jahresverbrauch_prognose_kwh",
        )

    def test_fast_jaehrliche_rechnung_ignoriert_prognose(self):
        # >= 350 Tage: der Ist-Verbrauch schlägt die EVU-Schätzung.
        result = finalize_invoice(_basis_raw(
            zeitraum_von="01.01.2025", zeitraum_bis="31.12.2025",
            verbrauch_kwh=3500.0, jahresverbrauch_prognose_kwh=3400.0,
        ))
        assert result["ist_hochgerechnet"] is False
        assert result["jahresverbrauch_kwh"] == 3500.0


# =============================================================================
# 2. jahreskosten_brutto_eur (Hauptmetrik)
# =============================================================================


class TestJahreskostenBrutto:
    def test_teilzeitraum_wird_annualisiert(self):
        result = finalize_invoice(_basis_raw(rechnungsbetrag_brutto_eur=600.0))
        assert result["rechnungsbetrag_brutto_eur"] == 600.0
        assert result["jahreskosten_brutto_eur"] == pytest.approx(600.0 * 365 / 181, abs=0.01)

    def test_jahresrechnung_bleibt_wie_sie_ist(self):
        result = finalize_invoice(_basis_raw(
            zeitraum_von="01.01.2025", zeitraum_bis="31.12.2025",
            verbrauch_kwh=3500.0, rechnungsbetrag_brutto_eur=1200.0,
        ))
        assert result["jahreskosten_brutto_eur"] == 1200.0

    def test_ohne_rechnungsbetrag_null(self):
        result = finalize_invoice(_basis_raw())
        assert result["jahreskosten_brutto_eur"] == 0.0
        assert "rechnungsbetrag_missing" in result["warnings"]

    def test_invoice_modell_traegt_hauptmetrik(self):
        result = finalize_invoice(_basis_raw(rechnungsbetrag_brutto_eur=600.0))
        inv = Invoice(**result)
        assert inv.jahreskosten_brutto_eur > 0
        assert inv.rechnungsbetrag_brutto_eur == 600.0


# =============================================================================
# 3. Adress-Extraktion (Anlagen-/Verbrauchsadresse)
# =============================================================================


class TestAdressExtraktion:
    _TEXT = (
        "Ihre Rechnung\n"
        "Anlagenadresse: Mag. Max Muster\n"
        "Musterstraße 12/4\n"
        "1060 Wien\n"
        "Zählpunkt: AT0010000000000000000000000012345\n"
        "Abrechnungszeitraum: 01.01.2025 - 31.12.2025\n"
        "wurden 3.500 kWh verbraucht\n"
        "Energiekosten 700,00\n"
    )

    def test_extrahiert_strasse_plz_ort(self):
        adresse, plz = _extract_address_from_text(self._TEXT)
        assert adresse == "Musterstraße 12/4, 1060 Wien"
        assert plz == "1060"

    def test_namenszeile_wird_verworfen(self):
        adresse, _ = _extract_address_from_text(self._TEXT)
        assert "Muster," not in adresse  # der Personenname ist kein Adressteil

    def test_deterministic_extraction_fuellt_adresse(self):
        result = _extract_deterministic_from_text(self._TEXT * 3)  # > 200 Zeichen
        assert result is not None
        assert result["adresse"] == "Musterstraße 12/4, 1060 Wien"

    def test_is_address_incomplete(self):
        assert _is_address_incomplete("") is True
        assert _is_address_incomplete("1060 Wien") is True  # keine Hausnummer
        assert _is_address_incomplete("Musterstraße") is True  # keine PLZ/Ort
        assert _is_address_incomplete("Musterstraße 12, 1060 Wien") is False

    def test_prognose_regex(self):
        text = (
            "Ihr voraussichtlicher Jahresverbrauch von 3.300 kWh wurde "
            "auf Basis Ihres Lastprofils geschätzt.\n" + self._TEXT
        )
        result = _extract_deterministic_from_text(text)
        assert result is not None
        assert result["jahresverbrauch_prognose_kwh"] == 3300.0


# =============================================================================
# 4. Zählpunkt-Kanon
# =============================================================================


class TestZaehlpunktKanon:
    def test_punktierte_form_wird_kanonisiert(self):
        assert (
            canonical_zaehlpunkt("AT.001000.00000.00000000000000012345")
            == "AT0010000000000000000000000012345"
        )

    def test_leerzeichen_form(self):
        zp = canonical_zaehlpunkt("AT 001000 00000 00000000000000012345")
        assert is_valid(zp)

    def test_pauschal_sentinel_roundtrip(self):
        zp = canonical_zaehlpunkt("AT399999999999 PAUSCHALE00000009999")
        assert zp == "AT399999999999PAUSCHALE00000009999"
        assert validate(zp).is_pauschal is True
        assert validate(zp).valid_strict is True

    def test_llm_platzhalter_faellt_durch(self):
        assert validate("NICHT EXPLIZIT ANGEGEBEN").valid_strict is False

    def test_finalize_kanonisiert_und_droppt_prosa(self):
        result = finalize_invoice(_basis_raw(zaehlpunkt="AT.001000.00000.00000000000000012345"))
        assert result["zaehlpunkt"] == "AT0010000000000000000000000012345"
        result = finalize_invoice(_basis_raw(zaehlpunkt="nicht angegeben"))
        assert result["zaehlpunkt"] == ""


# =============================================================================
# 5. Kombi: Strom-Block übersteuert per-Energie-Felder
# =============================================================================


class TestKombiOverride:
    def test_strom_block_gewinnt_bei_per_energie_feldern(self):
        # Top-Level trägt (fälschlich) die Gas-Werte — der Strom-Block muss die
        # per-Energie-Felder (verbrauch, zaehlpunkt, tarif_name) übersteuern.
        raw = {
            "lieferant": "Kombi Energie AG",
            "plz": "1060",
            "verbrauch_kwh": 12000.0,  # Gas-Verbrauch, fälschlich top-level
            "zaehlpunkt": "AT0020000000000000000000000099999",
            "zeitraum_von": "01.01.2025",
            "zeitraum_bis": "31.12.2025",
            "strom": {
                "verbrauch_kwh": 3500.0,
                "zaehlpunkt": "AT0010000000000000000000000012345",
                "tarif_name": "Strom Fix",
                "arbeitspreis_ct_kwh": 15.0,
            },
            "gas": {
                "verbrauch_kwh": 12000.0,
                "arbeitspreis_ct_kwh": 6.0,
                "tarif_name": "Gas Fix",
            },
        }
        result = finalize_invoice(raw)
        assert result["energieart"] == "kombi"
        assert result["jahresverbrauch_kwh"] == 3500.0  # Strom, nicht Gas
        assert result["zaehlpunkt"] == "AT0010000000000000000000000012345"
        assert result["tarif_name"] == "Strom Fix"
        assert result["gas"].jahresverbrauch_kwh == 12000.0

    def test_explizite_energieart_wird_respektiert(self):
        result = finalize_invoice(_basis_raw(energieart="gas"))
        assert result["energieart"] == "gas"


# =============================================================================
# 6. warnings (Extraktionsqualität)
# =============================================================================


class TestWarnings:
    def test_saubere_extraktion_ohne_flags(self):
        result = finalize_invoice(_basis_raw(
            rechnungsbetrag_brutto_eur=600.0,
            adresse="Musterstraße 12, 1060 Wien",
        ))
        assert result["warnings"] == []

    def test_flags_fuer_fehlende_felder(self):
        result = finalize_invoice(_basis_raw())
        assert "rechnungsbetrag_missing" in result["warnings"]
        assert "adresse_incomplete" in result["warnings"]

    def test_effective_price_implausible(self):
        result = finalize_invoice(_basis_raw(
            zeitraum_von="01.01.2025", zeitraum_bis="31.12.2025",
            verbrauch_kwh=3500.0, rechnungsbetrag_brutto_eur=49000.0,
        ))
        assert any(w.startswith("effective_price_implausible") for w in result["warnings"])

    def test_invoice_modell_traegt_warnings(self):
        inv = Invoice(**finalize_invoice(_basis_raw()))
        assert "rechnungsbetrag_missing" in inv.warnings
