# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
#
# Herkunft: Port der greedy-Variante aus ``pvtool.scenarios.peak_shaving``
# (batterystorage-sim, Jakob/holzjfk-a11y, MIT — siehe CREDITS.md). Hier ohne
# pandas/numpy: die Battery-Komponente trägt die Physik, die Monats-Spitzen
# werden über einen mitgereichten Monats-Schlüssel je Intervall gebildet. Der
# ``optimal``-Modus (CVXPY/LP) ist bewusst NICHT portiert (zu schwer für die
# leichtgewichtige, auditierbare Linie).
"""Greedy Peak-Shaving: Netzbezug unter eine kW-Schwelle drücken (Leistungspreis)."""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass

from energietools.components.battery import Battery


@dataclass(frozen=True)
class PeakShavingResult:
    """Bilanz + Ökonomie eines greedy Peak-Shaving-Durchlaufs."""

    capacity_kwh: float
    baseline_peak_kw: float
    achieved_peak_kw: float
    peak_reduction_kw: float
    demand_savings_eur: float
    energy_savings_eur: float
    net_benefit_eur: float
    grid_purchase_kwh: float
    battery_charge_kwh: float
    battery_discharge_kwh: float
    cycles: float
    grid_charge_kwh: float = 0.0
    #: Der Speicher konnte NIE laden — ohne diese Meldung wäre das Ergebnis eine
    #: stille 0 € (Produkt-Learning L13: Betriebe ohne PV haben nie Überschuss,
    #: und ohne ``grid_charge_threshold_kw`` gibt es keine zweite Ladequelle).
    kein_ladefenster: bool = False
    hinweis: str | None = None


def _group_max(values: Sequence[float], keys: Sequence[Hashable]) -> dict[Hashable, float]:
    """Maximum je Schlüssel (z.B. Monats-Spitze)."""
    out: dict[Hashable, float] = {}
    for val, key in zip(values, keys, strict=True):
        if key not in out or val > out[key]:
            out[key] = val
    return out


def run_peak_shaving(
    net_demand_kwh: Sequence[float],
    month_index: Sequence[Hashable],
    battery: Battery,
    *,
    peak_threshold_kw: float,
    demand_charge_eur_per_kw_year: float = 63.0,
    grid_buy_price_eur: float = 0.25,
    dt_hours: float = 0.25,
    combine_self_consumption: bool = True,
    baseline_peak_kw: float | None = None,
    grid_charge_threshold_kw: float | None = None,
) -> PeakShavingResult:
    """Greedy Peak-Shaving über eine Netto-Last-Zeitreihe (Port von pvtool).

    Args:
        net_demand_kwh: Netto-Last (Verbrauch − Produktion) je Intervall (kWh).
        month_index: Monats-Schlüssel je Intervall (für die Leistungs-Spitzen).
        battery: Start-Batterie (Kapazität/C-Rate/Wirkungsgrad/SOC-Grenzen).
        peak_threshold_kw: Schwelle, ab der entladen wird (kW).
        demand_charge_eur_per_kw_year: Leistungspreis (EUR/kW/Jahr).
        grid_buy_price_eur: Arbeitspreis für die Energie-Ersparnis (EUR/kWh).
        dt_hours: Intervalllänge (h).
        combine_self_consumption: zusätzlich Eigenverbrauch unter der Schwelle decken.
        baseline_peak_kw: optionaler Override der Baseline-Spitze (Daten-Korrektur).
        grid_charge_threshold_kw: Netzladung in Schwachlastzeiten — der Speicher lädt
            aus dem Netz, solange der Netzbezug dabei unter dieser kW-Schwelle bleibt.
            ``None`` = nur aus Überschuss laden (unverändertes pvtool-Port-Verhalten).
            Ohne diesen Parameter kann ein Betrieb OHNE PV nie laden (Produkt-Learning
            L13); das Ergebnis meldet das dann über ``kein_ladefenster``.

    Note:
        Der Netzladestrom zählt in ``grid_purchase_kwh`` mit und verteuert damit die
        Energiebilanz — die Ersparnis kommt aus dem Leistungspreis, nicht aus der
        Arbeit. ``energy_savings_eur`` wird bei Netzladung folgerichtig negativ.
    """
    n = len(net_demand_kwh)
    if len(month_index) != n:
        raise ValueError("month_index muss gleich lang wie net_demand_kwh sein")
    if peak_threshold_kw <= 0:
        raise ValueError("peak_threshold_kw muss > 0 sein")

    dt = dt_hours
    rate = demand_charge_eur_per_kw_year

    # --- Baseline (ohne Batterie) ---
    baseline_grid_kw = [max(nd / dt, 0.0) for nd in net_demand_kwh]
    baseline_monthly = _group_max(baseline_grid_kw, month_index)
    data_baseline_peak = max(baseline_monthly.values()) if baseline_monthly else 0.0
    effective_baseline = baseline_peak_kw if baseline_peak_kw is not None else data_baseline_peak
    n_months = len(baseline_monthly)
    baseline_demand_charge = effective_baseline * rate / 12.0 * n_months
    baseline_grid_purchase = sum(max(nd, 0.0) for nd in net_demand_kwh)

    cap = battery.capacity_kwh
    if cap <= 0:
        return PeakShavingResult(
            capacity_kwh=cap,
            baseline_peak_kw=round(data_baseline_peak, 2),
            achieved_peak_kw=round(data_baseline_peak, 2),
            peak_reduction_kw=0.0,
            demand_savings_eur=0.0,
            energy_savings_eur=0.0,
            net_benefit_eur=0.0,
            grid_purchase_kwh=round(baseline_grid_purchase, 1),
            battery_charge_kwh=0.0,
            battery_discharge_kwh=0.0,
            cycles=0.0,
        )

    eff_c, eff_d = battery.charge_efficiency, battery.discharge_efficiency
    min_soc, max_soc = battery.min_soc_kwh, battery.max_soc_kwh
    max_power_kw = cap * battery.c_rate
    max_charge_interval = max_power_kw * dt * eff_c
    max_discharge_interval = max_power_kw * dt
    threshold_kwh = peak_threshold_kw * dt

    # Netzladung (L13): unter dieser kWh-Grenze je Intervall darf aus dem Netz
    # geladen werden. Ohne sie hat ein Betrieb ohne PV keine Ladequelle.
    grid_charge_limit_kwh = (
        grid_charge_threshold_kw * dt if grid_charge_threshold_kw is not None else None
    )
    # Bei Netzladung wird NICHT zusätzlich unter der Schwelle entladen: die Energie
    # käme dann aus dem Netz zum selben Arbeitspreis zurück ins Netz-gedeckte
    # Intervall — ein reiner Wirkungsgradverlust, der obendrein den Speicher für
    # die Spitze leer laufen lässt (gemessen: Spitze blieb dabei unverändert).
    eigenverbrauch_decken = combine_self_consumption and grid_charge_limit_kwh is None

    soc = min_soc
    actual_grid_kw: list[float] = []
    grid_purchase = charge = discharge = grid_charge = 0.0

    for nd in net_demand_kwh:
        grid_kwh = 0.0
        if nd > threshold_kwh:  # Spitze kappen
            excess = nd - threshold_kwh
            need = excess / eff_d if eff_d > 0 else 0.0
            can_dis = min(soc - min_soc, need, max_discharge_interval)
            delivered = can_dis * eff_d
            soc -= can_dis
            discharge += delivered
            grid_kwh = max(nd - delivered, 0.0)
            grid_purchase += grid_kwh
        elif nd <= 0.0:  # Überschuss laden
            surplus = -nd
            can_chg = min(surplus * eff_c, max_soc - soc, max_charge_interval)
            soc += can_chg
            charge += can_chg
        elif eigenverbrauch_decken:  # unter Schwelle: Eigenverbrauch decken
            can_dis = min(soc - min_soc, nd / eff_d if eff_d > 0 else 0.0, max_discharge_interval)
            delivered = can_dis * eff_d
            soc -= can_dis
            discharge += delivered
            grid_kwh = max(nd - delivered, 0.0)
            grid_purchase += grid_kwh
        else:  # unter Schwelle, kein Eigenverbrauch: Netz deckt
            grid_kwh = nd
            grid_purchase += nd

        # Schwachlast-Netzladung: nur so viel, dass der Netzbezug dieses Intervalls
        # unter der Ladeschwelle bleibt (erzeugt also selbst keine neue Spitze).
        if grid_charge_limit_kwh is not None and grid_kwh < grid_charge_limit_kwh:
            kopf_kwh = grid_charge_limit_kwh - grid_kwh
            can_chg = min(kopf_kwh * eff_c, max_soc - soc, max_charge_interval)
            can_chg = max(can_chg, 0.0)
            if can_chg > 0.0:
                vom_netz = can_chg / eff_c if eff_c > 0 else 0.0
                soc += can_chg
                charge += can_chg
                grid_charge += vom_netz
                grid_purchase += vom_netz
                grid_kwh += vom_netz

        actual_grid_kw.append(grid_kwh / dt)

    achieved_monthly = _group_max(actual_grid_kw, month_index)
    achieved_demand_charge = sum(achieved_monthly.values()) * rate / 12.0
    achieved_peak = max(achieved_monthly.values()) if achieved_monthly else 0.0
    demand_savings = baseline_demand_charge - achieved_demand_charge
    energy_savings = (baseline_grid_purchase - grid_purchase) * grid_buy_price_eur
    cycles = charge / cap if cap > 0 else 0.0

    kein_ladefenster = charge <= 0.0
    hinweis = None
    if kein_ladefenster:
        hinweis = (
            "Der Speicher hat in dieser Zeitreihe NIE geladen: die Netto-Last ist nie "
            "negativ (kein PV-Überschuss) und Netzladung ist nicht freigegeben. Das "
            "Ergebnis ist deshalb 0 EUR — nicht weil sich Spitzenkappung nicht lohnt, "
            "sondern weil der Fall so nicht gerechnet werden kann. Mit "
            "grid_charge_threshold_kw (Laden in Schwachlastzeiten) erneut rechnen."
        )

    return PeakShavingResult(
        capacity_kwh=cap,
        baseline_peak_kw=round(data_baseline_peak, 2),
        achieved_peak_kw=round(achieved_peak, 2),
        peak_reduction_kw=round(data_baseline_peak - achieved_peak, 2),
        demand_savings_eur=round(demand_savings, 2),
        energy_savings_eur=round(energy_savings, 2),
        net_benefit_eur=round(demand_savings + energy_savings, 2),
        grid_purchase_kwh=round(grid_purchase, 1),
        battery_charge_kwh=round(charge, 1),
        battery_discharge_kwh=round(discharge, 1),
        cycles=round(cycles, 1),
        grid_charge_kwh=round(grid_charge, 1),
        kein_ladefenster=kein_ladefenster,
        hinweis=hinweis,
    )
