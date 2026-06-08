# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Spot-Tarif-Pricing: EPEX-Stundenpreise + Lieferanten-Aufschlag → ein vergleichbarer Tarifpreis.

Ein Spot-Tarif hat keinen festen Preis — er ergibt sich aus dem stündlichen
EPEX-Spotpreis, gewichtet mit dem Verbrauchsprofil, plus dem Lieferanten-Aufschlag.
Dieses Modul macht Spot damit vergleichbar mit Fixpreisen (effektiver ct/kWh +
€/Jahr), und ist ehrlich darüber, dass das ein **Backtest** auf historischen
Preisen ist, keine Prognose.

**Offline.** Die EPEX-Serie wird hineingereicht (``spot_prices``); die Beschaffung
(aWATTar-Fetch) lebt im konsumierenden Produkt. Default-Quelle für den
auditierbaren Backtest ist der gebündelte Snapshot
``energietools.data.spot`` (siehe ``capabilities.spot.data.load_epex_prices``).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from energietools.tools.cost_engine import _ts, build_price_at, compute_annual_cost
from energietools.tools.h0_profile import synthesize_h0_consumption


def _span(spot_prices: list[dict]) -> tuple[datetime, datetime]:
    ts = [datetime.fromisoformat(p["timestamp"]) for p in spot_prices]
    return min(ts), max(ts) + timedelta(hours=1)


def _resolve_consumption(
    annual_kwh: float, spot_prices: list[dict], consumption_data: list[dict] | None,
) -> tuple[list[dict], str]:
    if consumption_data is not None:
        return consumption_data, "eigene Verbrauchsdaten"
    start, end = _span(spot_prices)
    return synthesize_h0_consumption(annual_kwh, start, end), "H0-Standardlastprofil"


def _profile_stats(cons: list[dict], price_at, aufschlag_ct: float) -> tuple[float, float]:
    """volumengewichtetes vs zeitgewichtetes Spot-Mittel (ohne Aufschlag)."""
    sum_p = sum_pk = sum_kwh = 0.0
    n = 0
    for c in cons:
        ap = price_at(_ts(c["timestamp"]))
        if ap is None:
            continue
        spot = ap - aufschlag_ct
        sum_p += spot
        sum_pk += spot * c["kwh"]
        sum_kwh += c["kwh"]
        n += 1
    if sum_kwh <= 0:
        raise ValueError("Kein überlappender Zeitraum zwischen Verbrauch und Preisen")
    return sum_pk / sum_kwh, (sum_p / n if n else 0.0)


def _effective(
    spot_typ: str, tariftyp: str, hinweis: str,
    annual_kwh: float, aufschlag_ct: float, spot_prices: list[dict],
    consumption_data: list[dict] | None,
) -> dict:
    """Gemeinsamer Kern für Stunden- und Monatsfloater (über die Unified Cost Engine)."""
    if not spot_prices:
        raise ValueError("spot_prices darf nicht leer sein")

    cons, basis = _resolve_consumption(annual_kwh, spot_prices, consumption_data)

    # Preisreihe + Kosten kommen aus der EINEN Engine (cost_engine), nicht aus
    # tarifart-spezifischer Arithmetik. build_price_at ist modellfrei (Primitiven).
    price_at = build_price_at(
        tariftyp=tariftyp, spot_aufschlag_ct=aufschlag_ct, epex_prices=spot_prices,
    )
    cost = compute_annual_cost(cons, price_at, grundpreis_eur_monat=0.0)

    vol, zeit = _profile_stats(cons, price_at, aufschlag_ct)
    profil_faktor = round(((vol / zeit) - 1) * 100, 2) if zeit > 0 else 0.0

    return {
        "spot_typ": spot_typ,
        "effektiver_arbeitspreis_netto_ct": round(vol + aufschlag_ct, 4),
        "avg_spot_volumengewichtet_ct": round(vol, 4),
        "avg_spot_zeitgewichtet_ct": round(zeit, 4),
        "profilkostenfaktor_pct": profil_faktor,
        "jahreskosten_energie_netto_eur": cost["energie_netto_eur"],
        "basis": basis,
        "hinweis": hinweis,
    }


def compute_spot_effective(
    annual_kwh: float, aufschlag_ct: float, spot_prices: list[dict],
    *, consumption_data: list[dict] | None = None,
) -> dict:
    """Stundenfloater (real spot): stündlicher EPEX + Aufschlag, profilgewichtet."""
    return _effective(
        "stundenfloater", "Stundenfloater",
        "Backtest auf historischen EPEX-Preisen — keine Preisgarantie.",
        annual_kwh, aufschlag_ct, spot_prices, consumption_data,
    )


def compute_monthly_floater_effective(
    annual_kwh: float, aufschlag_ct: float, spot_prices: list[dict],
    *, consumption_data: list[dict] | None = None,
) -> dict:
    """Monatsfloater: ein Preis/Monat (Monatsmittel + Aufschlag), Tageszeit egal."""
    return _effective(
        "monatsfloater", "Monatsfloater",
        "Monatsmittel historischer EPEX-Preise — keine Preisgarantie.",
        annual_kwh, aufschlag_ct, spot_prices, consumption_data,
    )


def compute_spot_breakdown(
    tariff, annual_kwh: float, spot_prices: list[dict],
) -> dict:
    """Effektiver Spot-Preis pro Kalenderjahr + Mittel über alle Jahre.

    Für die ehrliche Darstellung: „Letztes Jahr hättest du X gezahlt, davor Y,
    im Mittel über N Jahre Z." Nutzt das H0-Standardlastprofil (repräsentativ,
    ohne Smart-Meter-Daten); jedes Jahr wird mit seinen echten EPEX-Preisen gerechnet.

    ``tariff`` ist ein beliebiges Objekt mit ``tariftyp`` + ``spot_aufschlag_ct``
    (z.B. ``CatalogTariff``).
    """
    if not spot_prices:
        raise ValueError("spot_prices darf nicht leer sein")

    by_year: dict[int, list[dict]] = {}
    for p in spot_prices:
        year = datetime.fromisoformat(p["timestamp"]).year
        by_year.setdefault(year, []).append(p)

    jahre: list[dict] = []
    for year in sorted(by_year):
        res = effective_for_tariff(tariff, annual_kwh, by_year[year])
        jahre.append({"jahr": year, **res})

    n = len(jahre)
    mittel_preis = round(sum(j["effektiver_arbeitspreis_netto_ct"] for j in jahre) / n, 4)
    mittel_kosten = round(sum(j["jahreskosten_energie_netto_eur"] for j in jahre) / n, 2)

    return {
        "spot_typ": jahre[0]["spot_typ"],
        "jahre": jahre,
        "mittel_arbeitspreis_netto_ct": mittel_preis,
        "mittel_jahreskosten_eur": mittel_kosten,
        "anzahl_jahre": n,
        "hinweis": "Backtest je Kalenderjahr auf echten EPEX-Preisen — keine Prognose.",
    }


def effective_for_tariff(
    tariff, annual_kwh: float, spot_prices: list[dict],
    *, consumption_data: list[dict] | None = None,
) -> dict:
    """Routet einen Spot-Tarif nach ``tariftyp`` auf das passende Preismodell.

    Monatsfloater → Monatsmittel; Stundenfloater/Spot → stündliche EPEX-Gewichtung.
    ``tariff`` ist ein beliebiges Objekt mit ``tariftyp`` + ``spot_aufschlag_ct``
    (z.B. ``CatalogTariff``).
    """
    if tariff.tariftyp == "Monatsfloater":
        return compute_monthly_floater_effective(
            annual_kwh, tariff.spot_aufschlag_ct, spot_prices, consumption_data=consumption_data,
        )
    return compute_spot_effective(
        annual_kwh, tariff.spot_aufschlag_ct, spot_prices, consumption_data=consumption_data,
    )
