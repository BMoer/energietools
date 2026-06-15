# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
#
# Herkunft: Der Eigenverbrauchs-Dispatch stammt aus `pvtool` (batterystorage-sim,
# Jakob/holzjfk-a11y), MIT-Zusage liegt vor — siehe CREDITS.md. Er läuft hier über
# die portierte Battery-Komponente (energietools.components.battery), die den
# SOC/Wirkungsgrad-Kern trägt.

"""Dispatch-Runner: Eigenverbrauchs-Lade-/Entlade-Logik über eine Zeitreihe.

Reicht die (immutable) :class:`Battery`-Komponente über eine Folge von
Überschuss-Punkten (Produktion - Verbrauch) und bilanziert Netzbezug,
Einspeisung, Lade-/Entlademenge und die Kennzahlen Eigenverbrauchsquote +
Autarkiegrad. Das ist die erste funktionierende Referenz unter der neuen Struktur;
die Abbildung auf den allgemeinen Optimierer (scenarios als Strategie) ist als
TODO erfasst.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence
from dataclasses import dataclass

from energietools.components.base import StepContext
from energietools.components.battery import Battery


@dataclass(frozen=True)
class DispatchResult:
    """Bilanz eines Eigenverbrauchs-Durchlaufs (kWh + Kennzahlen)."""

    capacity_kwh: float
    production_kwh: float
    consumption_kwh: float
    grid_import_kwh: float
    grid_feed_in_kwh: float
    battery_charge_kwh: float
    battery_discharge_kwh: float
    self_consumption_rate: float
    self_sufficiency_rate: float
    cycles: float


def run_self_consumption(
    production_kwh: Sequence[float],
    consumption_kwh: Sequence[float],
    battery: Battery,
    dt_hours: float = 0.25,
) -> DispatchResult:
    """Eigenverbrauchs-Dispatch über die Zeitreihe (Produktion/Verbrauch je Intervall).

    Args:
        production_kwh: PV-Erzeugung je Intervall.
        consumption_kwh: Verbrauch je Intervall (gleiche Länge wie ``production_kwh``).
        battery: Start-Batterie (wird nicht mutiert; der Zustand wird intern fortgeführt).
        dt_hours: Intervalllänge (Default 0,25 h = 15-min-Raster).
    """
    if len(production_kwh) != len(consumption_kwh):
        raise ValueError("production_kwh und consumption_kwh müssen gleich lang sein")

    ctx = StepContext(dt_hours=dt_hours)
    bat = battery
    tot_prod = tot_cons = charge = discharge = grid_import = grid_feed = 0.0

    for prod, cons in zip(production_kwh, consumption_kwh, strict=True):
        surplus = prod - cons
        step, bat = bat.step(surplus, ctx)
        if surplus >= 0:
            charge += step.consumed_kwh
            grid_feed += max(surplus - step.consumed_kwh, 0.0)
        else:
            discharge += step.produced_kwh
            grid_import += max(-surplus - step.produced_kwh, 0.0)
        tot_prod += prod
        tot_cons += cons

    self_consumption_rate = (tot_prod - grid_feed) / tot_prod if tot_prod > 0 else 0.0
    self_sufficiency_rate = (tot_cons - grid_import) / tot_cons if tot_cons > 0 else 0.0
    cycles = charge / battery.capacity_kwh if battery.capacity_kwh > 0 else 0.0

    return DispatchResult(
        capacity_kwh=battery.capacity_kwh,
        production_kwh=round(tot_prod, 4),
        consumption_kwh=round(tot_cons, 4),
        grid_import_kwh=round(grid_import, 4),
        grid_feed_in_kwh=round(grid_feed, 4),
        battery_charge_kwh=round(charge, 4),
        battery_discharge_kwh=round(discharge, 4),
        self_consumption_rate=round(self_consumption_rate, 4),
        self_sufficiency_rate=round(self_sufficiency_rate, 4),
        cycles=round(cycles, 2),
    )


# ---------------------------------------------------------------------------
# Preis-getriebener Dispatch (spot_optimized / arbitrage) + Ökonomie
#
# Herkunft: Port von ``pvtool.battery.simulate_battery`` (batterystorage-sim,
# Jakob/holzjfk-a11y, MIT — siehe CREDITS.md). Hier ohne pandas/numpy: die
# Battery-Komponente trägt SOC/Wirkungsgrad/C-Rate, die Strategie-Politik
# (Tages-Perzentil-Schwellen, Netz-Laden bei billigem Spot, FCR-SOC-Reserve)
# ist 1:1 übernommen. Die Ökonomie (Bezug/Einspeisung × Preis + Netzentgelt)
# fällt im selben Durchlauf an, weil sie bei Spot intrinsisch preisabhängig ist.
# ---------------------------------------------------------------------------

_STRATEGIES = ("self_consumption", "spot_optimized", "arbitrage")


@dataclass(frozen=True)
class MarketTerms:
    """Markt-/Tarif-Parameter für den preis-getriebenen Dispatch (EUR/kWh)."""

    grid_buy_price_eur: float = 0.25       # Fixtarif-Bezugspreis (self_consumption)
    feedin_tariff_eur: float = 0.08        # Fix-Einspeisetarif (self_consumption)
    grid_fees_eur_per_kwh: float = 0.1311  # Netzentgelt auf Spot-Bezug
    feedin_spot_discount: float = 0.0      # Aggregator-Abschlag auf Spot-Einspeisung
    charging_grid_fee_eur_per_kwh: float | None = None  # Speicher-Ladenetzentgelt (§16b)

    @property
    def charging_fee(self) -> float:
        """Netzentgelt fürs Laden aus dem Netz; Fallback = Bezugs-Netzentgelt."""
        if self.charging_grid_fee_eur_per_kwh is None:
            return self.grid_fees_eur_per_kwh
        return self.charging_grid_fee_eur_per_kwh


@dataclass(frozen=True)
class EconomicDispatchResult:
    """Physische Bilanz + Ökonomie eines preis-getriebenen Durchlaufs."""

    capacity_kwh: float
    strategy: str
    grid_purchase_kwh: float
    grid_feedin_kwh: float
    battery_charge_kwh: float
    battery_discharge_kwh: float
    cycles: float
    revenue_eur: float
    cost_eur: float
    net_benefit_eur: float


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Lineares Perzentil (numpy-kompatibel) über bereits sortierte Werte."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    rank = (q / 100.0) * (n - 1)
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] * (hi - rank) + sorted_vals[hi] * (rank - lo)


def _daily_thresholds(
    prices: Sequence[float], day_index: Sequence[Hashable], q: float
) -> dict[Hashable, float]:
    """Tagesweise Perzentil-Schwelle (Tag-Schlüssel → Schwellpreis)."""
    by_day: dict[Hashable, list[float]] = {}
    for price, day in zip(prices, day_index, strict=True):
        by_day.setdefault(day, []).append(price)
    return {day: _percentile(sorted(vals), q) for day, vals in by_day.items()}


def simulate_battery(
    surplus_kwh: Sequence[float],
    battery: Battery,
    terms: MarketTerms,
    *,
    strategy: str = "self_consumption",
    dt_hours: float = 0.25,
    spot_price_eur: Sequence[float] | None = None,
    day_index: Sequence[Hashable] | None = None,
    fcr_soc_reserve_pct: float = 0.0,
) -> EconomicDispatchResult:
    """Batterie-Dispatch über eine Zeitreihe mit Ökonomie (Port von pvtool).

    Args:
        surplus_kwh: Überschuss (Produktion − Verbrauch) je Intervall. Bei
            ``arbitrage`` ungenutzt (reiner Netzhandel), aber für die Länge maßgeblich.
        battery: Start-Batterie (Kapazität/C-Rate/Wirkungsgrad/SOC-Grenzen).
        terms: Markt-/Tarifparameter (EUR/kWh).
        strategy: ``self_consumption`` | ``spot_optimized`` | ``arbitrage``.
        dt_hours: Intervalllänge in Stunden.
        spot_price_eur: Spotpreis (EUR/kWh) je Intervall — Pflicht außer bei
            ``self_consumption``.
        day_index: Tag-Schlüssel je Intervall (für Tages-Perzentile). None ⇒ ein Tag.
        fcr_soc_reserve_pct: Bei ``arbitrage`` für FCR reservierter SOC-Anteil (%).

    Raises:
        ValueError: unbekannte Strategie, fehlende/uneinheitliche Preisreihe.
    """
    if strategy not in _STRATEGIES:
        raise ValueError(f"Unbekannte Strategie {strategy!r}; erlaubt: {_STRATEGIES}")
    n = len(surplus_kwh)
    if strategy != "self_consumption":
        if spot_price_eur is None or len(spot_price_eur) != n:
            raise ValueError("spot_price_eur muss gleich lang wie surplus_kwh sein")
    if day_index is None:
        day_index = [0] * n
    elif len(day_index) != n:
        raise ValueError("day_index muss gleich lang wie surplus_kwh sein")

    cap = battery.capacity_kwh
    eff_c, eff_d = battery.charge_efficiency, battery.discharge_efficiency
    max_step = cap * battery.c_rate * dt_hours
    min_soc, max_soc = battery.min_soc_kwh, battery.max_soc_kwh
    fee_buy, fee_charge = terms.grid_fees_eur_per_kwh, terms.charging_fee
    sell_discount = terms.feedin_spot_discount

    tot_import = tot_feed = charge = discharge = revenue = cost = 0.0

    if cap <= 0:
        for i in range(n):
            s = surplus_kwh[i]
            if strategy == "arbitrage":
                continue
            spot_mode = strategy == "spot_optimized"
            if s >= 0:
                tot_feed += s
                sell = (spot_price_eur[i] - sell_discount) if spot_mode else terms.feedin_tariff_eur
                revenue += s * sell
            else:
                deficit = -s
                tot_import += deficit
                price = (spot_price_eur[i] + fee_buy) if spot_mode else terms.grid_buy_price_eur
                cost += deficit * price
    elif strategy == "self_consumption":
        soc = min_soc
        for i in range(n):
            s = surplus_kwh[i]
            if s >= 0:
                stored = min(s * eff_c, max_soc - soc, max_step * eff_c)
                soc += stored
                charge += stored
                export = s - (stored / eff_c if eff_c > 0 else 0.0)
                tot_feed += export
                revenue += export * terms.feedin_tariff_eur
            else:
                deficit = -s
                deliverable = min(soc - min_soc, deficit / eff_d if eff_d > 0 else 0.0, max_step)
                delivered = deliverable * eff_d
                soc -= deliverable
                discharge += delivered
                buy = deficit - delivered
                tot_import += buy
                cost += buy * terms.grid_buy_price_eur
    elif strategy == "spot_optimized":
        p25 = _daily_thresholds(spot_price_eur, day_index, 25)
        p75 = _daily_thresholds(spot_price_eur, day_index, 75)
        soc = min_soc
        for i in range(n):
            s, price, day = surplus_kwh[i], spot_price_eur[i], day_index[i]
            sell, buy_p = price - sell_discount, price + fee_buy
            if s >= 0:
                if price >= p75[day] and soc > min_soc:
                    tot_feed += s
                    revenue += s * sell
                    deliverable = min(soc - min_soc, max_step)
                    delivered = deliverable * eff_d
                    soc -= deliverable
                    discharge += delivered
                    tot_feed += delivered
                    revenue += delivered * sell
                else:  # billig oder neutral ⇒ laden, Rest einspeisen
                    stored = min(s * eff_c, max_soc - soc, max_step * eff_c)
                    soc += stored
                    charge += stored
                    export = s - (stored / eff_c if eff_c > 0 else 0.0)
                    tot_feed += export
                    revenue += export * sell
            else:
                deficit = -s
                if price <= p25[day] and soc < max_soc:  # billig ⇒ Defizit + Laden aus Netz
                    tot_import += deficit
                    cost += deficit * buy_p
                    stored = min(max_soc - soc, max_step * eff_c)
                    grid_charge = stored / eff_c if eff_c > 0 else 0.0
                    soc += stored
                    charge += stored
                    tot_import += grid_charge
                    cost += grid_charge * (price + fee_charge)
                else:  # sonst aus Speicher decken
                    need = deficit / eff_d if eff_d > 0 else 0.0
                    deliverable = min(soc - min_soc, need, max_step)
                    delivered = deliverable * eff_d
                    soc -= deliverable
                    discharge += delivered
                    buy = deficit - delivered
                    tot_import += buy
                    cost += buy * buy_p
    else:  # arbitrage — reiner Netzhandel, FCR-SOC-Reserve
        p30 = _daily_thresholds(spot_price_eur, day_index, 30)
        p70 = _daily_thresholds(spot_price_eur, day_index, 70)
        reserve = cap * fcr_soc_reserve_pct / 100.0
        arb_min, arb_max = min_soc + reserve, max_soc - reserve
        soc = arb_min
        for i in range(n):
            price, day = spot_price_eur[i], day_index[i]
            if price <= p30[day] and soc < arb_max:
                stored = min(arb_max - soc, max_step * eff_c)
                grid_buy = stored / eff_c if eff_c > 0 else 0.0
                soc += stored
                charge += stored
                tot_import += grid_buy
                cost += grid_buy * (price + fee_charge)
            elif price >= p70[day] and soc > arb_min:
                deliverable = min(soc - arb_min, max_step)
                delivered = deliverable * eff_d
                soc -= deliverable
                discharge += delivered
                tot_feed += delivered
                revenue += delivered * (price - sell_discount)

    cycles = charge / cap if cap > 0 else 0.0
    return EconomicDispatchResult(
        capacity_kwh=cap,
        strategy=strategy,
        grid_purchase_kwh=round(tot_import, 1),
        grid_feedin_kwh=round(tot_feed, 1),
        battery_charge_kwh=round(charge, 1),
        battery_discharge_kwh=round(discharge, 1),
        cycles=round(cycles, 1),
        revenue_eur=round(revenue, 2),
        cost_eur=round(cost, 2),
        net_benefit_eur=round(revenue - cost, 2),
    )
