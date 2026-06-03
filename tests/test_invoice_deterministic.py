# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests for the deterministic invoice path + the Rechenweg / no-silent-defaults.

The LLM/OCR extraction moved to gridbert; energietools' invoice path is now
deterministic-only and emits an auditable ``rechenweg`` (which Arbeitspreis plan,
candidates, UST factor, whether the billing period was known, plausibility hints).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from energietools.models.invoice import Invoice
from energietools.tools.invoice_parser import finalize_invoice, parse_invoice


def test_finalize_emits_rechenweg_with_plan_and_ust() -> None:
    raw = {
        "lieferant": "Testenergie",
        "arbeitspreis_ct_kwh": 10.0,
        "arbeitspreis_ist_netto": True,
        "verbrauch_kwh": 3000,
        "plz": "1010",
        "zeitraum_von": "01.01.2025",
        "zeitraum_bis": "31.12.2025",
    }
    result = finalize_invoice(raw)
    rw = result["rechenweg"]
    # 10 ct/kWh netto -> 12 ct/kWh brutto (UST 1.2), via Plan A.
    assert result["energiepreis_ct_kwh"] == 12.0
    assert rw["arbeitspreis_ct_kwh_brutto"] == 12.0
    assert rw["ust_faktor"] == 1.2
    assert rw["arbeitspreis_kandidaten_ct_kwh_brutto"]["plan_a"] == 12.0
    assert "A" in rw["arbeitspreis_plan"]
    assert rw["zeitraum_bekannt"] is True


def test_finalize_flags_unknown_period_as_assumption() -> None:
    # No zeitraum -> the 12-month assumption must be surfaced, not silent.
    raw = {"lieferant": "X", "arbeitspreis_ct_kwh": 10.0, "verbrauch_kwh": 3000, "plz": "1010"}
    rw = finalize_invoice(raw)["rechenweg"]
    assert rw["zeitraum_bekannt"] is False
    assert any("12 Monate" in h for h in rw["hinweise"])


def test_finalize_flags_implausible_arbeitspreis() -> None:
    # 200 ct/kWh is outside the plausibility band -> a hint must appear.
    raw = {"lieferant": "X", "arbeitspreis_ct_kwh": 200.0, "verbrauch_kwh": 3000, "plz": "1010"}
    rw = finalize_invoice(raw)["rechenweg"]
    assert any("Plausibilitätsgrenzen" in h for h in rw["hinweise"])


def test_invoice_model_carries_rechenweg() -> None:
    raw = {"lieferant": "X", "arbeitspreis_ct_kwh": 10.0, "verbrauch_kwh": 3000, "plz": "1010"}
    inv = Invoice(**finalize_invoice(raw))
    assert isinstance(inv.rechenweg, dict)
    assert inv.rechenweg["ust_faktor"] == 1.2


def test_parse_invoice_rejects_non_pdf(tmp_path: Path) -> None:
    # No LLM/OCR in the open core: images/scans belong to gridbert.
    img = tmp_path / "rechnung.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError, match="Text-PDF"):
        parse_invoice(img)


def test_parse_invoice_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        parse_invoice(Path("/tmp/definitely-missing-energietools-invoice.pdf"))
