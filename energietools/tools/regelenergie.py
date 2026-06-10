# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
#
# Herkunft: Port der DETERMINISTISCHEN Teile aus ``pvtool.market.regelenergie``
# und dem Kapazitäts-Erlösmodell (batterystorage-sim, Jakob/holzjfk-a11y, MIT —
# siehe CREDITS.md). Bewusst NICHT portiert: die stochastische FCR-Aktivierungs-
# Simulation (``scenarios/fcr_simulation.py``, rng/Monte-Carlo) — sie widerspricht
# der deterministisch-auditierbaren Linie von energietools und bleibt im Produkt/
# in den Forschungs-Notebooks. Die Live-ENTSO-E-Beschaffung lebt ebenfalls dort;
# hier werden bereits beschaffte Preise nur ausgewertet.
"""Regelenergie: Auswertung von Balancing-Preisen + Reserve-Kapazitäts-Erlös (FCR/aFRR)."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import datetime


def summarise_balancing_prices(
    prices_eur_mwh: Sequence[float], timestamps: Sequence[datetime]
) -> dict[str, float]:
    """Kennzahlen einer Balancing-Preisreihe (EUR/MWh).

    Args:
        prices_eur_mwh: Regelenergie-Abrechnungspreise (EUR/MWh).
        timestamps: zugehörige Zeitstempel (für die abgedeckten Tage).

    Returns:
        ``{days, count, mean/median/min/max/std_eur_mwh}``; bei leerer Reihe
        ``{days: 0, count: 0}``.
    """
    if len(prices_eur_mwh) != len(timestamps):
        raise ValueError("prices_eur_mwh und timestamps müssen gleich lang sein")
    n = len(prices_eur_mwh)
    if n == 0:
        return {"days": 0, "count": 0}

    prices = list(prices_eur_mwh)
    days = (max(timestamps) - min(timestamps)).days + 1
    return {
        "days": days,
        "count": n,
        "mean_eur_mwh": round(statistics.mean(prices), 2),
        "median_eur_mwh": round(statistics.median(prices), 2),
        "min_eur_mwh": round(min(prices), 2),
        "max_eur_mwh": round(max(prices), 2),
        "std_eur_mwh": round(statistics.stdev(prices), 2) if n >= 2 else 0.0,
    }


def reserve_capacity_revenue(
    power_kw: float,
    capacity_price_eur_per_kw_year: float,
    availability: float = 0.85,
) -> float:
    """Jahres-Kapazitätserlös einer Reserve-Vorhaltung (FCR/aFRR), gerundet.

    Deterministisches Vorhalte-Modell: ``Leistung × Kapazitätspreis × Verfügbarkeit``.
    Das ist genau die Formel, die Simbas Arbitrage-Szenario für den FCR-Anteil nutzt.
    Aktivierungs-Energieerlöse (stochastisch) sind NICHT enthalten — siehe Modulkopf.

    Args:
        power_kw: vorgehaltene/präqualifizierte Leistung (kW), z.B. Wechselrichter-kW.
        capacity_price_eur_per_kw_year: Kapazitätspreis (EUR/kW/Jahr).
        availability: Anteil des Jahres mit verfügbarer Vorhaltung (0–1).

    Raises:
        ValueError: bei negativer Leistung/Preis oder availability außerhalb [0, 1].
    """
    if power_kw < 0 or capacity_price_eur_per_kw_year < 0:
        raise ValueError("power_kw und capacity_price dürfen nicht negativ sein")
    if not 0.0 <= availability <= 1.0:
        raise ValueError("availability muss in [0, 1] liegen")
    return round(power_kw * capacity_price_eur_per_kw_year * availability, 2)
