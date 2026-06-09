# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Per-Szenario-Gesamtkosten — die EINE auditierbare Kosten-Engine.

Komponiert die Kosten EINES Szenarios (Tarif + PLZ + Verbrauch) aus den Bausteinen:
effektiver Energiepreis (Fixpreis ODER Spot/Floater-Backtest über EPEX), Neukunden-
rabatt (Jahr 1), basisgenaue Gebrauchsabgabe (eigener Brutto-Block) und regulierte
Netzkosten. Separate-Block-Modell, 1:1 wie gridbert (``_tariff_from_row`` /
``compare_from_db``): die USt liegt nur auf Energie+Grund nach Rabatt; Gebrauchs-
abgabe und Netzkosten sind eigene Brutto-Blöcke und NICHT Teil der Energie-Jahres-
kosten.

Das ist der Per-Szenario-Endpunkt, den das Produkt (gridbert) im Cutover konsumiert
— statt eigener, gedrifteter Kosten-Mathematik. ``GesamtkostenCapability`` ist die
dünne CLI/LLM-Hülle darüber. Der VERGLEICH (Loop/Differenz/Ranking) bleibt Sache des
Konsumenten.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from energietools.capabilities.netz.models import GebrauchsabgabeRegelDetail
from energietools.capabilities.netz.resolve import (
    entry_fuer_key,
    gebrauchsabgabe_regel,
    netzkosten_brutto_fuer,
    netznutzung_netto_ohne_abgaben_fuer,
    resolve_netzbetreiber,
)
from energietools.models import Rechenweg
from energietools.tools.spot_pricing import effective_for_tariff

_UST = 1.20


@dataclass(frozen=True)
class _SpotTarif:
    """Minimal-Sicht für ``effective_for_tariff`` (braucht nur tariftyp + Aufschlag)."""

    tariftyp: str
    spot_aufschlag_ct: float


def effektiver_energiepreis_netto_ct(
    *,
    netto_ep_ct: float,
    tariftyp: str,
    spot_aufschlag_ct: float,
    verbrauch_kwh: float,
    spot_prices: list[dict] | None,
) -> float | None:
    """Effektiver Netto-Arbeitspreis: Fixpreis direkt, Spot/Floater über EPEX-Backtest.

    Spiegelt gridberts ``_tariff_from_row`` (``ep_netto <= 0`` → Spot-Effektivpreis,
    sonst der Fixpreis). Gibt ``None`` zurück, wenn ein Spot-Tarif ohne EPEX-Daten
    nicht bepreisbar ist (fail-open: Tarif wird übersprungen statt mit 0 fehlbepreist).
    """
    if netto_ep_ct and netto_ep_ct > 0:
        return netto_ep_ct
    # ep <= 0: nur ein Spot/Floater-Tarif wird über EPEX bepreist; ein (degenerierter)
    # Fixpreis mit 0-Energiepreis bleibt 0-Energie (kein erfundener Spot-Preis).
    ist_floater = tariftyp in ("Stundenfloater", "Monatsfloater") or spot_aufschlag_ct > 0
    if not ist_floater:
        return netto_ep_ct
    if not spot_prices:
        return None
    eff = effective_for_tariff(
        _SpotTarif(tariftyp=tariftyp, spot_aufschlag_ct=spot_aufschlag_ct),
        verbrauch_kwh,
        spot_prices,
    )
    ep = eff["effektiver_arbeitspreis_netto_ct"]
    return ep if ep > 0 else None


def energie_rechenweg(
    *,
    verbrauch_kwh: float,
    netto_ep_ct: float,
    netto_gg_eur_monat: float,
    neukundenrabatt_ct_kwh: float = 0.0,
    neukundenrabatt_eur: float = 0.0,
    gab_regel: GebrauchsabgabeRegelDetail | None = None,
    netz_netto_ga_eur: float = 0.0,
    quelle: str = "katalog",
) -> Rechenweg:
    """Energie-Jahreskosten (inkl. Rabatt) + Gebrauchsabgabe als eigener Block.

    Mirror von gridberts ``_tariff_from_row`` (Energie-Teil): die Energie-Kette
    schließt für sich (``netto_nach_rabatt × 1,20 − Rabatt-Pauschale``); die GAB ist
    ein EIGENER Brutto-Block, bemessen auf der **Vor-Rabatt**-Energie-Netto (und/oder
    Netz-Netto ohne Abgaben), und fließt NICHT in ``brutto_jahreskosten_eur``.

    ``netz_netto_ga_eur`` ist das reine Netznutzungs-Netto (ohne Abgaben) der PLZ,
    konstant über alle Tarife — die GA-Basis "Netz". ``gab_regel=None`` → keine GA.
    """
    netto_energie = verbrauch_kwh * netto_ep_ct / 100.0
    netto_grund = netto_gg_eur_monat * 12.0
    netto_gesamt = netto_energie + netto_grund

    jahreskosten_ohne_rabatt = netto_gesamt * _UST
    # Rabatt Jahr 1: per-kWh (netto ct → brutto) + Pauschale (brutto EUR).
    rabatt_brutto = (verbrauch_kwh * neukundenrabatt_ct_kwh / 100.0) * _UST + neukundenrabatt_eur
    jahreskosten = max(0.0, jahreskosten_ohne_rabatt - rabatt_brutto)

    # Gebrauchsabgabe basisgenau (typ/satz/basis), eigener Brutto-Block, auf der
    # Vor-Rabatt-Energie-Netto (1:1 wie gridbert: GA hängt nicht am Neukundenrabatt).
    gab_netto = (
        gab_regel.betrag_netto_eur(netto_energie, netz_netto_ga_eur, verbrauch_kwh)
        if gab_regel is not None
        else 0.0
    )
    gab_brutto = gab_netto * _UST
    # Anzeige-Prozentsatz (0 für ct/kWh-Regeln; der reale Euro-Betrag steht im Block).
    gab_rate_display = (
        gab_regel.satz if (gab_regel is not None and gab_regel.typ == "prozent") else 0.0
    )

    netto_nach_rabatt = netto_gesamt - rabatt_brutto / _UST
    return Rechenweg(
        energiepreis_netto_ct_kwh=round(netto_ep_ct, 4),
        grundgebuehr_netto_eur_monat=round(netto_gg_eur_monat, 2),
        netto_energie_eur=round(netto_energie, 2),
        netto_grund_eur=round(netto_grund, 2),
        netto_gesamt_eur=round(netto_gesamt, 2),
        neukundenrabatt_netto_eur=round(rabatt_brutto / _UST, 2),
        netto_nach_rabatt_eur=round(netto_nach_rabatt, 2),
        gebrauchsabgabe_rate=gab_rate_display,
        gebrauchsabgabe_eur=round(gab_brutto, 2),
        ust_eur=round(netto_nach_rabatt * 0.20, 2),  # USt auf Energie+Grund nach Rabatt
        brutto_jahreskosten_eur=round(jahreskosten, 2),  # netto_nach_rabatt × 1,20 − Pauschale
        quelle=quelle,
    )


def gesamtkosten_szenario(
    *,
    plz: str,
    verbrauch_kwh: float,
    netto_ep_ct: float,
    netto_gg_eur_monat: float,
    tariftyp: str = "Fixpreis",
    spot_aufschlag_ct: float = 0.0,
    neukundenrabatt_ct_kwh: float = 0.0,
    neukundenrabatt_eur: float = 0.0,
    spot_prices: list[dict] | None = None,
    nb_key: str | None = None,
    quelle: str = "katalog",
) -> dict[str, Any] | None:
    """Volle Brutto-Jahres-Gesamtkosten EINES Szenarios (separate-Block-Modell).

    Energie (Fixpreis ODER Spot/Floater-Backtest) + Neukundenrabatt + basisgenaue
    Gebrauchsabgabe (eigener Block) + regulierte Netzkosten. Spiegelt gridberts
    ``_tariff_from_row`` + die Netz/GA-Auflösung aus ``compare_from_db`` feldweise und
    ist damit der Per-Szenario-Kosten-Endpunkt für den Cutover.

    ``nb_key``: optional ein vom Konsumenten **vorgelöster** VNB-Schlüssel (z.B.
    VKZ-deterministisch über den Zählpunkt). Gesetzt → Netzkosten/GA-Netz-Basis folgen
    diesem VNB statt der (mehrdeutigen) PLZ-Auflösung; ``None`` → Auflösung aus der PLZ.

    Returns ``None``, wenn der Tarif nicht bepreisbar ist (Spot/Floater ohne EPEX-Daten).
    """
    ep_netto = effektiver_energiepreis_netto_ct(
        netto_ep_ct=netto_ep_ct,
        tariftyp=tariftyp,
        spot_aufschlag_ct=spot_aufschlag_ct,
        verbrauch_kwh=verbrauch_kwh,
        spot_prices=spot_prices,
    )
    if ep_netto is None:
        return None

    # Netzbetreiber EINMAL bestimmen → Netzkosten + GA-Regel + GA-Netz-Basis konsistent.
    # Vorgelöster nb_key (VKZ-deterministisch beim Konsumenten) hat Vorrang vor der PLZ.
    nb = entry_fuer_key(nb_key) if nb_key else resolve_netzbetreiber(plz)
    resolved_key = nb.key if nb is not None else None
    netz_netto_ga = netznutzung_netto_ohne_abgaben_fuer(nb, verbrauch_kwh)
    regel = gebrauchsabgabe_regel(plz, resolved_key)
    netzkosten_brutto, netzbetreiber = netzkosten_brutto_fuer(nb, verbrauch_kwh)

    rw = energie_rechenweg(
        verbrauch_kwh=verbrauch_kwh,
        netto_ep_ct=ep_netto,
        netto_gg_eur_monat=netto_gg_eur_monat,
        neukundenrabatt_ct_kwh=neukundenrabatt_ct_kwh,
        neukundenrabatt_eur=neukundenrabatt_eur,
        gab_regel=regel,
        netz_netto_ga_eur=netz_netto_ga,
        quelle=quelle,
    )

    gesamt = round(rw.brutto_jahreskosten_eur + netzkosten_brutto + rw.gebrauchsabgabe_eur, 2)
    return {
        "gesamtkosten_eur_jahr_brutto": gesamt,
        "jahreskosten_energie_brutto_eur": rw.brutto_jahreskosten_eur,
        "gebrauchsabgabe_eur": rw.gebrauchsabgabe_eur,
        "gebrauchsabgabe_rate": rw.gebrauchsabgabe_rate,
        "netzkosten_brutto_eur": netzkosten_brutto,
        "netzbetreiber": netzbetreiber or None,
        "effektiver_ep_netto_ct": round(ep_netto, 4),
        "rechenweg": rw,
    }
