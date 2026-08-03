# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Netz-Capabilities — Netzkosten, Gesamtkosten, Verfügbarkeit, Tarifvergleich.

Vier auditierbare Fähigkeiten über die publizierten Netz-Daten (offline):
- ``netzkosten``               — Brutto-Jahres-Netzkosten je PLZ (mit Rechenweg).
- ``gesamtkosten``             — echte Brutto-Jahreskosten (Energie + Netz + USt).
- ``netz_verfuegbar``          — Verfügbarkeit eines Tarifs in einer Region.
- ``tarifvergleich_inkl_netz`` — Tarifvergleich mit aus der PLZ gefüllten Netz-Inputs.

**FAIL-OPEN:** unbekannte PLZ → Netzkosten 0, ``netzbetreiber: null`` — kein
Hard-Fail, keine erfundenen Werte.
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.netz.data import load_abgaben
from energietools.capabilities.netz.models import NetzkostenEntry
from energietools.capabilities.netz.resolve import (
    entry_fuer_key,
    ist_verfuegbar,
    netzbetreiber_fuer_gemeinde,
    netzbetreiber_kandidaten,
    netzkosten_brutto_fuer,
    plz_info,
    resolve_netzbetreiber,
    tarif_fuer,
)

_UST = 1.20


def _require_plz(kwargs: dict[str, Any]) -> str:
    plz = str(kwargs.get("plz", "")).strip()
    if not plz:
        raise CapabilityError("plz ist erforderlich")
    return plz


def _vnb_aufloesen(
    plz: str, nb_key: str | None, gemeinde: str | None
) -> NetzkostenEntry | None:
    """Der VNB für eine PLZ, mit Vorrang für die eindeutigeren Angaben.

    1. ``nb_key`` — vom Aufrufer schon aufgelöst (im Gateway: deterministisch aus
       der Zählpunkt-VKZ). Ist der Key hier unbekannt, kennt der Aufrufer einen
       VNB, den energietools noch nicht modelliert; dann wird auf die PLZ
       zurückgefallen statt hart zu scheitern.
    2. ``gemeinde`` — die Antwort auf eine Rückfrage bei geteilter PLZ. Passt sie
       nicht zur PLZ, wird **nicht** auf die PLZ zurückgefallen: eine verworfene
       Nutzerantwort würde eine andere Frage beantworten als die gestellte.
    3. sonst die PLZ (fail-open bei geteilter PLZ → ``None``).
    """
    if nb_key:
        nb = entry_fuer_key(nb_key)
        if nb is not None:
            return nb
    if gemeinde:
        return netzbetreiber_fuer_gemeinde(plz, gemeinde)
    return resolve_netzbetreiber(plz)


def _require_positive(kwargs: dict[str, Any], feld: str) -> float:
    wert = kwargs.get(feld)
    if wert is None or float(wert) <= 0:
        raise CapabilityError(f"{feld} muss > 0 sein")
    return float(wert)


class NetzkostenCapability(Capability):
    """Brutto-Jahres-Netzkosten für eine PLZ (regulierte Werte, mit Rechenweg)."""

    name = "netzkosten"
    summary = (
        "Regulierte Brutto-Jahres-Netzkosten (NE7-Haushalt) für eine "
        "PLZ aus den Open-Data-Netzbereichen. Liefert VNB, Betrag und lückenlosen "
        "Rechenweg. Fail-open: unbekannte PLZ → netzbetreiber null, Kosten 0."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "plz": {"type": "string", "description": "Postleitzahl, z.B. '1010'"},
            "verbrauch_kwh": {"type": "number", "description": "Jahresverbrauch in kWh"},
            "nb_key": {
                "type": "string",
                "description": (
                    "Vorgelöster VNB-Key (z.B. deterministisch aus der Zählpunkt-VKZ). "
                    "Hat Vorrang vor der PLZ und löst geteilte PLZ auf."
                ),
            },
            "gemeinde": {
                "type": "string",
                "description": (
                    "Gemeinde des Anschlusses. Löst eine geteilte PLZ auf, wenn kein "
                    "nb_key vorliegt — siehe 'kandidaten' im Ergebnis."
                ),
            },
        },
        "required": ["plz", "verbrauch_kwh"],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        plz = _require_plz(kwargs)
        verbrauch = _require_positive(kwargs, "verbrauch_kwh")
        nb_key = str(kwargs.get("nb_key") or "").strip() or None
        gemeinde = str(kwargs.get("gemeinde") or "").strip() or None

        nb = _vnb_aufloesen(plz, nb_key, gemeinde)
        tarif = tarif_fuer(nb) if nb is not None else None
        if nb is None or tarif is None:
            # Fail-open: kein eindeutiger VNB/Tarif → keine Netzkosten erfunden.
            # ``kandidaten`` macht die Mehrdeutigkeit auflösbar, statt den Aufrufer
            # in einer Sackgasse stehen zu lassen (eine Rückfrage genügt).
            return {
                "netzbetreiber": None,
                "netzkosten_eur_jahr_brutto": 0.0,
                "rechenweg": {"komponenten": {}},
                "kandidaten": [
                    {"nb_key": k.key, "name": k.name, "gemeinden": list(gemeinden)}
                    for k, gemeinden in netzbetreiber_kandidaten(plz)
                ],
                "gueltig_ab": "",
                "quelle": "",
            }

        abgaben = load_abgaben()
        # Realer Name (nb.name), Tarif aus dem effektiven Netzbereich (tarif.*).
        brutto, name = netzkosten_brutto_fuer(nb, verbrauch)
        arbeitspreis_ct = (
            tarif.netznutzung_arbeitspreis_ct_kwh
            + tarif.netzverlust_ct_kwh
            + abgaben.eag_foerderbeitrag_ap_ct_kwh
            + abgaben.eag_foerderbeitrag_verlust_ct_kwh
            + abgaben.elektrizitaetsabgabe_haushalt_ct_kwh
        )
        pauschale_eur = tarif.netznutzung_pauschale_eur_jahr + abgaben.eag_foerderpauschale_eur_jahr
        netto = arbeitspreis_ct * verbrauch / 100.0 + pauschale_eur
        return {
            "netzbetreiber": name,
            "netzbereich": tarif.name if tarif.key != nb.key else None,
            "netzkosten_eur_jahr_brutto": brutto,
            "rechenweg": {
                "komponenten": {
                    "verbrauch_kwh": verbrauch,
                    "netznutzung_arbeitspreis_ct_kwh": tarif.netznutzung_arbeitspreis_ct_kwh,
                    "netzverlust_ct_kwh": tarif.netzverlust_ct_kwh,
                    "eag_foerderbeitrag_ap_ct_kwh": abgaben.eag_foerderbeitrag_ap_ct_kwh,
                    "eag_foerderbeitrag_verlust_ct_kwh": abgaben.eag_foerderbeitrag_verlust_ct_kwh,
                    "elektrizitaetsabgabe_haushalt_ct_kwh": (
                        abgaben.elektrizitaetsabgabe_haushalt_ct_kwh
                    ),
                    "arbeitspreis_summe_ct_kwh": round(arbeitspreis_ct, 4),
                    "netznutzung_pauschale_eur_jahr": tarif.netznutzung_pauschale_eur_jahr,
                    "eag_foerderpauschale_eur_jahr": abgaben.eag_foerderpauschale_eur_jahr,
                    "netto_eur_jahr": round(netto, 2),
                    "ust_faktor": _UST,
                    "brutto_eur_jahr": brutto,
                },
            },
            "kandidaten": [],
            "gueltig_ab": tarif.gueltig_ab,
            "quelle": tarif.quelle,
        }


class GesamtkostenCapability(Capability):
    """Echte Brutto-Jahreskosten (Energie + Netz + Gebrauchsabgabe + USt)."""

    name = "gesamtkosten"
    summary = (
        "Echte Brutto-Jahres-Gesamtkosten eines Haushalts: Energie (Arbeitspreis + "
        "Grundgebühr) + Gebrauchsabgabe + 20 % USt + regulierte Netzkosten. "
        "Lückenloser Rechenweg, alle Energie-Eingaben netto."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "plz": {"type": "string", "description": "Postleitzahl"},
            "verbrauch_kwh": {"type": "number", "description": "Jahresverbrauch in kWh"},
            "energiepreis_netto_ct_kwh": {"type": "number", "description": "Netto ct/kWh"},
            "grundgebuehr_netto_eur_monat": {"type": "number", "description": "Netto EUR/Monat"},
        },
        "required": [
            "plz",
            "verbrauch_kwh",
            "energiepreis_netto_ct_kwh",
            "grundgebuehr_netto_eur_monat",
        ],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        plz = _require_plz(kwargs)
        verbrauch = _require_positive(kwargs, "verbrauch_kwh")
        ep_netto_ct = float(kwargs["energiepreis_netto_ct_kwh"])
        gg_netto_monat = float(kwargs["grundgebuehr_netto_eur_monat"])

        # Delegiert an die EINE Szenario-Kosten-Engine (energietools.cost). Die
        # Capability ist deren dünne Fixpreis-Sicht (kein Rabatt/Spot über das LLM-/
        # CLI-Schema). Lazy-Import bricht den Package-Import-Zyklus (cost → netz).
        from energietools.cost import gesamtkosten_szenario

        res = gesamtkosten_szenario(
            plz=plz,
            verbrauch_kwh=verbrauch,
            netto_ep_ct=ep_netto_ct,
            netto_gg_eur_monat=gg_netto_monat,
            quelle="berechnet",
        )

        energie_netto = round(verbrauch * ep_netto_ct / 100.0, 2)
        grund_netto = round(gg_netto_monat * 12.0, 2)
        gesamt = res["gesamtkosten_eur_jahr_brutto"]
        return {
            "gesamtkosten_eur_jahr_brutto": gesamt,
            "netzbetreiber": res["netzbetreiber"],
            "rechenweg": {
                "energie_netto_eur": energie_netto,
                "grund_netto_eur": grund_netto,
                "gebrauchsabgabe_rate": res["gebrauchsabgabe_rate"],
                "gebrauchsabgabe_eur": res["gebrauchsabgabe_eur"],
                "energie_brutto_eur": res["jahreskosten_energie_brutto_eur"],
                "netzkosten_brutto_eur": res["netzkosten_brutto_eur"],
                "ust_faktor": _UST,
                "gesamt_brutto_eur": gesamt,
            },
        }


class VerfuegbarkeitCapability(Capability):
    """Prüft, ob ein Tarif mit gegebener Service-Area an einer PLZ verfügbar ist."""

    name = "netz_verfuegbar"
    summary = (
        "Prüft, ob ein Tarif mit gegebenem Versorgungsgebiet (service_area: 'AT', "
        "ein Bundesland oder eine Liste) an einer PLZ verfügbar ist. Fail-open: "
        "unbekannte PLZ → verfügbar."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "service_area": {
                "description": "'AT', ein Bundesland-String, oder eine Liste von Bundesländern",
                "anyOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
            },
            "plz": {"type": "string", "description": "Postleitzahl"},
        },
        "required": ["service_area", "plz"],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        plz = _require_plz(kwargs)
        service_area = kwargs.get("service_area")
        if service_area is None:
            raise CapabilityError("service_area ist erforderlich")
        info = plz_info(plz)
        return {
            "verfuegbar": ist_verfuegbar(service_area, plz),
            "bundeslaender": list(info.bundeslaender) if info else None,
        }
