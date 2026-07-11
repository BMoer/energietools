# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Capability-Hülle des Tarifvergleichs (B.1/B.3).

Default-Result ist KOMPAKT: Top-N Alternativen mit Rechenweg-Kurzform (eine
auditierbare Zeile je Tarif). Der volle Rechenweg jeder Alternative ist on
demand abrufbar (``rechenweg="voll"``) — DoD "Rechenweg abrufbar für ALLE
Alternativen" OHNE das ~150k-Zeichen-Tool-Result-Limit zu reißen (B.3).
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.invoice.facts import PLAUSIBILITAET as _INVOICE_PLAUSIBILITAET
from energietools.capabilities.tariff_compare.compare import vergleiche_tarife
from energietools.capabilities.tariff_compare.protocols import SpotPriceSource, TariffSource
from energietools.capabilities.tariff_compare.sources import (
    CatalogTariffSource,
    SnapshotSpotPriceSource,
)
from energietools.models import (
    Rechenweg,
    Tariff,
    TariffComparison,
    VersorgerAbdeckungBlock,
)

_DEFAULT_TOP_N = 10
_MAX_TOP_N = 100

# Plausibilitätsfenster für die aktuellen Rechnungswerte — DIESELBE Quelle der
# Zahlen wie die invoice-Validierung (ct/kWh bzw. EUR/Monat, brutto). Ein
# falsch transkribierter (0/negativer/absurder) Wert wird abgelehnt statt still
# zu einer erfundenen Ersparnis verrechnet (No-LLM-Math, dieselbe Transkriptions-
# Fehlerklasse wie bei der Rechnung).
_EP_MIN_CT, _EP_MAX_CT = _INVOICE_PLAUSIBILITAET["arbeitspreis_ct_kwh"]
_GG_MIN_EUR, _GG_MAX_EUR = _INVOICE_PLAUSIBILITAET["grundgebuehr_eur_monat"]


def _feld_art(annotation: Any) -> str:
    """Grobe Art-Klassifikation eines Feld-Typs für das Linter-Schema."""
    import typing

    if typing.get_origin(annotation) in (list, tuple, set):
        return "list"
    if annotation in (int, float):
        return "number"
    if annotation is bool:
        return "bool"
    return "str"


def _versorger_abdeckung_pfade() -> dict[str, str]:
    """Trigger-adressierbare Feldpfade des ``versorger_abdeckung``-Blocks —
    aus dem Modell abgeleitet, damit ein Feld-Rename hier automatisch mitzieht
    (und ein veralteter Trigger dann sauber vom Linter gefangen wird)."""
    pfade: dict[str, str] = {}
    for name, feld in VersorgerAbdeckungBlock.model_fields.items():
        pfade[f"versorger_abdeckung.{name}"] = _feld_art(feld.annotation)
    for name in getattr(VersorgerAbdeckungBlock, "model_computed_fields", {}):
        pfade[f"versorger_abdeckung.{name}"] = "number"  # im_katalog_fehlend_anzahl (int)
    return pfade


def rechenweg_kurzform(rechenweg: Rechenweg | None, verbrauch_kwh: float) -> str:
    """Eine auditierbare Kurzform-Zeile des Rechenwegs (No-LLM-Math-Beleg).

    Kompakt genug für Top-N-Listen, vollständig genug zum Nachrechnen:
    Energie- und Grund-Netto, Rabatt, USt und Brutto-Endwert plus GA-Block.
    """
    if rechenweg is None:
        return ""
    rw = rechenweg
    teile = [
        f"{verbrauch_kwh:g} kWh × {rw.energiepreis_netto_ct_kwh:g} ct netto"
        f" = {rw.netto_energie_eur:.2f} €",
        f"+ GG 12 × {rw.grundgebuehr_netto_eur_monat:.2f} € = {rw.netto_grund_eur:.2f} €",
        f"= {rw.netto_gesamt_eur:.2f} € netto",
    ]
    if rw.neukundenrabatt_netto_eur:
        teile.append(
            f"− Rabatt {rw.neukundenrabatt_netto_eur:.2f} € = {rw.netto_nach_rabatt_eur:.2f} €",
        )
    teile.append(f"+ USt {rw.ust_eur:.2f} € = {rw.brutto_jahreskosten_eur:.2f} € brutto/Jahr")
    if rw.gebrauchsabgabe_eur:
        teile.append(f"(+ Gebrauchsabgabe {rw.gebrauchsabgabe_eur:.2f} € als eigener Block)")
    return "; ".join(teile)


def _tarif_eintrag(t: Tariff, verbrauch_kwh: float, *, voller_rechenweg: bool) -> dict[str, Any]:
    """Kompakter Ergebnis-Eintrag eines Tarifs (Kurzform; voll on demand)."""
    eintrag: dict[str, Any] = {
        "lieferant": t.lieferant,
        "tarif_name": t.tarif_name,
        "tariftyp": t.tariftyp,
        "kategorie": t.kategorie,
        "energiepreis_ct_kwh_brutto": t.energiepreis_ct_kwh,
        "grundgebuehr_eur_monat_brutto": t.grundgebuehr_eur_monat,
        "jahreskosten_eur": t.jahreskosten_eur,
        "jahreskosten_ohne_rabatt_eur": t.jahreskosten_ohne_rabatt_eur,
        "ersparnis_eur": t.ersparnis_eur,
        "gesamtkosten_eur": t.gesamtkosten_eur,
        "gebrauchsabgabe_eur": t.gebrauchsabgabe_eur,
        "ist_oekostrom": t.ist_oekostrom,
        "wechsel_link": t.wechsel_link,
        "rechenweg_kurz": rechenweg_kurzform(t.rechenweg, verbrauch_kwh),
    }
    if voller_rechenweg and t.rechenweg is not None:
        eintrag["rechenweg"] = t.rechenweg.model_dump(mode="json")
    return eintrag


def _result_dict(
    cmp: TariffComparison, *, top_n: int, voller_rechenweg: bool,
) -> dict[str, Any]:
    """Kompaktes, JSON-fähiges Vergleichs-Result (B.3-Format)."""
    verbrauch = cmp.jahresverbrauch_kwh
    alternativen = cmp.alternativen[:top_n]
    result: dict[str, Any] = {
        "plz": cmp.plz,
        "jahresverbrauch_kwh": verbrauch,
        "aktueller_tarif": _tarif_eintrag(
            cmp.aktueller_tarif, verbrauch, voller_rechenweg=voller_rechenweg,
        ),
        "alternativen": [
            _tarif_eintrag(t, verbrauch, voller_rechenweg=voller_rechenweg)
            for t in alternativen
        ],
        "anzahl_alternativen_gesamt": len(cmp.alternativen),
        "anzahl_im_result": len(alternativen),
        "max_ersparnis_eur": cmp.max_ersparnis_eur,
        "bester_gesamt": cmp.bester_gesamt.tarif_name if cmp.bester_gesamt else None,
        "netzkosten_eur_jahr": cmp.netzkosten_eur_jahr,
        "netzbetreiber": cmp.netzbetreiber,
        "gebrauchsabgabe_rate": cmp.gebrauchsabgabe_rate,
        "versorger_abdeckung": (
            cmp.versorger_abdeckung.model_dump(mode="json")
            if cmp.versorger_abdeckung is not None
            else None
        ),
        "hinweis": (
            "Alle Preise brutto (inkl. 20 % USt). Netzkosten und Gebrauchsabgabe sind "
            "reguliert/anbieterunabhängig und eigene Blöcke. Voller Rechenweg je "
            "Alternative via rechenweg='voll' abrufbar."
        ),
    }
    if not cmp.alternativen:
        result["hinweis"] = (
            "Keine passenden Alternativen im Katalog für diese Anfrage — leeres, "
            "gültiges Ergebnis (kein Fehler). " + result["hinweis"]
        )
    return result


class TariffCompareCapability(Capability):
    """Vergleicht einen aktuellen Stromtarif gegen die Tarife einer Quelle."""

    name = "tariff_compare"
    summary = (
        "Tarifvergleich für Österreich: vergleicht die aktuellen Rechnungswerte "
        "(brutto) gegen die Tarife der Datenquelle (Default: Open-Data-Katalog). "
        "Alle €-Zahlen mit auditierbarem Rechenweg (Kurzform im Default-Result, "
        "voll via rechenweg='voll'). Netzkosten/Gebrauchsabgabe als eigene Blöcke; "
        "Abdeckungs-Block weist Katalog-Lücken aus."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "plz": {"type": "string", "description": "Postleitzahl (4-stellig)"},
            "jahresverbrauch_kwh": {
                "type": "number", "description": "Jahresverbrauch in kWh (> 0)",
            },
            "aktueller_lieferant": {
                "type": "string", "description": "Name des aktuellen Lieferanten",
            },
            "aktueller_energiepreis_brutto_ct_kwh": {
                "type": "number", "description": "Aktueller Arbeitspreis brutto ct/kWh",
            },
            "aktuelle_grundgebuehr_brutto_eur_monat": {
                "type": "number", "description": "Aktuelle Grundgebühr brutto €/Monat",
            },
            "nb_key": {
                "type": "string",
                "description": (
                    "Vorgelöster Netzbetreiber-Schlüssel (optional; sonst PLZ-Auflösung)"
                ),
            },
            "energy_type": {
                "type": "string", "enum": ["POWER", "GAS"], "default": "POWER",
            },
            "zielgruppe": {
                "type": "string",
                "enum": ["standard", "waermepumpe", "elektroheizung", "unterbrechbar"],
                "default": "standard",
            },
            "top_n": {
                "type": "integer", "minimum": 1, "maximum": _MAX_TOP_N,
                "default": _DEFAULT_TOP_N,
                "description": "Anzahl Alternativen im Result (Default kompakt)",
            },
            "rechenweg": {
                "type": "string", "enum": ["kurz", "voll"], "default": "kurz",
                "description": "'kurz' = Kurzform-Zeile je Tarif; 'voll' = kompletter Rechenweg",
            },
        },
        "required": [
            "plz", "jahresverbrauch_kwh", "aktueller_lieferant",
            "aktueller_energiepreis_brutto_ct_kwh",
            "aktuelle_grundgebuehr_brutto_eur_monat",
        ],
    }

    def result_field_paths(self) -> dict[str, str]:
        """Reale Result-Felder (Top-Level-Skalare + versorger_abdeckung.*), gegen
        die ein Prozess-Caveat-Trigger gelintet wird (siehe ``_result_dict``)."""
        pfade: dict[str, str] = {
            "plz": "str",
            "jahresverbrauch_kwh": "number",
            "anzahl_alternativen_gesamt": "number",
            "anzahl_im_result": "number",
            "max_ersparnis_eur": "number",
            "netzkosten_eur_jahr": "number",
            "netzbetreiber": "str",
            "gebrauchsabgabe_rate": "number",
            "bester_gesamt": "str",
        }
        pfade.update(_versorger_abdeckung_pfade())
        return pfade

    def __init__(
        self,
        tariff_source: TariffSource | None = None,
        spot_source: SpotPriceSource | None = None,
    ) -> None:
        # Konsumenten (z.B. MCP-Gateway) injizieren eigene Quellen; Standalone
        # rechnet auf den gebündelten Open-Data-Snapshots (lazy geladen).
        self._tariff_source = tariff_source
        self._spot_source = spot_source

    def _quellen(self) -> tuple[TariffSource, SpotPriceSource | None]:
        tariff_source = self._tariff_source or CatalogTariffSource()
        spot_source = self._spot_source or SnapshotSpotPriceSource()
        return tariff_source, spot_source

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        tariff_source, _ = self._quellen()
        meta = dict(getattr(tariff_source, "meta", {}) or {})
        meta.setdefault("quelle", type(tariff_source).__name__)
        return meta

    def _quelle_fuer_alternativen(self) -> str:
        """Herkunfts-Kennung je Alternativen-Tarif (``Tariff.quelle``).

        Katalog (kein injizierter Source) bleibt ``"katalog"``. Für injizierte
        Fremd-Quellen wird die Kennung — falls vorhanden — aus deren
        ``meta``-Attribut übernommen; sonst neutraler Default ``"extern"``
        (statt der zuvor hartkodierten, produktspezifischen Annahme
        ``"scraper"``, die für beliebige injizierte Quellen faktisch falsch war).
        """
        if self._tariff_source is None:
            return "katalog"
        meta = getattr(self._tariff_source, "meta", None) or {}
        quelle = meta.get("quelle") if isinstance(meta, dict) else None
        return quelle if isinstance(quelle, str) and quelle else "extern"

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        plz = str(kwargs.get("plz") or "").strip()
        if not plz.isdigit() or len(plz) != 4:
            raise CapabilityError("plz ist erforderlich (4-stellige österreichische PLZ)")
        try:
            verbrauch = float(kwargs.get("jahresverbrauch_kwh") or 0.0)
            ep = float(kwargs.get("aktueller_energiepreis_brutto_ct_kwh") or 0.0)
            gg = float(kwargs.get("aktuelle_grundgebuehr_brutto_eur_monat") or 0.0)
        except (TypeError, ValueError) as exc:
            raise CapabilityError(f"Ungültige Zahleneingabe: {exc}") from exc
        if verbrauch <= 0 or verbrauch > 1_000_000:
            raise CapabilityError("jahresverbrauch_kwh muss > 0 und plausibel sein")
        if not _EP_MIN_CT <= ep <= _EP_MAX_CT:
            raise CapabilityError(
                f"aktueller_energiepreis_brutto_ct_kwh muss plausibel sein "
                f"({_EP_MIN_CT:g}-{_EP_MAX_CT:g} ct/kWh brutto) — Wert {ep:g} abgelehnt "
                "(keine stille 0.0-Koersion, No-LLM-Math)",
            )
        if not _GG_MIN_EUR <= gg <= _GG_MAX_EUR:
            raise CapabilityError(
                f"aktuelle_grundgebuehr_brutto_eur_monat muss plausibel sein "
                f"({_GG_MIN_EUR:g}-{_GG_MAX_EUR:g} EUR/Monat brutto) — Wert {gg:g} abgelehnt",
            )
        lieferant = str(kwargs.get("aktueller_lieferant") or "").strip()
        if not lieferant:
            raise CapabilityError("aktueller_lieferant ist erforderlich")
        try:
            top_n = int(kwargs["top_n"]) if "top_n" in kwargs else _DEFAULT_TOP_N
        except (TypeError, ValueError) as exc:
            raise CapabilityError(f"top_n muss eine Ganzzahl sein: {exc}") from exc
        if not 1 <= top_n <= _MAX_TOP_N:
            raise CapabilityError(f"top_n muss zwischen 1 und {_MAX_TOP_N} liegen")
        rechenweg_modus = str(kwargs.get("rechenweg") or "kurz")
        if rechenweg_modus not in ("kurz", "voll"):
            raise CapabilityError("rechenweg muss 'kurz' oder 'voll' sein")

        tariff_source, spot_source = self._quellen()
        cmp = vergleiche_tarife(
            plz=plz,
            jahresverbrauch_kwh=verbrauch,
            aktueller_lieferant=lieferant,
            aktueller_energiepreis_brutto_ct_kwh=ep,
            aktuelle_grundgebuehr_brutto_eur_monat=gg,
            tariff_source=tariff_source,
            spot_source=spot_source,
            nb_key=kwargs.get("nb_key") or None,
            energy_type=str(kwargs.get("energy_type") or "POWER"),
            zielgruppe=str(kwargs.get("zielgruppe") or "standard"),
            quelle=self._quelle_fuer_alternativen(),
        )
        return _result_dict(cmp, top_n=top_n, voller_rechenweg=rechenweg_modus == "voll")
