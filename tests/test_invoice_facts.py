# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für das validierende Fakten-Schema (B.5, D2.2) + die Capability-Hüllen.

Kern-Semantik: STRIKT + Rejection — Garbage wird abgelehnt, nie zu 0.0
koerziert (kein ``_safe_float``-Erbe). Strom, Gas UND Kombi (§6 F6).
"""

from __future__ import annotations

import json

import pytest

from energietools.capabilities.base import CapabilityResult
from energietools.capabilities.invoice import (
    FinalizeInvoiceCapability,
    ValidateInvoiceFactsCapability,
    pruefe_invoice_facts,
)


def _anker_fuer(verbrauch, rechnungsbetrag) -> list[dict]:
    """Quellen-Anker, deren Zitat den transkribierten WERT enthält (D2.2-Anker-
    Gate prüft seit dem Härtungs-Fix exakten Feldnamen + Wert-Beleg im Zitat)."""
    anker = [{"feld": "verbrauch_kwh", "zitat": f"Verbrauch laut Zaehler: {verbrauch} kWh", "seite": 2}]
    if rechnungsbetrag is not None:
        anker.append({
            "feld": "rechnungsbetrag_brutto_eur",
            "zitat": f"Rechnungsbetrag inkl. USt: {rechnungsbetrag}",
        })
    return anker


def _payload(**overrides) -> dict:
    """Gültiges Basis-Payload (synthetische Rechnung, keine echten Kundendaten)."""
    base = {
        "energieart": "strom",
        "lieferant": "Testkraft Energie GmbH",
        "tarif_name": "Fix Basis 2026",
        "zeitraum_von": "2025-01-01",
        "zeitraum_bis": "2025-12-31",
        "verbrauch_kwh": 3500.0,
        "plz": "1060",
        "zaehlpunkt": "AT0010000000000000000000000012345",
        "summe_energieentgelte": {"wert_eur": 700.0, "ist_netto": True},
        "grundgebuehr": {"wert_eur": 5.0, "zeitraum": "monat", "ist_netto": True},
        "arbeitspreis": {"wert_ct_kwh": 18.0, "ist_netto": True},
        "rechnungsbetrag_brutto_eur": 1200.0,
        "anlagen_adresse": "Musterstraße 12, 1060 Wien",
        # Default-Anker belegen 3.500 kWh und 1.200,00 EUR wörtlich.
        "quellen_anker": [
            {"feld": "verbrauch_kwh", "zitat": "wurden 3.500 kWh verbraucht", "seite": 2},
            {"feld": "rechnungsbetrag_brutto_eur", "zitat": "Rechnungsbetrag inkl. USt 1.200,00"},
        ],
    }
    base.update(overrides)
    # Werden die belegpflichtigen Zahlen überschrieben (ohne eigene Anker), die
    # Anker mitziehen, damit ihr Zitat den neuen Wert weiter wörtlich belegt.
    if "quellen_anker" not in overrides and (
        "verbrauch_kwh" in overrides or "rechnungsbetrag_brutto_eur" in overrides
    ):
        base["quellen_anker"] = _anker_fuer(
            base["verbrauch_kwh"], base.get("rechnungsbetrag_brutto_eur"),
        )
    return base


def _regeln(fehler: list[dict]) -> set[str]:
    return {f["regel"] for f in fehler}


# =============================================================================
# 1. Schema strikt: keine stille Koersion (kein _safe_float-Erbe)
# =============================================================================


class TestSchemaStrikt:
    def test_gueltiges_payload_passiert(self):
        facts, fehler = pruefe_invoice_facts(_payload())
        assert fehler == []
        assert facts is not None
        assert facts.verbrauch_kwh == 3500.0

    @pytest.mark.parametrize("feld, wert", [
        ("verbrauch_kwh", "3500"),          # String statt Zahl → Reject, nicht float()
        ("verbrauch_kwh", None),
        ("rechnungsbetrag_brutto_eur", "1200,50"),
        ("lieferant", 42),
    ])
    def test_falscher_typ_wird_rejected_nicht_koerziert(self, feld, wert):
        facts, fehler = pruefe_invoice_facts(_payload(**{feld: wert}))
        assert facts is None
        assert any(f["feld"].startswith(feld.split(".")[0]) for f in fehler)
        assert all("rueckfrage" in f and f["rueckfrage"] for f in fehler)

    def test_betrag_braucht_ist_netto_pflicht(self):
        facts, fehler = pruefe_invoice_facts(
            _payload(summe_energieentgelte={"wert_eur": 700.0}),
        )
        assert facts is None  # keine Default-Annahme netto/brutto

    def test_unbekannte_felder_verboten(self):
        facts, fehler = pruefe_invoice_facts(_payload(energiepreis_eur_kwh=0.18))
        assert facts is None

    def test_plz_regex(self):
        facts, _ = pruefe_invoice_facts(_payload(plz="10"))
        assert facts is None

    def test_energieart_strom_gas_kombi(self):
        # §6 F6: alle drei Energiearten werden angenommen.
        for art in ("strom", "gas", "kombi"):
            facts, fehler = pruefe_invoice_facts(_payload(energieart=art))
            assert fehler == [], f"{art}: {fehler}"
            assert facts.energieart == art

    def test_zeitraum_bis_muss_nach_von(self):
        facts, fehler = pruefe_invoice_facts(
            _payload(zeitraum_von="2025-12-31", zeitraum_bis="2025-01-01"),
        )
        assert facts is None
        assert "zeitraum_bis_nach_von" in _regeln(fehler)


# =============================================================================
# 2. Plausibilität + Zählpunkt-Kanon + Pflichtfeld-Gate + Anker
# =============================================================================


class TestRegeln:
    def test_arbeitspreis_412_ct_rejected(self):
        # Das D2.2-Beispiel: 412 ct/kWh (EUR/kWh-Verwechslung) → Rückfrage.
        facts, fehler = pruefe_invoice_facts(
            _payload(arbeitspreis={"wert_ct_kwh": 412.0, "ist_netto": False}),
        )
        assert facts is None
        f = next(f for f in fehler if f["feld"] == "arbeitspreis")
        assert f["wert"] == 412.0
        assert "ct/kWh" in f["rueckfrage"]

    def test_zaehlpunkt_32_statt_33_zeichen_rejected(self):
        # Exakt die WP-C-Fehlerklasse: eine Ziffer verschluckt.
        facts, fehler = pruefe_invoice_facts(
            _payload(zaehlpunkt="AT001000000000000000000000001234"),
        )
        assert facts is None
        assert "zaehlpunkt_at_33_stellen" in _regeln(fehler)

    def test_zaehlpunkt_mit_punkten_wird_kanonisiert(self):
        # AT + 6 (VKZ) + 5 (Anlagengruppe) + 20 (Anlagencode) = 33 Zeichen kanonisch.
        facts, fehler = pruefe_invoice_facts(
            _payload(zaehlpunkt="AT.001000.00000.00000000000000012345"),
        )
        assert fehler == []

    def test_pflichtfeld_gate_arbeitspreis_oder_energiesumme(self):
        facts, fehler = pruefe_invoice_facts(
            _payload(arbeitspreis=None, summe_energieentgelte=None),
        )
        assert facts is None
        assert "pflichtfeld_arbeitspreis_oder_energiesumme" in _regeln(fehler)

    def test_anker_pflicht_fuer_verbrauch_und_betrag(self):
        facts, fehler = pruefe_invoice_facts(_payload(quellen_anker=[
            {"feld": "lieferant", "zitat": "Testkraft Energie GmbH"},
        ]))
        assert facts is None
        assert {"anker_verbrauch_fehlt", "anker_betrag_fehlt"} <= _regeln(fehler)

    def test_brutto_floor_30_eur(self):
        facts, fehler = pruefe_invoice_facts(_payload(rechnungsbetrag_brutto_eur=4.22))
        assert facts is None
        regeln = _regeln(fehler)
        assert "brutto_floor_30_eur" in regeln or "plausibilitaet_5_50000_eur" in regeln

    def test_effektivpreis_anker(self):
        # 3500 kWh, aber 60 EUR Rechnungsbetrag → einzelne Preiszeile erwischt.
        facts, fehler = pruefe_invoice_facts(_payload(rechnungsbetrag_brutto_eur=60.0))
        assert facts is None
        assert "effektivpreis_anker_5_100_ct" in _regeln(fehler)

    def test_netto_brutto_konsistenz(self):
        # Alle drei Netto-Blöcke + Brutto: 700+300+100=1100 × 1,2 = 1320 ≈ ok;
        # 2000 EUR Rechnungsbetrag wäre >15 % daneben → Reject.
        ok_payload = _payload(
            summe_netzentgelte={"wert_eur": 300.0, "ist_netto": True},
            summe_steuern_abgaben={"wert_eur": 100.0, "ist_netto": True},
            rechnungsbetrag_brutto_eur=1320.0,
        )
        facts, fehler = pruefe_invoice_facts(ok_payload)
        assert fehler == []
        schief = dict(ok_payload, rechnungsbetrag_brutto_eur=2000.0)
        facts, fehler = pruefe_invoice_facts(schief)
        assert facts is None
        assert "netto_brutto_konsistenz" in _regeln(fehler)

    def test_anker_bypass_mit_verwandten_feldnamen_wird_erkannt(self):
        # Fund 3: thematisch verwandte, aber NICHT exakte Feldnamen (Substring-
        # Schlupfloch) dürfen das Anker-Gate nicht mehr erfüllen.
        facts, fehler = pruefe_invoice_facts(_payload(quellen_anker=[
            {"feld": "verbrauchszeitraum", "zitat": "Verbrauchszeitraum: 01.01.2025 - 31.12.2025"},
            {"feld": "grundgebuehrhinweis", "zitat": "siehe AGB Punkt 4 zur Grundgebuehr"},
        ]))
        assert facts is None
        assert {"anker_verbrauch_fehlt", "anker_betrag_fehlt"} <= _regeln(fehler)

    def test_anker_exakter_feldname_aber_wert_fehlt_im_zitat(self):
        # Fund 3: exakter Feldname, aber der transkribierte Wert fehlt im Zitat.
        facts, fehler = pruefe_invoice_facts(_payload(quellen_anker=[
            {"feld": "verbrauch_kwh", "zitat": "Verbrauch laut Jahresabrechnung"},
            {"feld": "rechnungsbetrag_brutto_eur", "zitat": "Rechnungsbetrag inkl. USt: 1.200,00"},
        ]))
        assert facts is None
        assert "anker_verbrauch_fehlt" in _regeln(fehler)
        assert "anker_betrag_fehlt" not in _regeln(fehler)  # Betrag korrekt belegt

    def test_anker_wert_mit_deutscher_und_repr_schreibweise(self):
        # Wert-Match ist separator-tolerant: 3.500 (de) und 3500.0 (repr) belegen 3500.
        for zitat in ("3.500 kWh abgelesen", "3500.0 kWh abgelesen", "3 500 kWh"):
            facts, fehler = pruefe_invoice_facts(_payload(quellen_anker=[
                {"feld": "verbrauch_kwh", "zitat": zitat},
                {"feld": "rechnungsbetrag_brutto_eur", "zitat": "Endbetrag 1.200,00 EUR"},
            ]))
            assert fehler == [], f"{zitat}: {fehler}"

    def test_plz_lehnt_unicode_ziffern_ab(self):
        # Fund 4: arabisch-indische + Fullwidth-Ziffern sind keine gültige PLZ.
        for plz in ("١٠٦٠", "１０６０"):  # 1060
            facts, _ = pruefe_invoice_facts(_payload(plz=plz))
            assert facts is None, f"PLZ {plz!r} darf nicht akzeptiert werden"

    def test_datum_lehnt_unix_timestamp_ab(self):
        # Fund 5: Int/Float-Unixzeitstempel dürfen nicht still als Datum gelten.
        for ts in (1735689600, 1735689600.0):
            facts, fehler = pruefe_invoice_facts(_payload(zeitraum_von=ts))
            assert facts is None, f"Timestamp {ts!r} darf kein Datum sein"
            assert any(f["feld"].startswith("zeitraum_von") for f in fehler)
        # ISO-String bleibt gültig.
        facts, fehler = pruefe_invoice_facts(_payload(zeitraum_von="2025-01-01"))
        assert fehler == []

    def test_quellen_anker_seite_strict_kein_string(self):
        # Fund 6: QuellenAnker.seite darf String-Koersion nicht zulassen (strict).
        facts, fehler = pruefe_invoice_facts(_payload(quellen_anker=[
            {"feld": "verbrauch_kwh", "zitat": "3.500 kWh", "seite": "2"},
            {"feld": "rechnungsbetrag_brutto_eur", "zitat": "1.200,00 EUR"},
        ]))
        assert facts is None
        assert any(f["feld"].startswith("quellen_anker") for f in fehler)

    def test_prognose_fenster_30_pct(self):
        # Halbjahr, 1750 kWh → Hochrechnung ≈ 3520 kWh; Prognose 9000 → Reject.
        payload = _payload(
            zeitraum_von="2025-01-01", zeitraum_bis="2025-07-01",
            verbrauch_kwh=1750.0, rechnungsbetrag_brutto_eur=600.0,
            jahresverbrauch_prognose_kwh=9000.0,
        )
        facts, fehler = pruefe_invoice_facts(payload)
        assert facts is None
        assert "prognose_fenster_30_pct" in _regeln(fehler)
        # Im Fenster (3600) → ok.
        payload["jahresverbrauch_prognose_kwh"] = 3600.0
        facts, fehler = pruefe_invoice_facts(payload)
        assert fehler == []


# =============================================================================
# 3. Capability-Envelope: Rejection-Semantik (D2.2) + meta (B.6)
# =============================================================================


class TestZaehlpunktAscii:
    """Fund 4: der Zählpunkt-Kanon darf nur ASCII-Ziffern als strikt gültig führen."""

    def test_strict_lehnt_nicht_ascii_ziffern_ab(self):
        from energietools.tools.zaehlpunkt import validate

        zp = "AT" + "٠" * 31  # AT + 31× arabisch-indische Null
        res = validate(zp)
        assert res.valid_strict is False

    def test_ascii_standardform_bleibt_gueltig(self):
        from energietools.tools.zaehlpunkt import validate

        assert validate("AT0010000000000000000000000012345").valid_strict is True

    def test_facts_lehnt_nicht_ascii_zaehlpunkt_ab(self):
        zp = "AT" + "٠" * 31
        facts, fehler = pruefe_invoice_facts(_payload(zaehlpunkt=zp))
        assert facts is None
        assert "zaehlpunkt_at_33_stellen" in _regeln(fehler)


class TestValidateCapability:
    def test_erfolg(self):
        result = ValidateInvoiceFactsCapability().run(**_payload())
        assert isinstance(result, CapabilityResult)
        assert result.ok is True
        assert result.data["valid"] is True
        assert result.data["facts"]["plz"] == "1060"
        assert result.meta.get("quelle")
        json.dumps(result.model_dump(mode="json"))  # stdlib-json-fähig (date → ISO)

    def test_rejection_struktur_nach_d22(self):
        result = ValidateInvoiceFactsCapability().run(
            **_payload(arbeitspreis={"wert_ct_kwh": 412.0, "ist_netto": False}),
        )
        assert result.ok is False
        assert "Nichts wurde gespeichert" in result.error
        fehler = result.data["fehler"]
        assert fehler and all(
            {"feld", "regel", "wert", "rueckfrage"} <= set(f) for f in fehler
        )
        assert result.data["hinweis"] == result.error

    def test_facts_nested_unter_facts_key(self):
        result = ValidateInvoiceFactsCapability().run(facts=_payload())
        assert result.ok is True


class TestFinalizeCapability:
    def test_finalize_rechnet_mit_rechenweg_und_hauptmetrik(self):
        result = FinalizeInvoiceCapability().run(**_payload())
        assert result.ok is True
        inv = result.data["invoice"]
        # Plan A: 18 ct netto → 21,6 ct brutto
        assert inv["energiepreis_ct_kwh"] == pytest.approx(21.6)
        # Hauptmetrik: Jahreszeitraum → Rechnungsbetrag = Jahreskosten
        assert inv["jahreskosten_brutto_eur"] == pytest.approx(1200.0)
        assert inv["rechnungsbetrag_brutto_eur"] == pytest.approx(1200.0)
        rw = result.data["rechenweg"]
        assert rw["arbeitspreis_plan"]
        assert rw["ust_faktor"] == 1.2
        assert isinstance(result.data["warnings"], list)
        json.dumps(result.model_dump(mode="json"))

    def test_finalize_teilzeitraum_hochrechnung(self):
        # Halbjahr (181 Tage): Verbrauch + Rechnungsbetrag werden annualisiert.
        result = FinalizeInvoiceCapability().run(**_payload(
            zeitraum_von="2025-01-01", zeitraum_bis="2025-07-01",
            verbrauch_kwh=1750.0, rechnungsbetrag_brutto_eur=600.0,
            summe_energieentgelte={"wert_eur": 350.0, "ist_netto": True},
        ))
        assert result.ok is True
        inv = result.data["invoice"]
        assert inv["ist_hochgerechnet"] is True
        assert inv["jahresverbrauch_kwh"] == pytest.approx(1750.0 * 365 / 181, rel=1e-3)
        assert inv["jahreskosten_brutto_eur"] == pytest.approx(600.0 * 365 / 181, rel=1e-3)

    def test_finalize_rejected_bei_garbage(self):
        result = FinalizeInvoiceCapability().run(**_payload(verbrauch_kwh="viel"))
        assert result.ok is False
        assert result.data["fehler"]

    def test_finalize_gas_und_kombi(self):
        for art in ("gas", "kombi"):
            result = FinalizeInvoiceCapability().run(**_payload(energieart=art))
            assert result.ok is True, f"{art}: {result.error}"
            assert result.data["invoice"]["energieart"] == art
