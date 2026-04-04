# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests for deterministic invoice extraction (regex-based)."""

from __future__ import annotations

import pytest

from energietools.tools.invoice_parser import (
    _extract_deterministic_from_text,
    _parse_austrian_number,
)


class TestParseAustrianNumber:
    def test_comma_decimal(self):
        assert _parse_austrian_number("13.666,99", expect_large=True) == 13666.99

    def test_dot_thousands(self):
        assert _parse_austrian_number("3.240", expect_large=True) == 3240.0

    def test_dot_decimal_small(self):
        assert _parse_austrian_number("3.240", expect_large=False) == 3.240


class TestVerbrauchExtraction:
    """Tests for kWh consumption extraction — the most critical field."""

    def test_sturm_energie_wurden_verbraucht(self):
        """Sturm Energie: 'wurden 13.666,99 kWh verbraucht' on page 1."""
        text = (
            "Wien, am 15.09.2025\n"
            "Im Rechnungszeitraum 01.07.2024 -04.07.2025 wurden 13.666,99 kWh verbraucht.\n"
            "Abrechnung Betrag in €\n"
            "Energie 2.085,50 €\n"
            # Page 4 — daily consumption, must NOT be picked up as total
            "Verbrauch in der vorherigen Abrechnungsperiode 58 kWh/Tag (192 Tage, 11.191 kWh)\n"
            "Verbrauch in der aktuellen Abrechnungsperiode 37 kWh/Tag(369 Tage, 13.667 kWh)\n"
            # Need enough text to pass 200 char minimum
            "Anlagenadresse: 1220 Wien, Reiherweg 18\n"
            "Zählpunkt: AT0010000000000000001000009211706\n"
        )
        result = _extract_deterministic_from_text(text)
        assert result is not None
        assert result["verbrauch_kwh"] == 13666.99

    def test_kwh_per_tag_not_matched(self):
        """'kWh/Tag' values must NOT be extracted as total consumption."""
        text = (
            "Anlagenadresse: 1220 Wien, Reiherweg 18\n"
            "Zählpunkt: AT0010000000000000001000009211706\n"
            "Verbrauch in der vorherigen Abrechnungsperiode 58 kWh/Tag (192 Tage)\n"
            "Verbrauch in der aktuellen Abrechnungsperiode 37 kWh/Tag (369 Tage)\n"
            "x" * 200  # padding to pass min length check
        )
        result = _extract_deterministic_from_text(text)
        # Should NOT pick up 58 or 37 as verbrauch
        if result and "verbrauch_kwh" in result:
            assert result["verbrauch_kwh"] not in (58.0, 37.0), \
                f"Picked up daily rate as total consumption: {result['verbrauch_kwh']}"

    def test_wien_energie_aktuell_pattern(self):
        """Wien Energie: 'aktuell 3.240 kWh in 365 Tagen'."""
        text = (
            "aktuell 3.240 kWh in 365 Tagen\n"
            "Anlagenadresse: 1060 Wien\n"
            "x" * 200
        )
        result = _extract_deterministic_from_text(text)
        assert result is not None
        assert result["verbrauch_kwh"] == 3240.0

    def test_gesamtverbrauch_pattern(self):
        text = (
            "Gesamtverbrauch: 4.500 kWh\n"
            "Anlagenadresse: 1220 Wien\n"
            "x" * 200
        )
        result = _extract_deterministic_from_text(text)
        assert result is not None
        assert result["verbrauch_kwh"] == 4500.0


class TestZeitraumExtraction:
    def test_rechnungszeitraum(self):
        """Sturm Energie uses 'Rechnungszeitraum', not 'Abrechnungszeitraum'."""
        text = (
            "Im Rechnungszeitraum 01.07.2024 -04.07.2025 wurden 13.666,99 kWh verbraucht.\n"
            "Anlagenadresse: 1220 Wien\n"
            "Rechnungszeitraum 01.07.2024 -04.07.2025\n"
            "x" * 200
        )
        result = _extract_deterministic_from_text(text)
        assert result is not None
        assert result.get("zeitraum_von") == "01.07.2024"
        assert result.get("zeitraum_bis") == "04.07.2025"

    def test_abrechnungszeitraum(self):
        text = (
            "Abrechnungszeitraum: 01.01.2024 - 31.12.2024\n"
            "aktuell 3.240 kWh in 365 Tagen\n"
            "Anlagenadresse: 1060 Wien\n"
            "x" * 200
        )
        result = _extract_deterministic_from_text(text)
        assert result is not None
        assert result.get("zeitraum_von") == "01.01.2024"
        assert result.get("zeitraum_bis") == "31.12.2024"


class TestEnergieartDetection:
    """Tests for Invoice.energieart field set by _postprocess_llm_output."""

    def _postprocess(self, raw: dict) -> dict:
        from energietools.tools.invoice_parser import _postprocess_llm_output
        return _postprocess_llm_output(raw)

    def test_plain_strom_invoice(self):
        raw = {"lieferant": "Wien Energie", "tarif_name": "Optima", "verbrauch_kwh": 3240, "plz": "1090"}
        result = self._postprocess(raw)
        assert result.get("energieart") == "strom"
        assert result.get("gas") is None

    def test_plain_gas_invoice_via_section(self):
        raw = {"gas": {"lieferant": "Wien Energie", "tarif_name": "Gas Optima", "verbrauch_kwh": 12000}, "plz": "1090"}
        result = self._postprocess(raw)
        assert result.get("energieart") == "gas"

    def test_gas_detected_by_tarif_heuristic(self):
        raw = {"lieferant": "Wien Energie", "tarif_name": "Erdgas Classic", "verbrauch_kwh": 12000, "plz": "1090"}
        result = self._postprocess(raw)
        assert result.get("energieart") == "gas"

    def test_kombi_invoice(self):
        raw = {
            "strom": {"lieferant": "Wien Energie", "tarif_name": "Optima", "verbrauch_kwh": 3240},
            "gas": {"lieferant": "Wien Energie", "tarif_name": "Gas Optima", "verbrauch_kwh": 12000},
            "plz": "1090",
        }
        result = self._postprocess(raw)
        assert result.get("energieart") == "kombi"
        assert result.get("gas") is not None
        assert result["gas"].jahresverbrauch_kwh == 12000.0

    def test_kombi_preserves_strom_as_main(self):
        raw = {
            "strom": {"lieferant": "WE Strom", "verbrauch_kwh": 3000, "arbeitspreis_ct_kwh": 15.0},
            "gas": {"lieferant": "WE Gas", "verbrauch_kwh": 10000, "arbeitspreis_ct_kwh": 8.0},
            "plz": "1060",
        }
        result = self._postprocess(raw)
        assert result.get("energieart") == "kombi"
        # Main fields should be from strom
        assert result.get("lieferant") == "WE Strom"

    def test_strom_gas_in_tarif_name_is_not_gas(self):
        """'Strom & Gas' in tarif name should not be classified as gas."""
        raw = {"lieferant": "Wien Energie", "tarif_name": "Strom & Gas Kombi", "verbrauch_kwh": 3240, "plz": "1090"}
        result = self._postprocess(raw)
        assert result.get("energieart") == "strom"
