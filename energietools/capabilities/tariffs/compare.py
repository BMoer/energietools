# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Auditierbarer Kosten-Rechenweg für EINEN Tarif (Energie, ohne Netz).

et ist die reine Kosten-Engine: ``kosten_rechenweg`` liefert für einen Tarif einen
lückenlosen, von außen reproduzierbaren Rechenweg (netto → Rabatt → USt → brutto),
mit der Gebrauchsabgabe als EIGENEM Brutto-Block. Der VERGLEICH über viele Tarife
(Loop, Differenz, Ranking, Präsentation) ist Sache des Konsumenten (gridbert), nicht
dieses Pakets — siehe docs/PLAN_PRIO1_ET_KONSOLIDIERUNG.md (S4: et = Kosten-Engine).

Österreichische Energiekosten-Formel (ohne Netz, separate-Block-GAB):
    brutto_jahreskosten = netto_nach_rabatt × 1,20 − rabatt_pauschal   (Energie, ohne GAB)
    gebrauchsabgabe     = netto_nach_rabatt × rate × 1,20              (eigener Brutto-Block)
Netzkosten sind PLZ-/netzbetreiberabhängig (BGBl. II Nr. 305/2025) und werden separat
über die ``netz``-Capabilities ergänzt, nicht hier erfunden.
"""

from __future__ import annotations

from energietools.models import Rechenweg

_UST = 0.20


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
    """Vollständiger, auditierbarer Rechenweg für einen Tarif (Jahr 1, inkl. Rabatt).

    Gebrauchsabgabe ist ein EIGENER Brutto-Block (``gebrauchsabgabe_eur``), NICHT in
    ``brutto_jahreskosten_eur``; USt liegt nur auf Energie+Grund nach Rabatt.
    """
    netto_energie = verbrauch_kwh * netto_ep_ct / 100.0
    netto_grund = netto_gg_eur_monat * 12.0
    netto_gesamt = netto_energie + netto_grund

    rabatt_netto = verbrauch_kwh * rabatt_ct_kwh / 100.0
    netto_nach_rabatt = max(0.0, netto_gesamt - rabatt_netto)

    # Gebrauchsabgabe als eigener Brutto-Block (skaliert mit dem Energieanteil).
    gab_brutto = netto_nach_rabatt * gebrauchsabgabe_rate * (1.0 + _UST)
    # USt nur auf Energie+Grund nach Rabatt (NICHT auf die Gebrauchsabgabe).
    ust_eur = netto_nach_rabatt * _UST
    # Endwert Energie: netto_nach_rabatt × 1,20 − Rabatt-Pauschale (ohne Netz, ohne GAB).
    brutto = netto_nach_rabatt * (1.0 + _UST) - rabatt_pauschal_eur

    return Rechenweg(
        energiepreis_netto_ct_kwh=round(netto_ep_ct, 4),
        grundgebuehr_netto_eur_monat=round(netto_gg_eur_monat, 2),
        netto_energie_eur=round(netto_energie, 2),
        netto_grund_eur=round(netto_grund, 2),
        netto_gesamt_eur=round(netto_gesamt, 2),
        neukundenrabatt_netto_eur=round(rabatt_netto, 2),
        netto_nach_rabatt_eur=round(netto_nach_rabatt, 2),
        gebrauchsabgabe_rate=gebrauchsabgabe_rate,
        gebrauchsabgabe_eur=round(gab_brutto, 2),
        ust_eur=round(ust_eur, 2),
        brutto_jahreskosten_eur=round(brutto, 2),
        quelle=quelle,
    )
