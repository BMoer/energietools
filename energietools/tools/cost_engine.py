# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Unified Cost Engine — eine Rechenlogik für Fix, Monatsfloater und Spot.

    Jahreskosten = Σ_h ( arbeitspreis_h × verbrauch_h ) + grundpreis × 12
                   (+ Netz + Gebrauchsabgabe + USt − Rabatte)

Der einzige Unterschied zwischen den Tarifarten ist die Granularität der
Arbeitspreis-Zeitreihe (konstant / monatlich / stündlich). ``build_price_at``
erzeugt für jeden Tarif eine Funktion ``price_at(ts) -> netto ct/kWh``;
``compute_annual_cost`` summiert sie gegen das Verbrauchsprofil.

Der Backtest ist **offline**: die EPEX-Stundenreihe wird als ``epex_prices``
hineingereicht (Beschaffung passiert im konsumierenden Produkt). ``build_price_at``
arbeitet auf **Primitiven** (tariftyp/spot_aufschlag_ct/energiepreis_ct_kwh),
nicht auf einem Tarif-Modell — entkoppelt die Engine von den Modell-Schemata.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

_UST = 1.20  # österr. Umsatzsteuer auf Strom

PriceAt = Callable[[datetime], float | None]


def _ts(v) -> datetime:
    return v if isinstance(v, datetime) else datetime.fromisoformat(v)


def compute_annual_cost(
    consumption_hourly: list[dict],
    price_at: PriceAt,
    grundpreis_eur_monat: float,
    *,
    netz_ct: float = 0.0,
    steuern_ct: float = 0.0,
    gab_rate: float = 0.0,
    discount_eur_jahr1: float = 0.0,
    discount_ct_kwh_jahr1: float = 0.0,
) -> dict:
    """Summiert Verbrauch × Arbeitspreis + Grundpreis zu Jahreskosten.

    Args:
        consumption_hourly: [{timestamp, kwh}] — H0-Profil oder echte SM-Daten.
        price_at: Funktion ts → netto ct/kWh (None = Stunde nicht bepreisbar → skip).
        grundpreis_eur_monat: netto Grundgebühr €/Monat.
        netz_ct, steuern_ct: netto Aufschläge ct/kWh (gridarea-einheitlich).
        gab_rate: Gebrauchsabgabe-Satz auf den Energieanteil (z.B. 0.07).
        discount_eur_jahr1: einmaliger Year-1-Rabatt (netto €).

    Returns dict mit netto/brutto-Aufschlüsselung (Jahr 1 und Folgejahre).
    """
    matched_kwh = 0.0
    energie_netto_ct = 0.0
    for c in consumption_hourly:
        ap = price_at(_ts(c["timestamp"]))
        if ap is None:
            continue
        energie_netto_ct += c["kwh"] * ap
        matched_kwh += c["kwh"]

    energie_netto_eur = energie_netto_ct / 100.0
    grund_netto_eur = grundpreis_eur_monat * 12.0
    netz_netto_eur = matched_kwh * netz_ct / 100.0
    steuern_netto_eur = matched_kwh * steuern_ct / 100.0

    netto_gesamt = energie_netto_eur + grund_netto_eur + netz_netto_eur + steuern_netto_eur
    gab_eur = energie_netto_eur * gab_rate
    # Year-1-Rabatt: Pauschale + per-kWh-Anteil (netto)
    rabatt_jahr1_eur = discount_eur_jahr1 + matched_kwh * discount_ct_kwh_jahr1 / 100.0
    brutto_gesamt = (netto_gesamt + gab_eur) * _UST
    brutto_jahr1 = (netto_gesamt + gab_eur - rabatt_jahr1_eur) * _UST

    return {
        "matched_kwh": round(matched_kwh, 2),
        "energie_netto_eur": round(energie_netto_eur, 2),
        "grund_netto_eur": round(grund_netto_eur, 2),
        "netz_netto_eur": round(netz_netto_eur, 2),
        "steuern_netto_eur": round(steuern_netto_eur, 2),
        "netto_gesamt_eur": round(netto_gesamt, 2),
        "rabatt_jahr1_eur": round(rabatt_jahr1_eur, 2),
        "brutto_gesamt_eur": round(brutto_gesamt, 2),  # Folgejahre (ohne Rabatt)
        "brutto_jahr1_eur": round(brutto_jahr1, 2),     # Jahr 1 (mit Rabatt)
    }


def _monthly_means(epex_prices: list[dict]) -> dict[tuple[int, int], float]:
    acc: dict[tuple[int, int], list[float]] = {}
    for p in epex_prices:
        ts = _ts(p["timestamp"])
        acc.setdefault((ts.year, ts.month), []).append(p["price_ct"])
    return {k: sum(v) / len(v) for k, v in acc.items()}


def _hourly_map(epex_prices: list[dict]) -> dict[str, float]:
    return {_ts(p["timestamp"]).strftime("%Y-%m-%d %H"): p["price_ct"] for p in epex_prices}


def build_price_at(
    *,
    tariftyp: str,
    spot_aufschlag_ct: float = 0.0,
    energiepreis_ct_kwh: float = 0.0,
    epex_prices: list[dict] | None = None,
) -> PriceAt:
    """Erzeugt die Arbeitspreis-Funktion ``price_at(ts)`` aus Primitiven.

    - Fixpreis      → konstant ``energiepreis_ct_kwh``
    - Monatsfloater → Monats-EPEX-Schnitt + ``spot_aufschlag_ct``
    - Stundenfloater→ EPEX-Stundenpreis + ``spot_aufschlag_ct``

    Modellfrei (keine Tariff-Abhängigkeit) — der konsumierende Vergleich reicht
    die drei relevanten Primitiven plus die EPEX-Serie hinein.
    """
    if tariftyp == "Stundenfloater":
        hourly = _hourly_map(epex_prices or [])

        def _spot(ts: datetime) -> float | None:
            base = hourly.get(ts.strftime("%Y-%m-%d %H"))
            return None if base is None else base + spot_aufschlag_ct

        return _spot

    if tariftyp == "Monatsfloater":
        means = _monthly_means(epex_prices or [])

        def _monthly(ts: datetime) -> float | None:
            base = means.get((ts.year, ts.month))
            return None if base is None else base + spot_aufschlag_ct

        return _monthly

    # Fixpreis (Default)
    return lambda ts: energiepreis_ct_kwh
