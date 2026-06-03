# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die heatpump-Capability (Heizkostenvergleich WP vs. Gas, COP real)."""

from __future__ import annotations

import pytest

from energietools.capabilities.heatpump.capability import HeatPumpCapability


def test_heatpump_comparison_is_consistent() -> None:
    res = HeatPumpCapability().run(
        waermebedarf_kwh_jahr=15000,
        vorlauftemperatur_c=45,
        aussentemperatur_c=2,
        strompreis_ct_kwh=25,
        gaspreis_ct_kwh=10,
    )
    assert res.ok
    d = res.data
    assert d["cop_schaetzung"] > 1.0  # heat pump delivers more heat than electricity
    # electricity demand = thermal / COP (capability uses the unrounded COP internally).
    assert d["wp_strombedarf_kwh_jahr"] == pytest.approx(15000 / d["cop_schaetzung"], rel=1e-3)
    assert "Schätzung" in d["hinweis"]


def test_heatpump_requires_inputs() -> None:
    res = HeatPumpCapability().run(waermebedarf_kwh_jahr=15000)
    assert not res.ok
    assert "erforderlich" in (res.error or "") or "muss" in (res.error or "")
