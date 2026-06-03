# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Operator-/länderparametrisierte Netzentgelte pro kWh (offline, fail-open).

Liefert das **marginale** Netzentgelt pro kWh (das, was Dispatch/Optimierer und
Spot-Analyse als Kostenanteil brauchen) — im Gegensatz zur PLZ→Jahreskosten-
Sicht der ``netz``-Capability. Die österreichischen Zahlen kommen aus demselben
auditierten Snapshot (``data/netz/``): pro-kWh-Anteile = Netznutzungs-Arbeitspreis
+ Netzverlust + EAG-Förderbeitrag (AP + Verlust) + Elektrizitätsabgabe; brutto =
netto × 1,20. Das ist exakt die ``arbeitspreis_ct``-Komposition aus
``netz.resolve.netzkosten_brutto_eur`` (Single Source of Truth).

FAIL-OPEN: unbekannter Operator oder ``country != "AT"`` → ``None`` (keine
erfundenen Werte). Wo ein konkreter Default-Wert gebraucht wird (z.B. der
Netzentgelt-Anteil der Spot-Analyse), wirft ein nicht auflösbarer Default einen
``CapabilityError`` — lieber ein sichtbarer Fehler als eine stille Magic-Number.
"""

from __future__ import annotations

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.netz.data import load_abgaben, load_alle_vnb
from energietools.capabilities.netz.models import NetzkostenEntry
from energietools.capabilities.netz.resolve import tarif_fuer

_UST = 1.20

#: Default-Betreiber für Österreich (Stand-konsistent mit pvtool/Energienetze
#: Steiermark; Zahlen aus dem auditierten ``data/netz``-Snapshot).
DEFAULT_OPERATOR_AT = "energienetze_steiermark"


def resolve_operator(operator: str | None = None, country: str = "AT") -> NetzkostenEntry | None:
    """Findet den Netzbetreiber per key **oder** Name innerhalb eines Landes.

    - ``country != "AT"`` → ``None`` (DE/CH noch nicht befüllt; siehe TODO.md).
    - ``operator is None`` → der Default-Operator des Landes.
    - sonst case-insensitiver Vergleich gegen ``key`` und ``name``.

    Folgt ``tarif_referenz`` (Attributions-VNB billt den Tarif seines Netzbereichs).
    Fail-open: kein eindeutiger Treffer → ``None``.
    """
    if country.strip().upper() != "AT":
        return None

    ziel = (operator or DEFAULT_OPERATOR_AT).strip().casefold()
    treffer = [
        e for e in load_alle_vnb()
        if e.key.casefold() == ziel or e.name.casefold() == ziel
    ]
    if len(treffer) != 1:
        return None
    return tarif_fuer(treffer[0])


def _ap_netto_ct_kwh(tarif: NetzkostenEntry) -> float:
    """Voll geladener Netzentgelt-Arbeitspreis (netto, ct/kWh) — wie netz-Layer."""
    abgaben = load_abgaben()
    return (
        tarif.netznutzung_arbeitspreis_ct_kwh
        + tarif.netzverlust_ct_kwh
        + abgaben.eag_foerderbeitrag_ap_ct_kwh
        + abgaben.eag_foerderbeitrag_verlust_ct_kwh
        + abgaben.elektrizitaetsabgabe_haushalt_ct_kwh
    )


def network_fee_ct_kwh(
    operator: str | None = None, country: str = "AT", brutto: bool = False
) -> float | None:
    """Reiner Netz-Anteil pro kWh (Netznutzung + Netzverlust), ohne Bundesabgaben.

    Das ist „das Netzentgelt“ im engen Sinn — der Anteil, den die Spot-Analyse als
    ``netz_ct`` getrennt von Steuern/Abgaben führt. Fail-open: ``None``.
    """
    tarif = resolve_operator(operator, country)
    if tarif is None:
        return None
    netto = tarif.netznutzung_arbeitspreis_ct_kwh + tarif.netzverlust_ct_kwh
    return round(netto * (_UST if brutto else 1.0), 4)


def consumption_fee_ct_kwh(
    operator: str | None = None, country: str = "AT", brutto: bool = True
) -> float | None:
    """Voll geladenes Entnahme-Netzentgelt pro kWh (inkl. EAG + Elektrizitätsabgabe).

    Das ist der per-kWh-Kostenanteil für bezogene Energie (Dispatch/Optimierer).
    Fail-open: ``None``.
    """
    tarif = resolve_operator(operator, country)
    if tarif is None:
        return None
    return round(_ap_netto_ct_kwh(tarif) * (_UST if brutto else 1.0), 4)


def charging_fee_ct_kwh(
    operator: str | None = None,
    country: str = "AT",
    storage_exemption: bool = False,
    brutto: bool = True,
) -> float | None:
    """Netzentgelt pro kWh für **Ladeenergie** eines Speichers.

    Bei ``storage_exemption=True`` (Doppelbelastungs-Befreiung für Speicher,
    §16b/§17 ElWOG) entfällt das Netzentgelt auf die Ladeenergie → ``0.0``.
    Sonst wie :func:`consumption_fee_ct_kwh`. Fail-open: ``None``.
    """
    if storage_exemption:
        return 0.0
    return consumption_fee_ct_kwh(operator, country, brutto=brutto)


def default_network_fee_ct_kwh(country: str = "AT") -> float:
    """Netz-Anteil pro kWh des Default-Operators — sourced Ersatz für Magic-Numbers.

    Wird z.B. von ``spot_analysis`` als Default-``netz_ct`` genutzt (statt der
    früheren hartkodierten 3,5 ct/kWh). Wirft ``CapabilityError``, wenn der
    Default nicht auflösbar ist — kein stiller Fallback.
    """
    fee = network_fee_ct_kwh(None, country, brutto=False)
    if fee is None:
        raise CapabilityError(
            f"Default-Netzentgelt für Land '{country}' nicht auflösbar "
            f"(Operator '{DEFAULT_OPERATOR_AT}' fehlt im data/netz-Snapshot?)"
        )
    return fee


def total_fee_breakdown(
    operator: str | None = None, country: str = "AT", storage_exemption: bool = False
) -> dict | None:
    """Auditierbarer per-kWh-Aufschlüsselung des Netzentgelts (alle Komponenten).

    Fail-open: nicht auflösbar → ``None``.
    """
    tarif = resolve_operator(operator, country)
    if tarif is None:
        return None
    abgaben = load_abgaben()
    netznutzung = tarif.netznutzung_arbeitspreis_ct_kwh
    netzverlust = tarif.netzverlust_ct_kwh
    eag_ap = abgaben.eag_foerderbeitrag_ap_ct_kwh
    eag_verlust = abgaben.eag_foerderbeitrag_verlust_ct_kwh
    elabg = abgaben.elektrizitaetsabgabe_haushalt_ct_kwh
    netto = netznutzung + netzverlust + eag_ap + eag_verlust + elabg
    return {
        "operator": tarif.name,
        "country": country.strip().upper(),
        "storage_exemption": storage_exemption,
        "komponenten_ct_kwh": {
            "netznutzung_arbeitspreis": round(netznutzung, 4),
            "netzverlust": round(netzverlust, 4),
            "eag_foerderbeitrag_ap": round(eag_ap, 4),
            "eag_foerderbeitrag_verlust": round(eag_verlust, 4),
            "elektrizitaetsabgabe": round(elabg, 4),
            "summe_netto": round(netto, 4),
            "ust_faktor": _UST,
            "summe_brutto": round(netto * _UST, 4),
            "charging_brutto": 0.0 if storage_exemption else round(netto * _UST, 4),
        },
        "netznutzung_pauschale_eur_jahr": tarif.netznutzung_pauschale_eur_jahr,
        "eag_foerderpauschale_eur_jahr": abgaben.eag_foerderpauschale_eur_jahr,
        "gueltig_ab": tarif.gueltig_ab,
        "quelle": tarif.quelle,
        "abgaben_quelle": str(abgaben.federal.get("quelle", "")),
    }
