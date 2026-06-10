"""
pvtool — Solar PV Battery Simulation Toolkit

Austrian-market battery storage analysis: self-consumption, spot optimisation,
and arbitrage / ancillary-service revenue.

Quick start
-----------
>>> from pvtool.config import BatteryConfig, MarketConfig
>>> from pvtool.battery import simulate_battery
>>> result = simulate_battery(df, capacity_kwh=100, strategy="self_consumption")
"""

from .config import BatteryConfig, MarketConfig, DataConfig, HeatPumpConfig
from .battery import simulate_battery

__version__ = "0.1.0"
__all__ = ["BatteryConfig", "MarketConfig", "DataConfig", "HeatPumpConfig", "simulate_battery"]
