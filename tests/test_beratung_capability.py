# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Beratungsstellen-Capability (Open-Data-Energieberatung, offline)."""

from __future__ import annotations

from energietools.capabilities.beratung.capability import BeratungsstellenCapability
from energietools.capabilities.beratung.data import load_beratungsstellen, load_manifest
from energietools.capabilities.registry import default_registry


def test_manifest_konsistenz_count_gleich_len() -> None:
    entries = load_beratungsstellen()
    manifest = load_manifest()
    assert manifest.coverage["bundeslaender"] == len(entries) == 9
    assert manifest.license == "MIT"


def test_golden_case_wien() -> None:
    """Wien → genau 1 Beratungsstelle, Klima- und Innovationsagentur Wien."""
    result = BeratungsstellenCapability().run(bundesland="Wien")
    assert result.ok is True
    assert result.data["anzahl"] == 1
    stelle = result.data["beratungsstellen"][0]
    assert stelle["id"] == "beratung-wien"
    assert stelle["kosten"] == "kostenlos"
    assert stelle["quellen"]


def test_plz_leitet_bundesland_ab() -> None:
    via_plz = BeratungsstellenCapability().run(plz="6020")  # Innsbruck, Tirol
    assert via_plz.ok is True
    assert via_plz.data["bundesland"] == "Tirol"
    assert via_plz.data["anzahl"] == 1


def test_unsicher_standardmaessig_ausgeblendet() -> None:
    """Vorarlberg ist verlaesslichkeit='unsicher' → per Default nicht sichtbar."""
    default = BeratungsstellenCapability().run(bundesland="Vorarlberg")
    assert default.data["anzahl"] == 0

    mit_unsicher = BeratungsstellenCapability().run(bundesland="Vorarlberg", inkl_unsicher=True)
    assert mit_unsicher.data["anzahl"] == 1
    assert mit_unsicher.data["beratungsstellen"][0]["verlaesslichkeit"] == "unsicher"


def test_fail_open_unbekanntes_bundesland_ist_rejection() -> None:
    result = BeratungsstellenCapability().run(bundesland="Atlantis")
    assert result.ok is False
    assert result.data["fehler"][0]["feld"] == "bundesland"


def test_alle_9_bundeslaender_haben_je_eine_stelle() -> None:
    for bl in (
        "Wien", "Niederösterreich", "Oberösterreich", "Steiermark", "Tirol",
        "Salzburg", "Kärnten", "Burgenland",
    ):
        result = BeratungsstellenCapability().run(bundesland=bl)
        assert result.ok is True, bl
        assert result.data["anzahl"] == 1, bl


def test_default_registry_enthaelt_beratung_capability() -> None:
    assert "beratungsstellen" in default_registry().names
