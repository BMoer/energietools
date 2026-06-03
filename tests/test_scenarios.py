# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die scenarios-Capability (ersetzt battery_sim) + den Dispatch-Runner."""

from __future__ import annotations

import pytest

from energietools.capabilities.registry import default_registry
from energietools.capabilities.scenarios import run_self_consumption
from energietools.capabilities.scenarios.capability import ScenariosCapability
from energietools.components.battery import Battery

# Ein Tagesmuster (4 x 6 h): Mittagssonne, gleichmäßiger Verbrauch.
_PROD = [{"kwh": 0.0}, {"kwh": 4.0}, {"kwh": 4.0}, {"kwh": 0.0}]
_CONS = [{"kwh": 1.0}, {"kwh": 1.0}, {"kwh": 1.0}, {"kwh": 1.0}]


def test_battery_sim_is_gone() -> None:
    # Delete-evidence: das alte Modul existiert nicht mehr.
    with pytest.raises(ModuleNotFoundError):
        __import__("energietools.tools.battery_sim")


def test_scenarios_replaces_battery_sim_in_registry() -> None:
    names = set(default_registry().names)
    assert "scenarios" in names
    assert "battery_sim" not in names


def test_dispatch_bigger_battery_raises_self_consumption() -> None:
    prod = [0.0, 4.0, 4.0, 0.0]
    cons = [1.0, 1.0, 1.0, 1.0]
    small = run_self_consumption(prod, cons, Battery.new(0.0), dt_hours=6.0)
    big = run_self_consumption(prod, cons, Battery.new(10.0), dt_hours=6.0)
    assert big.self_consumption_rate >= small.self_consumption_rate
    assert big.self_sufficiency_rate >= small.self_sufficiency_rate
    assert big.grid_import_kwh <= small.grid_import_kwh


def test_scenarios_capability_sweep_with_roi() -> None:
    res = ScenariosCapability().run(
        production_data=_PROD,
        consumption_data=_CONS,
        sizes_kwh=[0.0, 5.0, 10.0],
        energiepreis_ct_kwh=25.0,
        einspeisung_ct_kwh=8.0,
        speicher_kosten_eur_pro_kwh=600.0,
        nutzungsdauer_jahre=15,
        diskontrate=0.04,
        dt_hours=6.0,
    )
    assert res.ok
    data = res.data
    assert len(data["szenarien"]) == 3
    # Each non-baseline row carries finance-derived ROI fields.
    row = next(r for r in data["szenarien"] if r["kapazitaet_kwh"] == 10.0)
    assert "amortisation_jahre" in row and "npv_eur" in row
    assert 0.0 <= row["eigenverbrauchsquote"] <= 1.0
    # The estimate is labelled as such (audit honesty).
    assert "Schätzung" in data["hinweis"]


def test_scenarios_requires_economics_no_magic_defaults() -> None:
    res = ScenariosCapability().run(production_data=_PROD, consumption_data=_CONS)
    assert not res.ok
    assert "erforderlich" in (res.error or "") or "muss" in (res.error or "")
