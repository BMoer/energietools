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
