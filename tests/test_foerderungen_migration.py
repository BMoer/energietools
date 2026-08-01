# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Migrations-Nachweis: die alten losen Kataloge sind weg, Konsumenten nutzen den neuen Loader.

Ergänzt die Löschungen im Diff (git) um einen ausführbaren Beweis, dass zur
Laufzeit niemand mehr die alten Pfade liest.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from energietools.tools.beg_advisor import _load_beg_providers
from energietools.tools.energy_monitor import load_foerderungen_catalog
from energietools.tools.pv_sim import _eag_pv_foerderung_pro_kwp


def test_alte_foerderungen_json_existiert_nicht_mehr() -> None:
    data_dir = Path(resources.files("energietools.data"))
    assert not (data_dir / "foerderungen.json").exists()


def test_alte_beg_providers_json_existiert_nicht_mehr() -> None:
    data_dir = Path(resources.files("energietools.data"))
    assert not (data_dir / "beg_providers.json").exists()


def test_energy_monitor_liest_neuen_katalog() -> None:
    """energy_monitor.py liefert die 45-Einträge-Recherche, nicht den alten 17er-Katalog."""
    catalog, stand = load_foerderungen_catalog()
    assert len(catalog) == 45
    assert stand == "2026-07-31"


def test_beg_advisor_liest_neuen_katalog() -> None:
    """beg_advisor.py liefert dieselben 3 Anbieter aus dem migrierten Subpackage."""
    providers = _load_beg_providers()
    assert len(providers) == 3
    assert {p["name"] for p in providers} == {"7Energy", "BEG Tirol", "OurPower"}


def test_pv_sim_liest_eag_satz_aus_neuem_katalog() -> None:
    """pv_sim.py's Förderschätzung nutzt den echten, aktuellen EAG-Kategorie-A-Satz."""
    assert _eag_pv_foerderung_pro_kwp() == 150.0
