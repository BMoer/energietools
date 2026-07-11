# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Capability-Hüllen der Rechnungs-Fakten (B.5).

``validate_invoice_facts``: strikte D2.2-Validierung mit Rejection-Semantik —
bei Verstoß strukturierte Fehler + Rückfragen ans (User-)LLM, nichts wird
gespeichert. ``finalize_invoice``: validiert UND rechnet deterministisch
weiter (Arbeitspreis-Pläne A/B/C, Cross-Check, Hochrechnung, Hauptmetrik
``jahreskosten_brutto_eur``) — Result mit lückenlosem ``rechenweg`` +
``warnings``. Strom, Gas und Kombi (§6 F6).
"""

from __future__ import annotations

from importlib import metadata
from typing import Any

from energietools.capabilities.base import Capability, CapabilityRejection
from energietools.capabilities.invoice.facts import InvoiceFacts, pruefe_invoice_facts

_REJECTION_HINWEIS = (
    "Nichts wurde gespeichert. Korrigiere die Felder und rufe das Tool erneut auf."
)

_FACTS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "Wörtlich von der Rechnung transkribierte Fakten (InvoiceFacts, D2.2). "
        "Beträge NIE umrechnen — ist_netto-Flag setzen; Preise in ct/kWh "
        "(wert_ct_kwh), Summen in EUR (wert_eur)."
    ),
    "properties": {
        "energieart": {"type": "string", "enum": ["strom", "gas", "kombi"]},
        "lieferant": {"type": "string", "minLength": 2},
        "tarif_name": {"type": ["string", "null"]},
        "zeitraum_von": {"type": "string", "format": "date"},
        "zeitraum_bis": {"type": "string", "format": "date"},
        "verbrauch_kwh": {"type": "number", "exclusiveMinimum": 0},
        "plz": {"type": "string", "pattern": "^\\d{4}$"},
        "zaehlpunkt": {
            "type": ["string", "null"],
            "description": "AT + 31 Ziffern (33 Zeichen), Ziffer für Ziffer abtippen",
        },
        "summe_energieentgelte": {"$ref": "#/$defs/betrag"},
        "summe_netzentgelte": {"$ref": "#/$defs/betrag"},
        "summe_steuern_abgaben": {"$ref": "#/$defs/betrag"},
        "rechnungsbetrag_brutto_eur": {"type": ["number", "null"]},
        "grundgebuehr": {
            "type": ["object", "null"],
            "properties": {
                "wert_eur": {"type": "number"},
                "zeitraum": {"type": "string", "enum": ["monat", "jahr"]},
                "ist_netto": {"type": "boolean"},
            },
            "required": ["wert_eur", "zeitraum", "ist_netto"],
            "additionalProperties": False,
        },
        "arbeitspreis": {
            "type": ["object", "null"],
            "properties": {
                "wert_ct_kwh": {"type": "number"},
                "ist_netto": {"type": "boolean"},
            },
            "required": ["wert_ct_kwh", "ist_netto"],
            "additionalProperties": False,
        },
        "jahresverbrauch_prognose_kwh": {"type": ["number", "null"]},
        "anlagen_adresse": {"type": ["string", "null"]},
        "quellen_anker": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "feld": {"type": "string"},
                    "zitat": {"type": "string", "minLength": 3},
                    "seite": {"type": ["integer", "null"]},
                },
                "required": ["feld", "zitat"],
                "additionalProperties": False,
            },
            "description": "Mind. je ein wörtliches Zitat für Verbrauch und einen Betrag",
        },
    },
    "required": [
        "energieart", "lieferant", "zeitraum_von", "zeitraum_bis",
        "verbrauch_kwh", "plz", "quellen_anker",
    ],
    "$defs": {
        "betrag": {
            "type": ["object", "null"],
            "properties": {
                "wert_eur": {"type": "number"},
                "ist_netto": {"type": "boolean"},
            },
            "required": ["wert_eur", "ist_netto"],
            "additionalProperties": False,
        },
    },
}


def _paket_version() -> str:
    try:
        return metadata.version("energietools")
    except metadata.PackageNotFoundError:
        return "dev"


def _validiere_oder_rejecte(kwargs: dict[str, Any]) -> InvoiceFacts:
    """Gemeinsamer Validierungs-Einstieg beider Capabilities (Rejection-Semantik)."""
    payload = kwargs.get("facts") if isinstance(kwargs.get("facts"), dict) else kwargs
    facts, fehler = pruefe_invoice_facts(dict(payload))
    if facts is None:
        raise CapabilityRejection(_REJECTION_HINWEIS, fehler)
    return facts


def facts_zu_rohdict(facts: InvoiceFacts) -> dict[str, Any]:
    """Mappt validierte InvoiceFacts auf das Roh-Dict von ``finalize_invoice``.

    Deterministische Feld-Übersetzung (keine Berechnung): Datumsfelder ins
    TT.MM.JJJJ-Format des Parsers, Netto-Flags 1:1, Beträge unverändert.
    """
    raw: dict[str, Any] = {
        "energieart": facts.energieart,
        "lieferant": facts.lieferant,
        "tarif_name": facts.tarif_name or "",
        "plz": facts.plz,
        "zaehlpunkt": facts.zaehlpunkt or "",
        "adresse": facts.anlagen_adresse or "",
        "verbrauch_kwh": facts.verbrauch_kwh,
        "zeitraum_von": facts.zeitraum_von.strftime("%d.%m.%Y"),
        "zeitraum_bis": facts.zeitraum_bis.strftime("%d.%m.%Y"),
    }
    if facts.arbeitspreis is not None:
        raw["arbeitspreis_ct_kwh"] = facts.arbeitspreis.wert_ct_kwh
        raw["arbeitspreis_ist_netto"] = facts.arbeitspreis.ist_netto
    if facts.grundgebuehr is not None:
        raw["grundgebuehr_eur"] = facts.grundgebuehr.wert_eur
        raw["grundgebuehr_zeitraum"] = facts.grundgebuehr.zeitraum
        raw["grundgebuehr_ist_netto"] = facts.grundgebuehr.ist_netto
    if facts.summe_energieentgelte is not None:
        raw["summe_energieentgelte_eur"] = facts.summe_energieentgelte.wert_eur
        raw["summe_energieentgelte_ist_netto"] = facts.summe_energieentgelte.ist_netto
    if facts.summe_netzentgelte is not None:
        raw["summe_netzentgelte_eur"] = facts.summe_netzentgelte.wert_eur
        raw["summe_netzentgelte_ist_netto"] = facts.summe_netzentgelte.ist_netto
    if facts.summe_steuern_abgaben is not None:
        raw["summe_steuern_abgaben_eur"] = facts.summe_steuern_abgaben.wert_eur
        raw["summe_steuern_abgaben_ist_netto"] = facts.summe_steuern_abgaben.ist_netto
    if facts.rechnungsbetrag_brutto_eur is not None:
        raw["rechnungsbetrag_brutto_eur"] = facts.rechnungsbetrag_brutto_eur
    if facts.jahresverbrauch_prognose_kwh is not None:
        raw["jahresverbrauch_prognose_kwh"] = facts.jahresverbrauch_prognose_kwh
    return raw


class ValidateInvoiceFactsCapability(Capability):
    """Validiert LLM-transkribierte Rechnungs-Fakten strikt (D2.2, Rejection)."""

    name = "validate_invoice_facts"
    summary = (
        "Validiert von einem LLM wörtlich transkribierte Rechnungs-Fakten "
        "(Strom/Gas/Kombi) strikt und deterministisch: Schema, Plausibilitäts- "
        "grenzen, Cross-Field-Checks, Zählpunkt-Kanon, Quellen-Anker. Bei "
        "Verstoß: strukturierte Fehler mit Rückfragen — nichts wird gespeichert."
    )
    input_schema = _FACTS_INPUT_SCHEMA

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "quelle": "invoice-facts-schema (D2.2)",
            "stand": "deterministische Validierung, kein Snapshot",
            "snapshot_version": _paket_version(),
        }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        facts = _validiere_oder_rejecte(kwargs)
        return {
            "valid": True,
            "facts": facts.model_dump(mode="json"),
            "hinweis": "Alle Prüfungen bestanden — Fakten sind rechenbereit.",
        }


class FinalizeInvoiceCapability(Capability):
    """Validiert Fakten und rechnet sie deterministisch zur Invoice auf (mit Rechenweg)."""

    name = "finalize_invoice"
    summary = (
        "Validiert Rechnungs-Fakten (wie validate_invoice_facts) und rechnet sie "
        "deterministisch auf: Arbeitspreis-Herleitung (Plan A/B/C mit Cross-Check), "
        "Netto/Brutto, Hochrechnung <300 Tage (EVU-Prognose im ±30%-Fenster), "
        "jahreskosten_brutto_eur als Hauptmetrik. Result mit lückenlosem rechenweg "
        "+ warnings. Kein LLM — jede €-Zahl nachrechenbar."
    )
    input_schema = _FACTS_INPUT_SCHEMA

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "quelle": "energietools.tools.invoice_parser.finalize_invoice",
            "stand": "deterministische Rechnung, kein Snapshot",
            "snapshot_version": _paket_version(),
        }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        from energietools.models import Invoice
        from energietools.tools.invoice_parser import finalize_invoice

        facts = _validiere_oder_rejecte(kwargs)
        ergebnis = finalize_invoice(facts_zu_rohdict(facts))
        invoice = Invoice(**ergebnis)
        return {
            "invoice": invoice.model_dump(mode="json"),
            "rechenweg": invoice.rechenweg,
            "warnings": invoice.warnings,
        }
