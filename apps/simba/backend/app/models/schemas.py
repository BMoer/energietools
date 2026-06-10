"""Pydantic schemas mirroring pvtool config dataclasses.

These are the request/response models for the API. They map 1:1 to the
pvtool dataclasses so conversion is trivial.
"""

from pydantic import BaseModel, Field

# --- Request models ---


class BatteryParams(BaseModel):
    """Battery configuration (mirrors pvtool.config.BatteryConfig)."""

    sizes_kwh: list[float] = Field(default=[0, 25, 50, 75, 100])
    charge_efficiency: float = Field(default=0.95, ge=0.0, le=1.0)
    discharge_efficiency: float = Field(default=0.95, ge=0.0, le=1.0)
    c_rate: float = Field(default=0.5, gt=0.0)
    min_soc_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    max_soc_pct: float = Field(default=95.0, ge=0.0, le=100.0)
    dt_hours: float = Field(default=5.0 / 60.0, gt=0.0)
    cost_eur_per_kwh: float = Field(default=300.0, ge=0.0)
    lifetime_years: int = Field(default=15, gt=0)
    degradation_pct_per_year: float = Field(default=2.0, ge=0.0)


class MarketParams(BaseModel):
    """Market configuration (mirrors pvtool.config.MarketConfig)."""

    grid_buy_price_eur: float = Field(default=0.25, ge=0.0)
    feedin_tariff_eur: float = Field(default=0.08, ge=0.0)
    grid_fees_eur_per_kwh: float = Field(default=0.1311, ge=0.0)
    charging_grid_fees_eur_per_kwh: float | None = Field(default=None)
    feedin_spot_discount: float = Field(default=0.0, ge=0.0, le=1.0)
    discount_rate_pct: float = Field(default=4.0)
    fcr_revenue_eur_per_kw_year: float = Field(default=80.0, ge=0.0)


class PeakShavingParams(BaseModel):
    """Peak shaving configuration."""

    peak_threshold_kw: float = Field(default=350.0, gt=0.0)
    demand_charge_eur_per_kw_year: float = Field(default=63.0, ge=0.0)
    mode: str = Field(default="greedy", pattern="^(greedy|optimal)$")
    combine_self_consumption: bool = Field(default=True)


class EVParams(BaseModel):
    """EV charging configuration."""

    daily_km: float = Field(default=40.0, ge=0.0, description="Average daily driving distance (km)")
    consumption_kwh_per_100km: float = Field(default=18.0, ge=5.0, le=40.0, description="EV efficiency")
    battery_kwh: float = Field(default=60.0, gt=0.0, description="EV battery capacity")
    charging_power_kw: float = Field(default=11.0, gt=0.0, description="Wallbox power (kW)")
    charging_start_hour: float = Field(default=18.0, ge=0.0, lt=24.0, description="Start charging (hour)")
    charging_end_hour: float = Field(default=6.0, ge=0.0, lt=24.0, description="Stop charging (hour)")
    weekend_factor: float = Field(default=0.6, ge=0.0, le=2.0, description="Weekend driving factor")


class LoadProfileParams(BaseModel):
    """Composable load profile configuration."""

    # Base household
    household_annual_kwh: float = Field(default=4500.0, ge=0.0, description="Annual household consumption (kWh)")

    # Heat pump
    has_heatpump: bool = Field(default=False, description="Include heat pump load")
    hp_annual_thermal_kwh: float = Field(default=20000.0, ge=0.0, description="Annual thermal demand (kWh)")
    hp_inlet_temp_c: float = Field(default=45.0, ge=25.0, le=80.0, description="Heating system supply temp (°C)")
    hp_bivalent_point_c: float | None = Field(default=None, description="Bivalent point (°C), None=monovalent")

    # EV
    has_ev: bool = Field(default=False, description="Include EV charging load")
    ev: EVParams = Field(default_factory=EVParams)

    # Domestic hot water
    has_dhw: bool = Field(default=False, description="Include DHW load")
    dhw_annual_kwh: float = Field(default=2000.0, ge=0.0, description="Annual DHW consumption (kWh)")


class HeatPumpParams(BaseModel):
    """Heat pump scenario configuration (mirrors pvtool.config.HeatPumpConfig)."""

    annual_thermal_kwh: float = Field(default=20000.0, ge=0.0, description="Annual heating demand (kWh)")
    inlet_temp_c: float = Field(default=45.0, ge=25.0, le=80.0, description="Heating system supply temp (°C)")
    bivalent_point_c: float | None = Field(default=None, description="Outdoor temp for gas backup (°C), None=monovalent")
    thermal_storage_kwh: float = Field(default=0.0, ge=0.0, description="Buffer tank capacity (kWh thermal)")
    gas_price_eur_per_kwh: float = Field(default=0.08, ge=0.0, description="Gas price (EUR/kWh thermal)")
    gas_boiler_efficiency: float = Field(default=0.90, ge=0.1, le=1.0, description="Existing gas boiler efficiency")
    hp_capex_eur: float = Field(default=25000.0, ge=0.0, description="Heat pump purchase + installation (EUR)")


class SimulationRequest(BaseModel):
    """Request body for POST /api/simulate."""

    battery: BatteryParams = Field(default_factory=BatteryParams)
    market: MarketParams = Field(default_factory=MarketParams)
    peak_shaving: PeakShavingParams | None = None
    heatpump: HeatPumpParams | None = None
    scenarios: list[str] = Field(
        default=["self_consumption"],
        description="Scenarios to run: self_consumption, spot_optimized, arbitrage, peak_shaving, heatpump",
    )
    data_source: str = Field(
        default="sample",
        description="'sample' for demo data, or a data_id from a previous upload",
    )


# --- Response models ---


class ScenarioResult(BaseModel):
    """Result for one battery size in one scenario."""

    capacity_kwh: float
    strategy: str
    grid_purchase_kwh: float
    grid_feedin_kwh: float
    batt_charged_kwh: float
    batt_discharged_kwh: float
    cycles: float
    revenue_eur: float
    cost_eur: float
    net_benefit_eur: float
    annual_savings_eur: float = 0.0  # computed: net_benefit minus baseline
    peak_reduction_kw: float | None = None


class ROIResult(BaseModel):
    """ROI calculation for one battery size."""

    capacity_kwh: float
    label: str
    capex_eur: float
    annual_savings_eur: float
    payback_years: float | None
    npv_eur: float
    lcoe_eur_per_kwh: float | None = None


class HeatPumpSummary(BaseModel):
    """Heat pump scenario summary — gas baseline vs HP economics."""

    inlet_temp_c: float
    thermal_storage_kwh: float
    average_cop: float
    gas_cost_baseline_eur: float
    hp_annual_electricity_kwh: float
    residual_gas_kwh: float
    residual_gas_cost_eur: float
    hp_covered_thermal_kwh: float
    pv_to_hp_kwh: float
    grid_to_hp_kwh: float
    self_consumption_rate_before: float
    self_consumption_rate_after: float


class SimulationResponse(BaseModel):
    """Response from POST /api/simulate."""

    scenarios: dict[str, list[ScenarioResult]]
    roi: list[ROIResult] | None = None
    heatpump_summary: HeatPumpSummary | None = None
    warnings: list[str] = Field(default_factory=list)
