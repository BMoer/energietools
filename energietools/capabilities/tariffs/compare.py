# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Auditierbarer Tarifvergleich gegen den Open-Data-Katalog.

Kern der Transparenz-These: jede Zahl, die hier herauskommt, ist von außen
reproduzierbar. Eingang ist ein Verbrauchsprofil (typischerweise aus einer
gescannten Rechnung) plus der aktuelle Tarif; Ausgang ein vollständig
sortierter Vergleich, bei dem **jeder** Tarif einen lückenlosen ``Rechenweg``
trägt (netto → Rabatt → Gebrauchsabgabe → USt → brutto).

Österreichische Energiekosten-Formel (ohne Netz):
    brutto = (netto_energie + netto_grund − rabatt_netto) × (1 + GAB) × 1.20
             − rabatt_pauschal_brutto

Netzkosten sind PLZ-/netzbetreiberabhängig und in der bundesweiten Entgelt-Verordnung
(BGBl. II Nr. 305/2025) festgelegt; sie
werden optional als Pauschale (``netzkosten_eur_jahr``) übergeben und in die
``gesamtkosten`` addiert, aber nicht erfunden.
"""

from __future__ import annotations

import logging

from energietools.capabilities.tariffs.catalog import TariffCatalog
from energietools.capabilities.tariffs.models import CatalogTariff
from energietools.models import Rechenweg, Tariff, TariffComparison

log = logging.getLogger(__name__)

_UST = 0.20


def _effektiver_netto_ep_ct(t: CatalogTariff, spot_baseline_ct: float | None) -> float | None:
    """Effektiver Netto-Energiepreis ct/kWh — oder None, wenn nicht bestimmbar.

    Fixtarif: der gelistete Energiepreis. Spot/Floater: Börsen-Baseline +
    Aufschlag, aber nur wenn eine ``spot_baseline_ct`` bekannt ist. Ohne
    Baseline lässt sich ein Spot-Tarif nicht auditierbar bepreisen → None.
    """
    if t.energiepreis_ct_kwh > 0:
        return t.energiepreis_ct_kwh
    if t.ist_spot:
        if spot_baseline_ct is None:
            return None
        return spot_baseline_ct + t.spot_aufschlag_ct
    # Weder Fixpreis noch Spot-Aufschlag → kein bepreisbarer Energieanteil.
    # Defensiv: ein negativer/0-Preis (Scraping-Drift) wird nicht bepreist.
    return t.energiepreis_ct_kwh if t.energiepreis_ct_kwh > 0 else None


def kosten_rechenweg(
    *,
    verbrauch_kwh: float,
    netto_ep_ct: float,
    netto_gg_eur_monat: float,
    gebrauchsabgabe_rate: float,
    rabatt_ct_kwh: float = 0.0,
    rabatt_pauschal_eur: float = 0.0,
    quelle: str = "katalog",
) -> Rechenweg:
    """Vollständiger, auditierbarer Rechenweg für einen Tarif (Jahr 1, inkl. Rabatt)."""
    netto_energie = verbrauch_kwh * netto_ep_ct / 100.0
    netto_grund = netto_gg_eur_monat * 12.0
    netto_gesamt = netto_energie + netto_grund

    rabatt_netto = verbrauch_kwh * rabatt_ct_kwh / 100.0
    netto_nach_rabatt = max(0.0, netto_gesamt - rabatt_netto)

    gab_eur = netto_nach_rabatt * gebrauchsabgabe_rate
    netto_inkl_gab = netto_nach_rabatt + gab_eur
    ust_eur = netto_inkl_gab * _UST
    brutto = netto_inkl_gab * (1.0 + _UST) - rabatt_pauschal_eur

    return Rechenweg(
        energiepreis_netto_ct_kwh=round(netto_ep_ct, 4),
        grundgebuehr_netto_eur_monat=round(netto_gg_eur_monat, 2),
        netto_energie_eur=round(netto_energie, 2),
        netto_grund_eur=round(netto_grund, 2),
        netto_gesamt_eur=round(netto_gesamt, 2),
        neukundenrabatt_netto_eur=round(rabatt_netto, 2),
        netto_nach_rabatt_eur=round(netto_nach_rabatt, 2),
        gebrauchsabgabe_rate=gebrauchsabgabe_rate,
        gebrauchsabgabe_eur=round(gab_eur, 2),
        netto_inkl_gab_eur=round(netto_inkl_gab, 2),
        ust_eur=round(ust_eur, 2),
        brutto_jahreskosten_eur=round(brutto, 2),
        quelle=quelle,
    )


def _catalog_to_tariff(
    t: CatalogTariff,
    *,
    verbrauch_kwh: float,
    gebrauchsabgabe_rate: float,
    spot_baseline_ct: float | None,
) -> Tariff | None:
    """Katalog-Eintrag → bepreister ``Tariff`` mit Rechenweg, oder None wenn nicht bepreisbar."""
    netto_ep = _effektiver_netto_ep_ct(t, spot_baseline_ct)
    if netto_ep is None:
        return None  # Spot ohne Baseline — bewusst NICHT mit 0 bepreist

    rw = kosten_rechenweg(
        verbrauch_kwh=verbrauch_kwh,
        netto_ep_ct=netto_ep,
        netto_gg_eur_monat=t.grundgebuehr_eur_monat,
        gebrauchsabgabe_rate=gebrauchsabgabe_rate,
        rabatt_ct_kwh=t.neukundenrabatt_ct_kwh,
        rabatt_pauschal_eur=t.neukundenrabatt_eur,
    )
    # Jahr 2 (ohne Rabatt) für ehrliche Langfrist-Sicht.
    rw_ohne = kosten_rechenweg(
        verbrauch_kwh=verbrauch_kwh,
        netto_ep_ct=netto_ep,
        netto_gg_eur_monat=t.grundgebuehr_eur_monat,
        gebrauchsabgabe_rate=gebrauchsabgabe_rate,
    )

    return Tariff(
        lieferant=t.lieferant,
        tarif_name=t.tarif_name,
        energiepreis_ct_kwh=round(netto_ep * (1.0 + _UST), 2),  # brutto für Anzeige
        grundgebuehr_eur_monat=round(t.grundgebuehr_eur_monat * (1.0 + _UST), 2),
        jahreskosten_eur=rw.brutto_jahreskosten_eur,
        jahreskosten_ohne_rabatt_eur=rw_ohne.brutto_jahreskosten_eur,
        ist_oekostrom=t.ist_oekostrom,
        tariftyp=t.tariftyp,
        preismodell=t.preismodell,
        hat_bindung=t.hat_bindung,
        quelle=f"katalog:{t.key}",
        wechsel_link=t.wechsel_link,
        rechenweg=rw,
    )


def compare_against_catalog(
    *,
    verbrauch_kwh: float,
    aktueller_lieferant: str,
    aktueller_energiepreis_ct_kwh: float,
    aktuelle_grundgebuehr_eur_monat: float,
    gebrauchsabgabe_rate: float = 0.0,
    netzkosten_eur_jahr: float = 0.0,
    netzbetreiber: str = "",
    spot_baseline_ct: float | None = None,
    catalog: TariffCatalog | None = None,
    plz: str = "",
) -> TariffComparison:
    """Vergleicht den aktuellen Tarif gegen den Open-Data-Katalog.

    Alle Preis-Eingaben sind **brutto** (inkl. 20% USt) — so, wie sie auf der
    Rechnung stehen. Intern wird auf netto zurückgerechnet. Spot-/Floater-
    Tarife werden nur einbezogen, wenn ``spot_baseline_ct`` gesetzt ist;
    andernfalls werden sie übersprungen (kein erfundener Preis von 0).
    """
    catalog = catalog or TariffCatalog.load()

    # Aktueller Tarif (brutto → netto), mit identischem Rechenweg.
    netto_ep = aktueller_energiepreis_ct_kwh / (1.0 + _UST)
    netto_gg = aktuelle_grundgebuehr_eur_monat / (1.0 + _UST)
    aktuell_rw = kosten_rechenweg(
        verbrauch_kwh=verbrauch_kwh,
        netto_ep_ct=netto_ep,
        netto_gg_eur_monat=netto_gg,
        gebrauchsabgabe_rate=gebrauchsabgabe_rate,
        quelle="rechnung",
    )
    aktueller_tarif = Tariff(
        lieferant=aktueller_lieferant,
        tarif_name="Aktueller Tarif",
        energiepreis_ct_kwh=aktueller_energiepreis_ct_kwh,
        grundgebuehr_eur_monat=aktuelle_grundgebuehr_eur_monat,
        jahreskosten_eur=aktuell_rw.brutto_jahreskosten_eur,
        jahreskosten_ohne_rabatt_eur=aktuell_rw.brutto_jahreskosten_eur,
        quelle="rechnung",
        rechenweg=aktuell_rw,
    )

    alternativen: list[Tariff] = []
    uebersprungen_spot = 0
    for t in catalog.all():
        tarif = _catalog_to_tariff(
            t,
            verbrauch_kwh=verbrauch_kwh,
            gebrauchsabgabe_rate=gebrauchsabgabe_rate,
            spot_baseline_ct=spot_baseline_ct,
        )
        if tarif is None:
            uebersprungen_spot += 1
            continue
        alternativen.append(tarif)

    if uebersprungen_spot:
        log.info(
            "%d Spot-/Floater-Tarife übersprungen (keine spot_baseline_ct übergeben)",
            uebersprungen_spot,
        )

    comparison = TariffComparison(
        aktueller_tarif=aktueller_tarif,
        alternativen=alternativen,
        plz=plz,
        jahresverbrauch_kwh=verbrauch_kwh,
        netzkosten_eur_jahr=netzkosten_eur_jahr,
        netzbetreiber=netzbetreiber,
        gebrauchsabgabe_rate=gebrauchsabgabe_rate,
    )
    return comparison.enrich()
