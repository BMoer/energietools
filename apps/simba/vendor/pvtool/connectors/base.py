"""Abstract base class for data connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class BaseConnector(ABC):
    """
    Common interface for all data sources (Solis, Huawei, CSV, PVGIS, …).

    Subclasses must implement ``fetch_day`` and ``fetch_range``.
    All connectors return DataFrames with standardised column names:

    timestamp         datetime64[ns]  — UTC
    production_kWh    float           — PV production per interval
    consumption_kWh   float           — Household load per interval
    surplus_kWh       float           — production_kWh − consumption_kWh
    """

    @abstractmethod
    def fetch_day(self, day: date) -> pd.DataFrame:
        """Fetch one day of 5-minute interval data."""
        ...

    @abstractmethod
    def fetch_range(self, start: date, end: date) -> pd.DataFrame:
        """Fetch a date range of 5-minute interval data."""
        ...

    def validate(self, df: pd.DataFrame) -> None:
        """Raise ValueError if required columns are missing."""
        required = {"timestamp", "production_kWh", "consumption_kWh", "surplus_kWh"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame is missing columns: {missing}")
