# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Spot-Backtest + Tarif-Ersparnis — Rechen-Kerne (L.4, Port von gridbert
``gridbert/tools/lastgang_cost.py``).

Zwei unabhängige Ergebnis-Bausteine. Beide sind optional — fehlt die
Datenlage, wird das NIE als 0 ausgewiesen (F8/L.6.2), sondern als
``verfuegbar=False`` + ``grund``:

- :func:`compute_spot_backtest` — profilgewichteter Spot-Backtest (echter
  Verbrauchs-Shape × EPEX-Stundenpreise) gegen den aktuellen Fixpreis. Nutzt
  die bestehende ``compute_spot_effective`` (``energietools.tools.spot_pricing``)
  + die Unified Cost Engine (``build_price_at``/``compute_annual_cost``) —
  KEINE eigene €-Arithmetik hier (No-LLM-Math). Port von
  ``build_spot_backtest`` (``lastgang_cost.py:68-116``).
- :func:`extract_tarif_ersparnis` — reine Extraktion aus einem bereits
  gelaufenen ``TariffCompareCapability``-Result (L.4.3: die DB-gebundene
  Quelle ``compare_from_db`` der gridbert-Quelle wird NICHT portiert —
  offline über die bestehende ``TariffSource``-Protocol-Injection von
  ``tariff_compare``).

**Offline (L.4.2):** ``consumption``/``spot_prices`` sind Parameter, die die
Capability-Hülle hereinreicht — kein DB-/Netzzugriff in diesem Modul, dadurch
mit einer synthetischen EPEX-Reihe testbar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from energietools.tools.cost_engine import _ts, build_price_at, compute_annual_cost
from energietools.tools.spot_pricing import compute_spot_effective

# Repräsentativer Anbieter-Aufschlag fürs Spot-Backtest, falls keiner gesetzt
# ist. Annahme (keine Preisgarantie) — wird im Result immer als aufschlag_ct
# mitgegeben (lastgang_cost.py:28).
DEFAULT_SPOT_AUFSCHLAG_CT = 1.5
_UST = 1.20  # österr. Umsatzsteuer auf Strom (brutto -> netto), lastgang_cost.py:25

GRUND_KEIN_SPOT = "Keine EPEX-Spotpreise übergeben — Spot-Backtest nicht berechenbar."
GRUND_KEIN_VERBRAUCH = "Kein Verbrauchs-Lastgang übergeben — Spot-Backtest nicht berechenbar."
GRUND_KEIN_FIXPREIS = (
    "Kein aktueller Fixpreis (energiepreis_brutto_ct_kwh) übergeben — "
    "Fix-vs-Spot-Vergleich nicht möglich."
)
_GRUND_KEIN_OVERLAP_TEMPLATE = "Verbrauch und EPEX-Preise überlappen sich zeitlich nicht ({exc})."

GRUND_TARIF_ERSPARNIS_LEER = (
    "Keine passende Alternative im Tarifkatalog gefunden (tariff_compare liefert 0 Alternativen)."
)


@dataclass(frozen=True)
class SpotBacktestCore:
    """Ergebnis von :func:`compute_spot_backtest` — IMMER gesetzt, nie eine
    stille 0 bei fehlender Datenlage (``verfuegbar=False`` + ``grund`` statt)."""

    verfuegbar: bool
    grund: str | None
    aufschlag_ct: float
    spot_netto_eur: float | None = None
    fix_netto_eur: float | None = None
    differenz_eur: float | None = None  # fix - spot; positiv = Spot günstiger
    effektiver_spot_ct: float | None = None
    profilkostenfaktor_pct: float | None = None
    basis: str | None = None
    hinweis: str | None = None
    # Volumen-Parität (Demo-Fund 2026-07-13): BEIDE Seiten rechnen über exakt
    # die EPEX-gedeckten Verbrauchs-Slots — das Fenster steht im Result.
    vergleichs_kwh: float | None = None
    vergleich_von: str | None = None
    vergleich_bis: str | None = None


def compute_spot_backtest(
    consumption: list[dict],
    spot_prices: list[dict],
    energiepreis_brutto_ct_kwh: float | None,
    *,
    aufschlag_ct: float = DEFAULT_SPOT_AUFSCHLAG_CT,
) -> SpotBacktestCore:
    """Profilgewichteter Spot-Backtest vs. aktueller Fixpreis (Port L.4.3).

    ``consumption``/``spot_prices`` je ``[{"timestamp": ISO, "kwh"|"price_ct": …}]``
    — das von ``compute_spot_effective``/``compute_annual_cost`` erwartete
    Primitiv-Format (L.4.2, ``spot_pricing.py:91-100``). Guard-Reihenfolge wie
    ``build_spot_backtest`` (``lastgang_cost.py:87-96``), erweitert um eine
    Begründung statt eines stillen ``None`` (L.6.2 — jede Zahl im Result
    verweist über ``grund``/``rechenweg`` auf ihre Herkunft, auch die
    Nicht-Berechenbarkeit).
    """
    if not spot_prices:
        return SpotBacktestCore(verfuegbar=False, grund=GRUND_KEIN_SPOT, aufschlag_ct=aufschlag_ct)
    if not consumption:
        return SpotBacktestCore(
            verfuegbar=False, grund=GRUND_KEIN_VERBRAUCH, aufschlag_ct=aufschlag_ct
        )
    if energiepreis_brutto_ct_kwh is None:
        return SpotBacktestCore(
            verfuegbar=False, grund=GRUND_KEIN_FIXPREIS, aufschlag_ct=aufschlag_ct
        )

    # Volumen-Parität: die Spot-Seite kann nur EPEX-gedeckte Stunden bepreisen
    # (price_at → None-skip). Der Fixpreis würde sonst den GESAMTEN Lastgang
    # bepreisen und differenz_eur um das ungedeckte Volumen aufblähen
    # (Demo-Fund 2026-07-13: 1,5 Jahre Verbrauch vs. 1 Jahr EPEX). Deshalb
    # laufen BEIDE Seiten über exakt die Slots mit EPEX-Stundenpreis —
    # derselbe Stunden-Schlüssel wie ``cost_engine._hourly_map``.
    epex_stunden = {_ts(p["timestamp"]).strftime("%Y-%m-%d %H") for p in spot_prices}
    gedeckt = [
        c for c in consumption
        if _ts(c["timestamp"]).strftime("%Y-%m-%d %H") in epex_stunden
    ]
    if not gedeckt:
        return SpotBacktestCore(
            verfuegbar=False,
            grund=_GRUND_KEIN_OVERLAP_TEMPLATE.format(exc="0 gemeinsame Stunden"),
            aufschlag_ct=aufschlag_ct,
        )

    vergleichs_kwh = sum(r["kwh"] for r in gedeckt)
    try:
        spot = compute_spot_effective(
            vergleichs_kwh, aufschlag_ct, spot_prices, consumption_data=gedeckt,
        )
    except ValueError as exc:
        return SpotBacktestCore(
            verfuegbar=False,
            grund=_GRUND_KEIN_OVERLAP_TEMPLATE.format(exc=exc),
            aufschlag_ct=aufschlag_ct,
        )

    # Fixpreis-Vergleich über DIESELBE Cost Engine UND DASSELBE Volumen wie Spot.
    fix_ep_netto_ct = energiepreis_brutto_ct_kwh / _UST
    fix = compute_annual_cost(
        gedeckt,
        build_price_at(tariftyp="Fixpreis", energiepreis_ct_kwh=fix_ep_netto_ct),
        grundpreis_eur_monat=0.0,
    )

    spot_eur = spot["jahreskosten_energie_netto_eur"]
    fix_eur = fix["energie_netto_eur"]
    zeitpunkte = sorted(_ts(r["timestamp"]) for r in gedeckt)
    return SpotBacktestCore(
        verfuegbar=True,
        grund=None,
        aufschlag_ct=aufschlag_ct,
        spot_netto_eur=round(spot_eur, 2),
        fix_netto_eur=round(fix_eur, 2),
        differenz_eur=round(fix_eur - spot_eur, 2),
        effektiver_spot_ct=spot["effektiver_arbeitspreis_netto_ct"],
        profilkostenfaktor_pct=spot["profilkostenfaktor_pct"],
        basis=spot["basis"],
        hinweis=spot["hinweis"],
        vergleichs_kwh=round(vergleichs_kwh, 2),
        vergleich_von=zeitpunkte[0].isoformat(),
        vergleich_bis=zeitpunkte[-1].isoformat(),
    )


@dataclass(frozen=True)
class TarifErsparnisCore:
    """Ergebnis von :func:`extract_tarif_ersparnis` — dünne Sicht auf
    ``tariff_compare`` (L.4.3), Felder wie ``gridbert/models/lastgang_cost.py:17-25``
    (``TarifErsparnis``)."""

    verfuegbar: bool
    grund: str | None
    ist_eur: float | None = None
    best_eur: float | None = None
    ersparnis_eur: float | None = None
    lieferant_ist: str | None = None
    lieferant_best: str | None = None
    tarif_best: str | None = None
    netzkosten_vollstaendig: bool | None = None
    basis: str | None = None


def extract_tarif_ersparnis(
    *,
    ok: bool,
    error: str | None,
    data: dict[str, Any] | None,
    aktueller_lieferant: str,
) -> TarifErsparnisCore:
    """Extrahiert ``ist_eur/best_eur/ersparnis_eur/lieferant_best/tarif_best``
    aus einem bereits gelaufenen ``TariffCompareCapability``-Result.

    Reine Funktion — sie ruft ``tariff_compare`` NICHT selbst auf (das macht
    die Capability-Hülle, die die Quelle injiziert bekommt); hier wird nur
    das fertige Envelope ausgewertet (L.4.3: die DB-Variante
    ``compare_from_db`` wird NICHT portiert, stattdessen die bestehende
    ``TariffSource``-Protocol-Injection von ``tariff_compare`` genutzt —
    offline via ``CatalogTariffSource``).
    """
    if not ok:
        return TarifErsparnisCore(verfuegbar=False, grund=f"tariff_compare abgelehnt: {error}")
    data = data or {}
    alternativen = data.get("alternativen") or []
    if not alternativen:
        return TarifErsparnisCore(verfuegbar=False, grund=GRUND_TARIF_ERSPARNIS_LEER)

    # alternativen ist bereits nach jahreskosten_eur aufsteigend sortiert
    # (compare.py: vergleiche_tarife sortiert vor der Top-N-Kürzung) — [0]
    # ist somit dieselbe Alternative wie cmp.bester_gesamt.
    bester = alternativen[0]
    ist = data.get("aktueller_tarif") or {}
    ist_eur = ist.get("jahreskosten_eur", ist.get("energiepreis_anteil_eur"))
    best_eur = bester.get("jahreskosten_eur", bester.get("energiepreis_anteil_eur"))
    # Ersparnis LOKAL aus ist_eur/best_eur (Energie-Basis), NICHT aus
    # tariff_compare's data["max_ersparnis_eur"] übernommen: seit dem
    # Gesamtkosten-Fix in tariff_compare (fix/ersparnis-gesamtkosten) ist
    # max_ersparnis_eur bei netzkosten_vollstaendig=true die GESAMTKOSTEN-
    # Differenz (Energie + Netz + Gebrauchsabgabe) — hier im Spot-Backtest-
    # Kontext geht es aber um den ENERGIEPREIS-Hebel (Fix vs. günstigste
    # Alternative; ``spot_backtest.differenz_eur`` daneben ist ebenfalls rein
    # energie-basiert, KEIN Netz/GAB). Netz+GAB sind für ist_eur/best_eur
    # ohnehin identisch (dieselbe PLZ) und ändern den Hebel nicht — Übernahme
    # von max_ersparnis_eur würde hier wieder zwei Zahlenwelten im selben
    # Block erzeugen (ist_eur − best_eur ≠ ersparnis_eur). Bleibt konsistent
    # mit ``_CAVEAT_TARIF_ERSPARNIS_ENERGIEBASIS`` (lastgang/capability.py),
    # die ist_eur/best_eur bereits als Energiepreis-Anteil dokumentiert.
    ersparnis_eur = (
        round(ist_eur - best_eur, 2) if ist_eur is not None and best_eur is not None else None
    )
    return TarifErsparnisCore(
        verfuegbar=True,
        grund=None,
        ist_eur=ist_eur,
        best_eur=best_eur,
        ersparnis_eur=ersparnis_eur,
        lieferant_ist=aktueller_lieferant,
        lieferant_best=bester.get("lieferant"),
        tarif_best=bester.get("tarif_name"),
        netzkosten_vollstaendig=bool(data.get("netzkosten_vollstaendig")),
        basis=(
            "Energiepreis-Jahreskosten brutto (Netzkosten/Gebrauchsabgabe separate "
            "Blöcke in tariff_compare, s. netzkosten_vollstaendig) — ersparnis_eur "
            "ist ist_eur minus best_eur auf DERSELBEN Energie-Basis (bewusst NICHT "
            "tariff_compare's gesamtkosten-basierte max_ersparnis_eur, s. Kommentar)"
        ),
    )
