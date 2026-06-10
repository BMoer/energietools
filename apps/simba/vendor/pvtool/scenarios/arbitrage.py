"""Scenario 3: Standalone grid arbitrage + FCR ancillary services."""

from __future__ import annotations

import pandas as pd

from .base import BaseScenario
from ..battery import simulate_battery


class ArbitrageScenario(BaseScenario):
    """
    Pure grid arbitrage — no PV, no household load.
    Buys at low spot prices, sells at high spot prices.
    Reserves SOC headroom for FCR (Primärregelreserve) obligations.

    FCR revenue is calculated separately and added on top of arbitrage profit.
    """

    def run(self, df: pd.DataFrame, capacity_kwh: float) -> dict:
        result = simulate_battery(
            df, capacity_kwh,
            strategy="arbitrage",
            battery_cfg=self.battery_cfg,
            market_cfg=self.market_cfg,
            data_cfg=self.data_cfg,
        )
        # Attach FCR revenue
        if capacity_kwh > 0:
            inverter_kw = capacity_kwh * self.battery_cfg.c_rate
            result["inverter_kw"] = inverter_kw
            result["fcr_revenue_eur"] = round(
                inverter_kw
                * self.market_cfg.fcr_revenue_eur_per_kw_year
                * self.market_cfg.fcr_availability,
                2,
            )
            result["arbitrage_profit_eur"] = result["net_benefit_eur"]
            result["total_revenue_eur"] = round(
                result["arbitrage_profit_eur"] + result["fcr_revenue_eur"], 2
            )
        else:
            result["inverter_kw"] = 0
            result["fcr_revenue_eur"] = 0.0
            result["arbitrage_profit_eur"] = 0.0
            result["total_revenue_eur"] = 0.0
        return result
