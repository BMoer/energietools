"""Scenario 2: PV + spot-market price-aware dispatch."""

from __future__ import annotations

import pandas as pd

from .base import BaseScenario
from ..battery import simulate_battery


class SpotMarketScenario(BaseScenario):
    """
    Combines PV self-consumption with spot-price optimisation.
    Charges from grid during cheap hours; discharges (or exports) during expensive hours.
    Costs include grid fees (Netzentgelte) on top of spot price.
    """

    def run(self, df: pd.DataFrame, capacity_kwh: float) -> dict:
        return simulate_battery(
            df, capacity_kwh,
            strategy="spot_optimized",
            battery_cfg=self.battery_cfg,
            market_cfg=self.market_cfg,
            data_cfg=self.data_cfg,
        )
