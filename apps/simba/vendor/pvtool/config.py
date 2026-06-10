"""
Configuration dataclasses for pvtool.

All economic and technical defaults reflect the Austrian residential PV market
(Energienetze Steiermark, SNE-V 2025). Override individual fields when
instantiating — the rest stay at the defaults.

Grid fee values are sourced from AustrianGridFees (pvtool.market.grid_fees).
Run AustrianGridFees().summary() to see the full breakdown.

Example
-------
>>> cfg = BatteryConfig(c_rate=0.5, cost_eur_per_kwh=280)
>>> mkt = MarketConfig()  # Steiermark 2025 defaults
>>> mkt = MarketConfig(grid_fees_eur_per_kwh=0.109)  # Doppeltarif NT
"""

from dataclasses import dataclass, field
from typing import List

from pvtool.market.grid_fees import AustrianGridFees

# Shared grid fee instance used to populate MarketConfig defaults.
# Import and adjust in your notebook if your tariff differs.
_grid = AustrianGridFees()


@dataclass
class BatteryConfig:
    """Battery hardware and capital-cost parameters."""

    # Simulation sweep
    sizes_kwh: List[float] = field(
        default_factory=lambda: [0, 25, 50, 75, 100]
    )

    # Electrical
    charge_efficiency: float = 0.95       # one-way charge efficiency
    discharge_efficiency: float = 0.95    # one-way discharge efficiency
    c_rate: float = 0.5                   # max charge/discharge = capacity × c_rate
    min_soc_pct: float = 5.0             # minimum SOC as % of capacity
    max_soc_pct: float = 95.0            # maximum SOC as % of capacity
    dt_hours: float = 5.0 / 60.0         # interval length (5-minute data)

    # Economics
    cost_eur_per_kwh: float = 300.0       # EUR per kWh usable capacity
    inverter_cost_eur_per_kw: float = 0.0 # EUR per kW inverter rating
    installation_fixed_eur: float = 0.0   # fixed installation cost
    annual_maintenance_eur: float = 500.0 # annual O&M cost

    # Lifetime & degradation
    lifetime_years: int = 15
    warranty_cycles: int = 6000
    degradation_pct_per_year: float = 2.0  # capacity loss per year


@dataclass
class MarketConfig:
    """
    Electricity market and price parameters.

    Defaults are set from AustrianGridFees() (Energienetze Steiermark, SNE-V 2025).
    Override any field at instantiation time.

    grid_fees_eur_per_kwh is the network-only component (Netznutzung +
    Netzdienstleistung + taxes) added on top of the commodity/spot price.
    """

    # Scenario 1 — fixed retail tariff (commodity + grid + taxes all-in)
    grid_buy_price_eur: float = 0.25       # EUR/kWh retail all-in price (to be confirmed)
    feedin_tariff_eur: float = 0.08         # EUR/kWh OeMAG/market feed-in payment (set per contract)

    # Scenario 2 & 3 — spot market: grid fee added on top of spot price
    # Source: AustrianGridFees().consumption_fee() = NE7 flat, SNE-V 2025
    grid_fees_eur_per_kwh: float = field(default_factory=lambda: _grid.consumption_fee())
    # HT/NT variants (Doppeltarif, SNE-V 2025):
    #   HT: AustrianGridFees().consumption_fee(tou=True, peak=True)  = 0.1325 EUR/kWh
    #   NT: AustrianGridFees().consumption_fee(tou=True, peak=False) = 0.1037 EUR/kWh

    # Grid fee applied specifically when charging the battery from the grid.
    # Under ElWG § 16b (Doppelbesteuerungsbefreiung), storage systems may be exempt
    # from grid fees on charging energy. Set to 0.0 to model full exemption.
    # Set to None to use grid_fees_eur_per_kwh (no exemption, default).
    # Source: AustrianGridFees(storage_exemption=True).charging_fee() = 0.0
    charging_grid_fees_eur_per_kwh: float | None = None

    feedin_spot_discount: float = 0.0      # aggregator discount on spot feed-in

    # Financial
    discount_rate_pct: float = 4.0         # discount rate for NPV

    # Scenario 3 — ancillary services (FCR)
    fcr_revenue_eur_per_kw_year: float = 80.0  # EUR/kW/year FCR capacity price
    fcr_soc_reserve_pct: float = 20.0          # SOC reserved for FCR obligations
    fcr_availability: float = 0.85             # fraction of year battery is available


@dataclass
class PeakShavingConfig:
    """Peak shaving scenario parameters (Austrian Leistungspreis / demand charge)."""

    # Grid connection threshold — battery discharges whenever grid draw exceeds this
    peak_threshold_kw: float = 350

    # Demand charge rate: EUR per kW of peak monthly demand, per year
    # Typical Austrian NE7 Leistungspreis range: 80–180 EUR/kW/year
    demand_charge_eur_per_kw_year: float = 63.0

    # Optional manual baseline peak (kW).
    # If set, overrides the value computed from the data for the demand-savings calculation.
    # Useful when the raw data contains spikes you know are measurement errors.
    # Set to None to always compute from data.
    baseline_peak_kw: float | None = None

    # Dispatch mode:
    #   "greedy"  — reactive: discharge whenever grid draw exceeds threshold (fast)
    #   "optimal" — LP via CVXPY/HiGHS: minimises the true peak with full-year foresight
    #               requires: pip install cvxpy  (~30–90 s per battery size)
    mode: str = "greedy"

    # Combined mode: also discharge for self-consumption when demand is below threshold.
    # When False (default), the battery only discharges for peak shaving.
    # When True, the battery also displaces grid purchases below the threshold,
    # combining demand-charge savings with energy-cost savings.
    combine_self_consumption: bool = True


@dataclass
class RegelenergieConfig:
    """Parameters for Regelenergie (balancing reserve) estimation and simulation.

    Phase 2 fields (estimation): capacity prices per kW/year, availability.
    Phase 4 fields (simulation): block prices, SOC management, activation model.
    """

    # --- Phase 2: Estimation parameters ---

    # Capacity prices (EUR/kW/year) — typical Austrian FCR cooperation results
    fcr_capacity_eur_per_kw_year: float = 80.0
    afrr_capacity_eur_per_kw_year: float = 50.0

    # Availability factor — fraction of year the battery can participate
    # (accounts for maintenance, degradation, SOC constraints)
    availability: float = 0.85

    # SOC reserved for FCR symmetric obligation (% of capacity)
    fcr_soc_reserve_pct: float = 20.0

    # Battery sizing (independent from BatteryConfig — Regelenergie targets
    # larger standalone storage, not residential PV systems)
    sizes_kwh: List[float] = field(
        default_factory=lambda: [0, 500, 1000, 5000, 7500, 10000]
    )
    c_rate: float = 0.5  # inverter kW = capacity * c_rate

    # Economics
    cost_eur_per_kwh: float = 300.0
    lifetime_years: int = 15
    discount_rate_pct: float = 4.0
    annual_maintenance_eur: float = 500.0

    # Minimum battery size for FCR participation (MW) — regelleistung.net
    # requires 1 MW minimum bid, but pooling allows smaller units
    min_pool_kw: float = 0.0  # set to e.g. 1000 to enforce 1 MW minimum

    # --- Phase 4: Simulation parameters ---

    # FCR block price (EUR/MW per 4h block, from regelleistung.net auctions)
    # Typical range: 5–15 EUR/MW/block (~7,300–21,900 EUR/MW/year)
    fcr_block_price_eur_per_mw: float = 10.0

    # aFRR capacity prices per 4h block (asymmetric: up vs down)
    afrr_up_block_price_eur_per_mw: float = 8.0
    afrr_down_block_price_eur_per_mw: float = 6.0

    # Battery electrical (independent from BatteryConfig for large storage)
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    min_soc_pct: float = 5.0
    max_soc_pct: float = 95.0

    # FCR SOC management
    fcr_target_soc_pct: float = 50.0         # target SOC for symmetric response
    fcr_soc_deadband_pct: float = 10.0       # no rebalancing within ±deadband of target
    fcr_rebalance_cost_eur_per_kwh: float = 0.005  # bid-ask spread for SOC re-centering (~5 EUR/MWh)

    # Synthetic activation model — calibrated to ENTSO-E frequency quality statistics
    fcr_mean_activation_fraction: float = 0.15   # avg ~15% of contracted MW activated
    fcr_activation_std: float = 0.10             # std dev of activation fraction
    afrr_activation_probability: float = 0.25    # fraction of hours aFRR is activated
    afrr_mean_activation_fraction: float = 0.30  # when activated, avg 30% of contracted MW

    # Degradation
    degradation_pct_per_year: float = 2.0
    warranty_cycles: int = 6000


@dataclass
class HeatPumpConfig:
    """Heat pump simulation parameters.

    Models a water-to-water or air-to-water heat pump replacing gas heating.
    COP depends on both outdoor temperature and heating system inlet temperature.
    """

    # Thermal demand
    annual_thermal_kwh: float = 120_000.0   # annual heating demand (kWh thermal)
    heating_threshold_c: float = 15.0       # no heating above this outdoor temp

    # Heating system
    inlet_temp_c: float = 65.0              # heating system supply temperature (°C)
    # Scenarios to compare: [45, 55, 65] for retrofit analysis

    # COP model: COP = cop_base - cop_slope * (inlet_temp - outdoor_temp)
    # Fitted to manufacturer data (Carnot-fraction approach):
    #   COP ≈ eta_carnot * T_hot / (T_hot - T_cold)  with eta_carnot ~ 0.45
    # Simplified linear approximation per inlet temp:
    #   65°C inlet: COP 1.5–2.5 depending on outdoor temp
    #   45°C inlet: COP 2.5–4.5 depending on outdoor temp
    cop_carnot_efficiency: float = 0.45     # fraction of Carnot COP achieved
    cop_min: float = 1.5                    # COP floor (defrost, part-load losses)
    cop_max: float = 5.5                    # COP ceiling

    # Outdoor temperature model (Austrian lowlands default, overridable for web tool)
    mean_outdoor_temp_c: float = 10.0       # annual mean outdoor temperature
    outdoor_temp_amplitude_c: float = 12.0  # seasonal half-amplitude (peak-to-trough / 2)

    # Bivalent operation: HP turns off below this outdoor temperature (°C).
    # Gas boiler provides backup heating for the coldest periods.
    # Allows a smaller/cheaper HP that doesn't need to cover the design-day peak.
    # None = monovalent (HP always on, must cover full peak).
    # Typical values: -5.0 (mild bivalent) to +2.0 (aggressive, ~80% coverage)
    bivalent_point_c: float | None = None

    # Thermal storage (hot water buffer tank)
    thermal_storage_kwh: float = 0.0        # buffer tank capacity (kWh thermal), 0=none
    # Rule of thumb: 1000L tank at ΔT=30K ≈ 35 kWh thermal
    thermal_storage_loss_pct_per_hour: float = 0.5  # standby loss (%/hour)

    # Economics
    gas_price_eur_per_kwh: float = 0.08     # current gas price (EUR/kWh thermal)
    gas_boiler_efficiency: float = 0.90     # gas boiler conversion efficiency
    hp_capex_eur: float = 25_000.0          # heat pump purchase + installation
    hp_lifetime_years: int = 20
    hp_annual_maintenance_eur: float = 300.0


@dataclass
class DataConfig:
    """Column-name mapping for the input DataFrame."""

    timestamp_col: str = "timestamp"
    production_col: str = "production_kWh"
    consumption_col: str = "consumption_kWh"
    surplus_col: str = "surplus_kWh"
    spot_price_col: str = "price_eur_kwh"     # EUR/kWh spot price
    spot_mwh_col: str = "price_eur_mwh"       # EUR/MWh spot price (visualisation)
