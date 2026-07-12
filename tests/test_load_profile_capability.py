# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die load_profile-Capability (WP2-S).

WP2-S 1 (Rest-Check): ein load_profile-Result MIT Anomalie (``AnomalyResult.datum:
date``, ``models/load_profile.py:34`` — das einzige ``date``-Feld in der ganzen
``LoadProfileAnalysis``) muss nach der Capability-Serialisierung unverändert durch
stdlib ``json.dumps`` gehen. Das ist der B.6-/§5.3-Crash-Fall (``datetime.date`` ist
nicht JSON-serialisierbar). Läuft bewusst über die REGISTRY
(``default_registry().get("load_profile").run(...)``), nicht über einen internen
Helper — das prüft den tatsächlichen Laufzeitpfad, unabhängig davon, ob
``load_profile`` als ``FunctionCapability`` oder als dedizierte Capability-Klasse
registriert ist.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

from energietools.capabilities.registry import default_registry
from energietools.models.load_profile import (
    AnomalyResult,
    LoadProfileAnalysis,
    LoadProfileMetrics,
)


def _fixture_analysis_mit_anomalie() -> LoadProfileAnalysis:
    metrics = LoadProfileMetrics(
        mean_kw=1.0, median_kw=1.0, min_kw=0.0, max_kw=2.0, std_kw=0.5,
        grundlast_kw=0.5, spitzenlast_kw=2.0, volllaststunden=100.0,
        grundlast_anteil_pct=10.0, total_kwh=1000.0,
    )
    return LoadProfileAnalysis(
        metrics=metrics,
        anomalien=[
            AnomalyResult(
                datum=date(2026, 1, 15),
                wochentag="Donnerstag",
                typ="magnitude",
                cluster_id=0,
                abweichung_kwh=12.3,
                spitzen_abweichung_kw=4.5,
            )
        ],
    )


def test_load_profile_capability_result_mit_anomalie_ist_json_dumpbar():
    """WP2-S 1 Rest-Check: date in einer Anomalie darf json.dumps nicht crashen lassen."""
    analysis = _fixture_analysis_mit_anomalie()
    with patch(
        "energietools.tools.load_profile.analyze_load_profile",
        return_value=analysis,
    ):
        result = default_registry().get("load_profile").run(
            consumption_data=[{"timestamp": "2026-01-15T00:00:00", "kwh": 1.0}],
        )

    assert result.ok is True
    dumped = json.dumps(result.data)  # darf NICHT TypeError werfen (date!)
    assert '"datum": "2026-01-15"' in dumped
    assert result.data["anomalien"][0]["datum"] == "2026-01-15"


# =============================================================================
# WP2-S 2 — ok/error-Semantik: in-band analyse_erfolgreich=False -> CapabilityError
# =============================================================================


def test_load_profile_ohne_daten_ist_ok_false():
    """Kein consumption_data/csv_text: die Capability muss ok=False liefern, nicht
    versteckt in data.analyse_erfolgreich=False (WP2-S 2 — vorher: ok blieb True)."""
    result = default_registry().get("load_profile").run()
    assert result.ok is False
    assert "Keine Daten" in (result.error or "")


def test_load_profile_zu_wenig_datenpunkte_ist_ok_false():
    """< 96 Datenpunkte (< 1 Tag Q15): ok=False mit sprechendem Fehlertext."""
    result = default_registry().get("load_profile").run(
        consumption_data=[{"timestamp": "2026-01-15T00:00:00", "kwh": 1.0}],
    )
    assert result.ok is False
    assert "wenig" in (result.error or "").lower()


def test_load_profile_erfolgreiche_analyse_ist_ok_true():
    """Gegenprobe: eine erfolgreiche Analyse bleibt ok=True (kein Overblocking)."""
    analysis = _fixture_analysis_mit_anomalie()
    with patch(
        "energietools.tools.load_profile.analyze_load_profile",
        return_value=analysis,
    ):
        result = default_registry().get("load_profile").run(
            consumption_data=[{"timestamp": "2026-01-15T00:00:00", "kwh": 1.0}],
        )
    assert result.ok is True
    assert result.error is None


# =============================================================================
# WP2-S 3 — _meta-Befuellung (stand/quelle/snapshot_version)
# =============================================================================


def test_load_profile_meta_enthaelt_quelle_und_snapshot_version():
    """_meta liefert quelle + snapshot_version unabhaengig vom Erfolg des Laufs."""
    result = default_registry().get("load_profile").run(
        consumption_data=[{"timestamp": "2026-01-15T00:00:00", "kwh": 1.0}],
    )
    assert "quelle" in result.meta
    assert "snapshot_version" in result.meta
    assert result.meta["snapshot_version"]  # nicht leer


def test_load_profile_meta_stand_ist_zeitspanne_der_consumption_data():
    """stand = min..max Zeitstempel der uebergebenen consumption_data (WP2-S 3)."""
    from energietools.capabilities.load_profile.capability import LoadProfileCapability

    meta = LoadProfileCapability()._meta(
        consumption_data=[
            {"timestamp": "2026-01-01T00:00:00", "kwh": 1.0},
            {"timestamp": "2026-01-15T12:00:00", "kwh": 1.0},
            {"timestamp": "2026-01-08T06:00:00", "kwh": 1.0},
        ],
    )
    assert meta["stand"] == "2026-01-01T00:00:00…2026-01-15T12:00:00"


def test_load_profile_meta_ohne_consumption_data_hat_kein_stand():
    """csv_text-Pfad (bzw. keine strukturierten Daten): kein stand, aber kein Crash."""
    from energietools.capabilities.load_profile.capability import LoadProfileCapability

    meta = LoadProfileCapability()._meta(csv_text="irrelevant")
    assert "stand" not in meta
    assert "quelle" in meta
    assert "snapshot_version" in meta
