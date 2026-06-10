# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
"""Composable LoadBuilder — Golden-Tests gegen die pvtool-Referenz (HP/EV/DHW)."""

import pytest

from energietools.tools.load_builder import (
    EVSpec,
    LoadSpec,
    build_load,
    heatpump_load,
    outdoor_temperature,
)


def _spec() -> LoadSpec:
    return LoadSpec(
        household_annual_kwh=4500,
        has_heatpump=True, hp_annual_thermal_kwh=20000, hp_inlet_temp_c=45,
        hp_bivalent_point_c=None, hp_heating_threshold_c=15,
        mean_outdoor_temp_c=10, outdoor_temp_amplitude_c=12,
        has_ev=True, ev=EVSpec(daily_km=40, consumption_kwh_per_100km=18,
            charging_power_kw=11, charging_start_hour=18, charging_end_hour=6, weekend_factor=0.6),
        has_dhw=True, dhw_annual_kwh=2000,
    )


def test_annual_sums_match_pvtool():
    res = build_load(_spec(), year=2025)
    assert len(res.timestamps) == 8760
    s = res.annual_summary()
    assert s["hp_electricity_kwh"] == pytest.approx(7356.6, abs=1.0)
    assert s["ev_kwh"] == pytest.approx(2328.5, abs=1.0)
    assert s["dhw_kwh"] == pytest.approx(2000.0, abs=0.5)
    assert s["household_kwh"] == pytest.approx(4500.0, abs=1.0)


def test_outdoor_temperature_and_cop_points():
    res = build_load(_spec(), year=2025)
    out = outdoor_temperature(res.timestamps, 10, 12)
    assert out[0] == pytest.approx(0.9449, abs=0.001)
    assert out[12] == pytest.approx(-4.2513, abs=0.001)
    assert out[4380] == pytest.approx(19.03, abs=0.01)


def test_ev_window_and_value():
    res = build_load(_spec(), year=2025)
    # 2025-01-01 = Mittwoch (Werktag): 12 Fenster-Stunden, 7,2 kWh/12 = 0,6 je Stunde
    ev = res.ev_kwh
    for h in list(range(0, 6)) + list(range(18, 24)):
        assert ev[h] == pytest.approx(0.6, abs=0.001)
    for h in range(6, 18):  # außerhalb Fenster
        assert ev[h] == pytest.approx(0.0, abs=1e-9)


def test_dhw_peaks():
    res = build_load(_spec(), year=2025)
    dhw = res.dhw_kwh
    assert dhw[7] == pytest.approx(0.7061, abs=0.001)
    assert dhw[19] == pytest.approx(0.5331, abs=0.001)
    assert dhw[3] == pytest.approx(0.1179, abs=0.001)


def test_components_disabled_by_default():
    res = build_load(LoadSpec(household_annual_kwh=3000), year=2025)
    assert res.hp_electricity_kwh == []
    assert res.ev_kwh == []
    assert res.dhw_kwh == []
    assert sum(res.consumption_kwh) == pytest.approx(3000.0, abs=1.0)


def test_bivalent_reduces_hp_electricity():
    from energietools.tools.load_builder import _hourly_timestamps

    ts = _hourly_timestamps(2025)
    mono = sum(heatpump_load(ts, annual_thermal_kwh=20000, inlet_temp_c=45))
    biv = sum(heatpump_load(ts, annual_thermal_kwh=20000, inlet_temp_c=45, bivalent_point_c=2.0))
    # Bivalent: WP läuft nicht unter 2 °C → Gas übernimmt den kältesten Anteil,
    # die WP liefert weniger thermische Energie → weniger Strom.
    assert biv < mono
