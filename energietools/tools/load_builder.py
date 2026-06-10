# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
#
# Herkunft: Port von ``pvtool.connectors.load_builder`` + ``heatpump_profile``
# (batterystorage-sim, Jakob/holzjfk-a11y, MIT — siehe CREDITS.md). Pandas-/numpy-
# frei, stündlich. Der Haushalt nutzt das bestehende ``h0_profile``, die COP die
# bestehende ``HeatPump``-Komponente (identische Carnot-Fraktion). EV-, DHW- und
# Außentemperatur-/Wärmepumpen-Profil sind 1:1 übernommen.
"""Komponierbares Lastprofil: Haushalt + Wärmepumpe + E-Auto + Warmwasser (stündlich)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from energietools.components.heatpump import HeatPump
from energietools.tools.h0_profile import synthesize_h0_consumption

_HEATING_HOURS = 1.0  # stündliche Auflösung (interval_hours)


@dataclass(frozen=True)
class EVSpec:
    """E-Auto-Lade-Parameter (einfaches Tagesmuster im Ladefenster)."""

    daily_km: float = 40.0
    consumption_kwh_per_100km: float = 18.0
    charging_power_kw: float = 11.0
    charging_start_hour: float = 18.0
    charging_end_hour: float = 6.0  # über Nacht, wenn start > end
    weekend_factor: float = 0.6


@dataclass(frozen=True)
class LoadSpec:
    """Konfiguration der Lastkomponenten (Komponenten einzeln zuschaltbar)."""

    household_annual_kwh: float = 4500.0
    has_heatpump: bool = False
    hp_annual_thermal_kwh: float = 20_000.0
    hp_inlet_temp_c: float = 45.0
    hp_bivalent_point_c: float | None = None
    hp_heating_threshold_c: float = 15.0
    mean_outdoor_temp_c: float = 10.0
    outdoor_temp_amplitude_c: float = 12.0
    has_ev: bool = False
    ev: EVSpec = field(default_factory=EVSpec)
    has_dhw: bool = False
    dhw_annual_kwh: float = 2000.0


@dataclass(frozen=True)
class LoadProfileResult:
    """Stündliches Lastprofil + Komponenten-Spuren (kWh je Stunde)."""

    timestamps: list[datetime]
    household_kwh: list[float]
    hp_electricity_kwh: list[float]  # leere Liste, wenn deaktiviert
    ev_kwh: list[float]
    dhw_kwh: list[float]
    consumption_kwh: list[float]

    def annual_summary(self) -> dict[str, float]:
        out = {
            "total_annual_kwh": round(sum(self.consumption_kwh), 0),
            "household_kwh": round(sum(self.household_kwh), 0),
        }
        if self.hp_electricity_kwh:
            out["hp_electricity_kwh"] = round(sum(self.hp_electricity_kwh), 0)
        if self.ev_kwh:
            out["ev_kwh"] = round(sum(self.ev_kwh), 0)
        if self.dhw_kwh:
            out["dhw_kwh"] = round(sum(self.dhw_kwh), 0)
        return out


def _hourly_timestamps(year: int) -> list[datetime]:
    start, end = datetime(year, 1, 1), datetime(year + 1, 1, 1)
    out, cur = [], start
    while cur < end:
        out.append(cur)
        cur += timedelta(hours=1)
    return out


def outdoor_temperature(
    timestamps: list[datetime], mean_c: float = 10.0, amplitude_c: float = 12.0
) -> list[float]:
    """Synthetische Außentemperatur: saisonaler Kosinus (kältester ~15.1.) + ±3 K Tagesgang."""
    out = []
    for ts in timestamps:
        doy = ts.timetuple().tm_yday
        hour = ts.hour + ts.minute / 60.0
        daily = mean_c - amplitude_c * math.cos(2 * math.pi * (doy - 15) / 365)
        out.append(daily - 3 * math.cos(2 * math.pi * (hour - 14) / 24))
    return out


def heatpump_load(
    timestamps: list[datetime],
    *,
    annual_thermal_kwh: float,
    inlet_temp_c: float,
    heating_threshold_c: float = 15.0,
    bivalent_point_c: float | None = None,
    mean_outdoor_temp_c: float = 10.0,
    outdoor_temp_amplitude_c: float = 12.0,
) -> list[float]:
    """Wärmepumpen-Stromlast: Wärmebedarf (Gradtag-Gewicht) → COP → Strom."""
    outdoor = outdoor_temperature(timestamps, mean_outdoor_temp_c, outdoor_temp_amplitude_c)
    hp = HeatPump(inlet_temp_c=inlet_temp_c)
    cop = [hp.cop(t, inlet_temp_c) for t in outdoor]

    full_need = [max(heating_threshold_c - t, 0.0) for t in outdoor]
    full_dd = sum(full_need)
    if bivalent_point_c is not None:
        hp_need = [n if t >= bivalent_point_c else 0.0 for n, t in zip(full_need, outdoor)]
    else:
        hp_need = full_need
    hp_dd = sum(hp_need)
    if full_dd <= 0 or hp_dd <= 0:
        return [0.0] * len(timestamps)
    scale = annual_thermal_kwh / full_dd  # = annual * hp_fraction / hp_dd
    return [need * scale / c for need, c in zip(hp_need, cop)]


def ev_load(timestamps: list[datetime], ev: EVSpec) -> list[float]:
    """E-Auto-Ladelast: Tagesbedarf gleichmäßig im Ladefenster, Wochenend-Faktor."""
    n = len(timestamps)
    daily_kwh = ev.daily_km * ev.consumption_kwh_per_100km / 100.0
    overnight = ev.charging_start_hour > ev.charging_end_hour

    def _in_window(ts: datetime) -> bool:
        h = ts.hour + ts.minute / 60.0
        if overnight:
            return h >= ev.charging_start_hour or h < ev.charging_end_hour
        return ev.charging_start_hour <= h < ev.charging_end_hour

    max_per_interval = ev.charging_power_kw * _HEATING_HOURS
    out = [0.0] * n
    by_day: dict[object, list[int]] = {}
    for i, ts in enumerate(timestamps):
        if _in_window(ts):
            by_day.setdefault(ts.date(), []).append(i)
    for day, idxs in by_day.items():
        factor = ev.weekend_factor if day.weekday() >= 5 else 1.0
        needed = daily_kwh * factor
        per_interval = min(needed / len(idxs), max_per_interval)
        for i in idxs:
            out[i] = per_interval
    return out


def dhw_load(timestamps: list[datetime], dhw_annual_kwh: float) -> list[float]:
    """Warmwasser-Last: Morgen- (7h) + Abend-Peak (19,5h) + Grundlast, auf Jahr skaliert."""
    def _pattern(ts: datetime) -> float:
        h = ts.hour + ts.minute / 60.0
        morning = math.exp(-0.5 * ((h - 7.0) / 1.0) ** 2)
        evening = math.exp(-0.5 * ((h - 19.5) / 1.0) ** 2)
        return 0.1 + 0.5 * morning + 0.4 * evening

    pattern = [_pattern(ts) for ts in timestamps]
    raw_annual = sum(pattern) * _HEATING_HOURS
    scale = dhw_annual_kwh / raw_annual if raw_annual > 0 else 0.0
    return [p * scale * _HEATING_HOURS for p in pattern]


def build_load(spec: LoadSpec, year: int = 2025) -> LoadProfileResult:
    """Komponiert das stündliche Gesamt-Lastprofil aus den aktiven Komponenten."""
    ts = _hourly_timestamps(year)
    household = [p["kwh"] for p in synthesize_h0_consumption(
        spec.household_annual_kwh, datetime(year, 1, 1), datetime(year + 1, 1, 1)
    )]
    if len(household) != len(ts):  # Defensive: H0 muss zur Stundenraster passen
        household = (household + [0.0] * len(ts))[: len(ts)]

    hp = heatpump_load(
        ts, annual_thermal_kwh=spec.hp_annual_thermal_kwh, inlet_temp_c=spec.hp_inlet_temp_c,
        heating_threshold_c=spec.hp_heating_threshold_c, bivalent_point_c=spec.hp_bivalent_point_c,
        mean_outdoor_temp_c=spec.mean_outdoor_temp_c,
        outdoor_temp_amplitude_c=spec.outdoor_temp_amplitude_c,
    ) if spec.has_heatpump else []
    ev = ev_load(ts, spec.ev) if spec.has_ev else []
    dhw = dhw_load(ts, spec.dhw_annual_kwh) if spec.has_dhw else []

    total = list(household)
    for series in (hp, ev, dhw):
        if series:
            total = [a + b for a, b in zip(total, series)]

    return LoadProfileResult(
        timestamps=ts, household_kwh=household,
        hp_electricity_kwh=hp, ev_kwh=ev, dhw_kwh=dhw, consumption_kwh=total,
    )
