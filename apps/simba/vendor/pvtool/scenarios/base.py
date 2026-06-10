"""Base class for all battery scenarios."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseScenario(ABC):
    """
    Abstract base for battery dispatch scenarios.

    Subclasses implement ``run()`` for a single battery size.
    ``run_all_sizes()`` iterates over ``battery_cfg.sizes_kwh``.
    """

    def __init__(self, battery_cfg=None, market_cfg=None, data_cfg=None):
        from ..config import BatteryConfig, MarketConfig, DataConfig
        self.battery_cfg = battery_cfg or BatteryConfig()
        self.market_cfg = market_cfg or MarketConfig()
        self.data_cfg = data_cfg or DataConfig()

    @abstractmethod
    def run(self, df: pd.DataFrame, capacity_kwh: float) -> dict:
        """Run the scenario for one battery size. Returns metrics dict."""
        ...

    def run_all_sizes(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        """
        Run for every size in battery_cfg.sizes_kwh.

        Returns
        -------
        df_results : pd.DataFrame
            One row per battery size (no soc_timeseries column).
        soc_data : dict
            {capacity_kwh: soc_timeseries_array} for non-zero sizes.
        """
        rows = []
        soc_data = {}
        for cap in self.battery_cfg.sizes_kwh:
            result = self.run(df, cap)
            soc = result.pop("soc_timeseries")
            if cap > 0:
                soc_data[cap] = soc
            rows.append(result)
        return pd.DataFrame(rows), soc_data
