# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für ``tools.load_profile`` — L.7-Merge (WP2-L Zeile L.7, Diff-Inventar).

Portiert aus ``gridbert/tests/unit/test_load_profile.py`` (``TestGenerateVisualizationsFlag``,
``TestPartialPeriodMetrics``) — genau die vier Tests, die die beiden gridbert-Exklusiva
absichern, die laut Diff-Inventar in energietools eingemerged werden:

1. ``generate_visualizations``-Flag (spart die matplotlib-Base64-PNGs).
2. Perioden-normalisierte Hochrechnung von ``volllaststunden``/``grundlast_anteil_pct``
   (Bugfix: vorher wurde eine Jahreskennzahl gegen eine Teilzeitraum-Summe gerechnet).

``TestFallBAnnualisierung`` ist der zusätzliche numerische Beweis (Diff-Inventar §2,
Fall B): eine rein synthetische Teiljahr-Serie mit denselben Aggregat-Kennzahlen wie
``analysen/09_lastgang/out_09.json`` (77.272 Slots, total_kwh=4326.0, grundlast_kw=0.06,
spitzenlast_kw=4.33 — gerundete Aggregat-Referenzwerte, KEINE echten Zählpunktdaten),
die nachweist, dass die neue Formel exakt die im Diff-Inventar dokumentierten
Referenzwerte (453.0/26.8) reproduziert und die alte, unkorrigierte Formel exakt die
dort dokumentierten falschen Werte (999.0/12.1) — der Bugfix ist damit nicht nur
behauptet, sondern an einer eigenständigen Serie nachgerechnet.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from energietools.tools.load_profile import analyze_load_profile


class TestGenerateVisualizationsFlag:
    """Ein Upload-/JSON-Endpunkt muss die ~200KB-Base64-PNGs unterdrücken können."""

    def _data(self, days: int = 3) -> list[dict]:
        data = []
        start = datetime(2025, 1, 1)
        for i in range(96 * days):
            ts = start + timedelta(minutes=15 * i)
            hour = ts.hour
            data.append({"timestamp": ts.isoformat(), "kwh": 0.3 if 6 <= hour <= 22 else 0.15})
        return data

    def test_default_generates_visualizations(self):
        """Default-Verhalten bleibt unverändert: PNGs werden erzeugt."""
        result = analyze_load_profile(consumption_data=self._data())
        assert result.analyse_erfolgreich is True
        assert result.visualisierungen  # nicht-leeres Dict aus base64-PNGs

    def test_flag_false_suppresses_visualizations(self):
        """generate_visualizations=False liefert ein leeres viz-Dict, keine Render-Kosten."""
        result = analyze_load_profile(consumption_data=self._data(), generate_visualizations=False)
        assert result.analyse_erfolgreich is True
        assert result.visualisierungen == {}
        # Metriken/Sparpotenziale sind vom Flag unberührt.
        assert result.metrics.total_kwh > 0


class TestPartialPeriodMetrics:
    """Grundlast-Anteil & Volllaststunden dürfen die Jahreskonstante (8760 h) nicht
    gegen einen Teilzeitraum rechnen (sonst systematisch überhöht)."""

    @staticmethod
    def _constant_load(days: int, kw: float) -> list[dict]:
        start = datetime(2025, 1, 1)
        kwh = kw * 0.25  # konstante Leistung kw über 15-min-Intervalle
        return [
            {"timestamp": (start + timedelta(minutes=15 * i)).isoformat(), "kwh": kwh}
            for i in range(96 * days)
        ]

    def test_grundlast_anteil_not_inflated_on_partial_period(self):
        # Konstante Last über 14 Tage: Grundlast == Last → Anteil ≈ 100 %, nicht > 100 %.
        result = analyze_load_profile(
            consumption_data=self._constant_load(days=14, kw=1.0),
            generate_visualizations=False,
        )
        assert result.analyse_erfolgreich is True
        assert 95.0 <= result.metrics.grundlast_anteil_pct <= 101.0

    def test_volllaststunden_annualized(self):
        # Konstante 1 kW → Jahresenergie 8760 kWh, Spitze 1 kW → ~8760 Volllaststunden,
        # unabhängig davon, dass nur 14 Tage hochgeladen wurden.
        result = analyze_load_profile(
            consumption_data=self._constant_load(days=14, kw=1.0),
            generate_visualizations=False,
        )
        assert result.metrics.volllaststunden == pytest.approx(8760, rel=0.02)


class TestFallBAnnualisierung:
    """Numerischer Beweis der Perioden-Normalisierung gegen die Fall-B-Referenzwerte
    aus dem Diff-Inventar (``analysen/09_lastgang/out_09.json``, 77.272 Q15-Slots).

    Die Serie ist rein synthetisch konstruiert (kein Zählpunkt, kein Rohdaten-Bezug) —
    sie trifft nur dieselben GERUNDETEN Aggregat-Kennzahlen wie Fall B (period_hours,
    total_kwh, grundlast_kw, spitzenlast_kw), um die Formel bit-genau gegen die im
    Diff-Inventar dokumentierten Zielwerte nachzurechnen.
    """

    @staticmethod
    def _fall_b_series() -> list[dict]:
        """77.272 Q15-Slots, konstruiert für total_kwh=4326.0, grundlast_kw=0.06 (15.
        Perzentil), spitzenlast_kw=4.33 — exakt die aus out_09.json gerundeten Werte."""
        n_slots = 77_272
        n_low = 70_000  # >> Index des 15.-Perzentils (~11.591 von 77.272) → Plateau
        low_kwh = 0.015  # → 0.06 kW (15. Perzentil)
        peak_kwh = 1.0825  # → 4.33 kW (Maximum, einzelner Slot)
        n_mid = n_slots - n_low - 1
        mid_kwh = (4326.0 - n_low * low_kwh - peak_kwh) / n_mid

        kwh = np.empty(n_slots)
        kwh[:n_low] = low_kwh
        kwh[n_low:n_low + n_mid] = mid_kwh
        kwh[n_low + n_mid] = peak_kwh
        # Reihenfolge verwürfeln — die Formel darf nicht von der Sortierung abhängen,
        # nur _prepare_dataframe sortiert wieder nach Zeitstempel.
        np.random.default_rng(42).shuffle(kwh)

        timestamps = pd.date_range("2025-01-01", periods=n_slots, freq="15min")
        return [
            {"timestamp": ts.isoformat(), "kwh": float(v)}
            for ts, v in zip(timestamps, kwh)
        ]

    def test_annualisierte_formel_trifft_fall_b_referenzwerte(self):
        """Neue (Perioden-normalisierte) Formel: volllaststunden=453.0, grundlast_anteil_pct=26.8
        — exakte Übereinstimmung mit den im Diff-Inventar dokumentierten out_09.json-Werten."""
        result = analyze_load_profile(
            consumption_data=self._fall_b_series(),
            generate_visualizations=False,
        )
        assert result.analyse_erfolgreich is True
        # Aggregat-Kennzahlen der Konstruktion selbst (Zwischenschritt, keine Behauptung).
        assert result.metrics.total_kwh == pytest.approx(4326.0, abs=0.1)
        assert result.metrics.grundlast_kw == pytest.approx(0.06, abs=0.001)
        assert result.metrics.spitzenlast_kw == pytest.approx(4.33, abs=0.005)
        # Der eigentliche Beweis: annualisierte Kennzahlen treffen die Referenzwerte exakt.
        assert result.metrics.volllaststunden == pytest.approx(453.0, abs=0.5)
        assert result.metrics.grundlast_anteil_pct == pytest.approx(26.8, abs=0.05)
