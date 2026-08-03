# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Energiegemeinschaften-Info-Capability (offline).

Deckt auch die BEG-Provider-Migration (``beg_advisor.py``) und die
foerderungen-Migration in ``energy_monitor.py``/``pv_sim.py`` ab (separate
Testdateien für die Capability selbst; hier nur der reine Info-Teil).
"""

from __future__ import annotations

from energietools.capabilities.energiegemeinschaften.capability import (
    EnergiegemeinschaftenInfoCapability,
)
from energietools.capabilities.energiegemeinschaften.data import (
    load_beg_providers,
    load_fakten,
    load_manifest,
    load_verzeichnis,
)
from energietools.capabilities.energiegemeinschaften.models import VerzeichnisEintrag
from energietools.capabilities.registry import default_registry


def test_manifest_konsistenz() -> None:
    manifest = load_manifest()
    assert manifest.license == "MIT"
    assert manifest.coverage["rechtsformen"] == 4
    assert manifest.coverage["beg_providers"] == len(load_beg_providers()) == 3


def test_golden_case_rechtsformen_ohne_bundesland() -> None:
    """Rechtsformen-Fakten sind bundesweit — kein bundesland nötig (fail-open)."""
    result = EnergiegemeinschaftenInfoCapability().run()
    assert result.ok is True
    rechtsformen = result.data["rechtsformen"]
    # 'beg' ist verlaesslichkeit=unsicher → per Default ausgeblendet.
    assert set(rechtsformen) == {"gea", "eeg_lokal", "eeg_regional"}
    assert rechtsformen["eeg_lokal"]["netzentgelt_reduktion"]["prozent"] == 57


def test_beg_nur_mit_inkl_unsicher() -> None:
    result = EnergiegemeinschaftenInfoCapability().run(inkl_unsicher=True)
    assert "beg" in result.data["rechtsformen"]
    assert result.data["rechtsformen"]["beg"]["verlaesslichkeit"] == "unsicher"


def test_elwg_zweistufigkeit_nicht_verwaessert() -> None:
    """Der 31.12.2026-Stolperstein (Netzentgelt-Bestimmung, NICHT 1.10.2026) bleibt sichtbar."""
    result = EnergiegemeinschaftenInfoCapability().run()
    elwg = result.data["elwg_aenderung"]
    assert elwg["teil_inkrafttreten_1"]["datum"] == "2026-10-01"
    assert elwg["teil_inkrafttreten_2"]["datum"] == "2026-12-31"
    assert "NICHT korrekt" in elwg["teil_inkrafttreten_2"]["wichtiger_hinweis"]


def test_beg_prozent_ist_null_nicht_erfunden() -> None:
    """Der künftige BEG-Netzentgelt-Prozentsatz ist unbekannt → null, kein Platzhalterwert."""
    fakten = load_fakten()
    assert fakten.rechtsformen["beg"].netzentgelt_reduktion["prozent"] is None


def test_marktstand_stichtag() -> None:
    result = EnergiegemeinschaftenInfoCapability().run()
    assert result.data["marktstand"]["stichtag"] == "2025-06-30"
    assert result.data["marktstand"]["eeg"] == 3868


def test_verzeichnis_ist_befuellt() -> None:
    """Seit 03.08.2026 befüllt — nächtlicher Refresh aus der amtlichen Landkarte.

    Prüft bewusst Invarianten statt einer Anzahl: der Snapshot wächst und schrumpft
    mit dem freiwillig befüllten amtlichen Verzeichnis, ein fixer Zählwert wäre ein
    Test, der bei jedem Refresh bricht. Der Vorgänger ``test_verzeichnis_initial_leer``
    hat den leeren Schema-Platzhalter aus B1 festgehalten und ist damit erledigt.
    """
    eintraege = load_verzeichnis()
    assert eintraege, "Verzeichnis leer — Refresh-Job oder Landkarten-Parser kaputt"
    # Die amtliche Landkarte ist BEG-only. Ein anderer Typ hieße, die Quelle hat sich
    # geändert — dann gehört auch der Unvollständigkeits-Hinweis nachgezogen.
    assert {e.typ for e in eintraege} == {"beg"}
    # Kontaktdaten sind bewusst NICHT exportiert: die Nutzungsbedingung der
    # Koordinierungsstelle untersagt Werbenutzung.
    assert not {"email", "telefon", "kontakt", "adresse"} & set(VerzeichnisEintrag.model_fields)


def test_verzeichnis_bundesland_filter() -> None:
    result = EnergiegemeinschaftenInfoCapability().run(bundesland="Wien")
    assert result.data["verzeichnis_anzahl"] == len(result.data["verzeichnis"])
    assert result.data["verzeichnis_anzahl"] > 0
    assert {e["bundesland"] for e in result.data["verzeichnis"]} == {"Wien"}
    # Der Unvollständigkeits-Hinweis bleibt Pflicht (~18 % Abdeckung, EEG fehlt ganz).
    assert result.data["verzeichnis_hinweis"]


def test_manifest_zaehlt_dieselben_verzeichnis_eintraege() -> None:
    """Domänen-MANIFEST und Datei dürfen nicht auseinanderlaufen.

    Der Refresh-Job zieht ``coverage.verzeichnis_eintraege`` mit; ohne diesen Test
    fällt es niemandem auf, wenn er es einmal nicht tut und das MANIFEST weiter
    eine veraltete Zahl neben einer befüllten Datei behauptet.
    """
    assert load_manifest().coverage["verzeichnis_eintraege"] == len(load_verzeichnis())


def test_unbekanntes_bundesland_ist_fail_open_nicht_rejection() -> None:
    """Anders als foerderungen_check: bundesland ist hier optional (kein Pflicht-Input)."""
    result = EnergiegemeinschaftenInfoCapability().run(bundesland="Nirgendwo")
    assert result.ok is True
    assert result.data["bundesland"] is None  # unbekannt → Filter ignoriert, kein Hard-Fail


def test_default_registry_enthaelt_energiegemeinschaften_capability() -> None:
    names = default_registry().names
    assert "energiegemeinschaften_info" in names
    # Bestehende SSR/SCR-Capability bleibt unangetastet, beide koexistieren.
    assert "community_metrics" in names
