"""
CSV/Excel import connector with flexible column mapping.

Allows users without Solis/Huawei hardware to import their own PV data
from any CSV or Excel file and map columns to the standard pvtool format.

Example
-------
>>> from pvtool.connectors.csv_import import CsvConnector
>>> conn = CsvConnector(
...     "my_data.csv",
...     column_map={"ts": "timestamp", "pv_kwh": "production_kWh", "load_kwh": "consumption_kWh"},
...     timestamp_format="%Y-%m-%d %H:%M",
... )
>>> df = conn.load()
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .base import BaseConnector


# Default column mapping: assumes pvtool standard names already present
_DEFAULT_MAP = {
    "timestamp": "timestamp",
    "production_kWh": "production_kWh",
    "consumption_kWh": "consumption_kWh",
}


class CsvConnector(BaseConnector):
    """
    Import PV/load data from CSV or Excel files.

    Parameters
    ----------
    path : str or Path
        Path to CSV (.csv) or Excel (.xlsx, .xls) file.
    column_map : dict, optional
        Mapping from source column names to pvtool standard names.
        Keys are the column names in your file, values are pvtool names.
        At minimum, map to 'timestamp', 'production_kWh', 'consumption_kWh'.
        If 'surplus_kWh' is not mapped, it is computed automatically.
    timestamp_format : str, optional
        strftime format for parsing timestamps (e.g. '%Y-%m-%d %H:%M:%S').
        If None, pandas infers the format.
    timezone : str, optional
        Timezone of the input data (default: 'UTC'). Timestamps are
        converted to UTC for consistency with other connectors.
    separator : str, optional
        CSV separator (default: ','). Use ';' for European CSV exports.
    decimal : str, optional
        Decimal separator (default: '.'). Use ',' for European number formats.
    sheet_name : str or int, optional
        Sheet name or index for Excel files (default: 0 = first sheet).
    """

    def __init__(
        self,
        path: str | Path,
        column_map: dict[str, str] | None = None,
        timestamp_format: str | None = None,
        timezone: str = "UTC",
        separator: str = ",",
        decimal: str = ".",
        sheet_name: str | int = 0,
    ):
        self.path = Path(path)
        self.column_map = column_map or _DEFAULT_MAP
        self.timestamp_format = timestamp_format
        self.timezone = timezone
        self.separator = separator
        self.decimal = decimal
        self.sheet_name = sheet_name

    def load(self) -> pd.DataFrame:
        """
        Load and transform the file into a pvtool-standard DataFrame.

        Returns
        -------
        pd.DataFrame with columns: timestamp, production_kWh,
        consumption_kWh, surplus_kWh (all UTC).
        """
        df = self._read_file()
        df = self._apply_column_map(df)
        df = self._parse_timestamps(df)
        df = self._compute_surplus(df)
        self.validate(df)
        return df

    def fetch_day(self, day: date) -> pd.DataFrame:
        """Load full file, then filter to a single day."""
        df = self.load()
        mask = df["timestamp"].dt.date == day
        return df[mask].reset_index(drop=True)

    def fetch_range(self, start: date, end: date) -> pd.DataFrame:
        """Load full file, then filter to a date range (inclusive)."""
        df = self.load()
        mask = (df["timestamp"].dt.date >= start) & (df["timestamp"].dt.date <= end)
        return df[mask].reset_index(drop=True)

    def _read_file(self) -> pd.DataFrame:
        """Read CSV or Excel based on file extension."""
        suffix = self.path.suffix.lower()
        if suffix in (".xlsx", ".xls"):
            return pd.read_excel(self.path, sheet_name=self.sheet_name)
        elif suffix == ".csv":
            return pd.read_csv(
                self.path,
                sep=self.separator,
                decimal=self.decimal,
            )
        else:
            raise ValueError(
                f"Unsupported file format '{suffix}'. Use .csv, .xlsx, or .xls."
            )

    def _apply_column_map(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rename columns from source names to pvtool standard names."""
        rename = {}
        for src, dst in self.column_map.items():
            if src in df.columns:
                rename[src] = dst
            elif dst in df.columns:
                # Column already has the target name
                pass
            else:
                raise KeyError(
                    f"Column '{src}' not found in file. "
                    f"Available columns: {list(df.columns)}"
                )
        return df.rename(columns=rename)

    def _parse_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse and localise timestamps to UTC."""
        if self.timestamp_format:
            df["timestamp"] = pd.to_datetime(
                df["timestamp"], format=self.timestamp_format
            )
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Localise or convert to UTC
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(self.timezone).dt.tz_convert("UTC")
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")

        return df

    def _compute_surplus(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add surplus column if not already present."""
        if "surplus_kWh" not in df.columns:
            df["surplus_kWh"] = df["production_kWh"] - df["consumption_kWh"]
        return df

    def preview(self, n: int = 5) -> pd.DataFrame:
        """Quick preview: load and show first n rows (before mapping)."""
        df = self._read_file()
        print(f"File: {self.path.name}")
        print(f"Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(f"Dtypes:\n{df.dtypes}\n")
        return df.head(n)

    def detect_columns(self) -> dict:
        """
        Auto-detect likely column mappings based on common naming patterns.

        Returns a suggested column_map dict.
        """
        df = self._read_file()
        cols = [c.lower() for c in df.columns]
        original = list(df.columns)

        suggestions = {}

        # Timestamp detection
        ts_patterns = ["timestamp", "time", "datetime", "date", "zeit", "zeitstempel"]
        for pat in ts_patterns:
            for i, c in enumerate(cols):
                if pat in c:
                    suggestions[original[i]] = "timestamp"
                    break
            if "timestamp" in suggestions.values():
                break

        # Production detection
        prod_patterns = ["production", "pv", "solar", "erzeugung", "generation", "yield"]
        for pat in prod_patterns:
            for i, c in enumerate(cols):
                if pat in c and original[i] not in suggestions:
                    suggestions[original[i]] = "production_kWh"
                    break
            if "production_kWh" in suggestions.values():
                break

        # Consumption detection
        cons_patterns = ["consumption", "load", "verbrauch", "demand", "usage"]
        for pat in cons_patterns:
            for i, c in enumerate(cols):
                if pat in c and original[i] not in suggestions:
                    suggestions[original[i]] = "consumption_kWh"
                    break
            if "consumption_kWh" in suggestions.values():
                break

        return suggestions
