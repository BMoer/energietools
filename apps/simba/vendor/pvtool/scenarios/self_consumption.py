"""Scenario 1: PV self-consumption with fixed electricity tariffs."""

from __future__ import annotations

import pandas as pd

from .base import BaseScenario
from ..battery import simulate_battery


class SelfConsumptionScenario(BaseScenario):
    """
    Charge from PV surplus, discharge to cover household deficit.
    Uses fixed grid buy price and feed-in tariff (no spot prices needed).
    """

    def run(self, df: pd.DataFrame, capacity_kwh: float) -> dict:
        return simulate_battery(
            df, capacity_kwh,
            strategy="self_consumption",
            battery_cfg=self.battery_cfg,
            market_cfg=self.market_cfg,
            data_cfg=self.data_cfg,
        )
