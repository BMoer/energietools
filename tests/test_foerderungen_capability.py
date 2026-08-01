# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Förderungen-Capability (Open-Data-Förderungen, offline)."""

from __future__ import annotations

from energietools.capabilities.foerderungen.capability import FoerderungenCheckCapability
from energietools.capabilities.foerderungen.data import load_foerderungen, load_manifest
from energietools.capabilities.registry import default_registry


def test_manifest_konsistenz_count_gleich_len() -> None:
    """MANIFEST.coverage.gesamt muss exakt der Anzahl der Einträge entsprechen."""
    entries = load_foerderungen()
    manifest = load_manifest()
    assert manifest.coverage["gesamt"] == len(entries) == 45
    assert manifest.license == "MIT"
    assert manifest.disclaimer


def test_golden_case_wien_offene_foerderungen() -> None:
    """Wien: 4 offene Bund- + 2 offene, verifizierte Wien-Förderungen = 6 Treffer."""
    result = FoerderungenCheckCapability().run(bundesland="Wien")
    assert result.ok is True
    assert result.data["anzahl"] == 6
    ids = {f["id"] for f in result.data["foerderungen"]}
    assert "bund-eag-invest-pv-speicher" in ids
    assert "wien-pv-foerderpaket-2026" in ids
    # Geschlossene und unsichere Wien-Einträge dürfen NICHT auftauchen (Default-Filter).
    assert "wien-pv-standard-dach-alt" not in ids  # geschlossen
    assert "wien-sanierung-ma25" not in ids  # verlaesslichkeit=unsicher


def test_plz_leitet_bundesland_ab() -> None:
    """plz='1010' (Wien) liefert dasselbe Ergebnis wie bundesland='Wien'."""
    via_plz = FoerderungenCheckCapability().run(plz="1010")
    via_bundesland = FoerderungenCheckCapability().run(bundesland="Wien")
    assert via_plz.ok is True
    assert via_plz.data["anzahl"] == via_bundesland.data["anzahl"]
    assert via_plz.data["bundesland"] == "Wien"


def test_fail_open_unbekanntes_bundesland_ist_rejection() -> None:
    """Ein unbekanntes Bundesland ist eine strukturierte Ablehnung, kein Absturz."""
    result = FoerderungenCheckCapability().run(bundesland="Nirgendwo")
    assert result.ok is False
    assert "Nirgendwo" in result.error
    assert result.data["fehler"][0]["feld"] == "bundesland"


def test_fail_open_weder_bundesland_noch_plz() -> None:
    """Weder bundesland noch plz angegeben → klare Rückfrage, kein Absturz."""
    result = FoerderungenCheckCapability().run()
    assert result.ok is False
    assert result.data["fehler"][0]["regel"] == "erforderlich"


def test_inkl_unsicher_zeigt_zusaetzliche_eintraege() -> None:
    """inkl_unsicher=True zeigt mehr (oder gleich viele) Treffer als der Default."""
    default = FoerderungenCheckCapability().run(bundesland="Wien")
    mit_unsicher = FoerderungenCheckCapability().run(bundesland="Wien", inkl_unsicher=True)
    assert mit_unsicher.data["anzahl"] > default.data["anzahl"]
    ids = {f["id"] for f in mit_unsicher.data["foerderungen"]}
    assert "wien-sanierung-ma25" in ids


def test_nur_offen_false_zeigt_auch_geschlossene() -> None:
    """nur_offen=False zeigt auch geschlossene Förderungen (z.B. für historischen Kontext)."""
    result = FoerderungenCheckCapability().run(bundesland="Wien", nur_offen=False)
    ids = {f["id"] for f in result.data["foerderungen"]}
    assert "wien-pv-standard-dach-alt" in ids


def test_kategorien_filter() -> None:
    """kategorien filtert auf die angegebenen Förderkategorien."""
    result = FoerderungenCheckCapability().run(bundesland="Tirol", kategorien=["speicher"])
    assert result.ok is True
    assert all(f["kategorie"] == "speicher" for f in result.data["foerderungen"])
    assert result.data["anzahl"] >= 1


def test_bund_einträge_ohne_bundesland_filter() -> None:
    """Bundesförderungen (bundesland=None) erscheinen unabhängig vom gewählten Land."""
    wien_result = FoerderungenCheckCapability().run(bundesland="Wien")
    tirol_result = FoerderungenCheckCapability().run(bundesland="Tirol")
    wien = {f["id"] for f in wien_result.data["foerderungen"]}
    tirol = {f["id"] for f in tirol_result.data["foerderungen"]}
    bund_ids = {e.id for e in load_foerderungen() if e.ebene == "bund" and e.status == "offen"}
    assert bund_ids <= wien
    assert bund_ids <= tirol


def test_meta_traegt_stand() -> None:
    result = FoerderungenCheckCapability().run(bundesland="Wien")
    assert result.meta["stand"] == "2026-07-31"
    assert "foerderungen" in result.meta["quelle"]


def test_default_registry_enthaelt_foerderungen_capability() -> None:
    assert "foerderungen_check" in default_registry().names
