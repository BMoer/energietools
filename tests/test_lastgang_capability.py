# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die ``lastgang_signals``-Capability (L.1, WP2-L Durchstich 2).

Alle Serien sind synthetisch generiert (Sinus/Konstante-Bausteine) — KEINE
echten Zählpunkte, Namen oder Adressen (MIT-Repo-Pflicht, DoD-Kriterium 13).

Struktur:
- Rechen-Kern-Unit-Tests (``signals.py``): je ein Signal isoliert erzeugt.
- PV-Guard-Tests (DoD-Kriterium 4, Ledger-F3/F14/F24): Fall-A-artiger
  Prosumer vs. Gegenprobe ohne PV.
- False-Positive-Regressionstest (Ledger-F24-Muster, anonymisiert — WS 3,16
  war real eine Pelletsheizung): E-Heizungs-Signal MUSS bei PV als Frage
  erscheinen, nie als Behauptung (``electric_heating`` darf bei geguardeten
  Fällen niemals ``"likely"`` im Result stehen).
- Referenz-Fixture (Fall B, structural gegen ``out_09.json``): reproduziert
  winter_summer_ratio≈1.29, midday_dip≈1.27, evening_peak_hour==19,
  electric_heating/pv_self_consumption == unlikely. ``night_base_w`` wird
  gegen den mit dem NEUEN 0–5h-Fenster selbst berechneten Wert geprüft
  (nicht die alten 88 W aus dem 1–4h-Fenster, Spec L.1.5/L.1.8).
- Envelope- + Registry-Smoke-Test.
- L.6-Nenner-Struktur-Test.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.lastgang.capability import LastgangSignalsCapability
from energietools.capabilities.lastgang.guards import apply_pv_guards, guard_rueckfragen
from energietools.capabilities.lastgang.signals import (
    ELECTRIC_HEAT_RATIO,
    HIGH_BASE_W,
    PV_DIP_RATIO,
    Signal,
    compute_signals,
    select_rueckfragen,
)
from energietools.capabilities.registry import default_registry

# ---------------------------------------------------------------------------
# Synthetische Serien-Generatoren (kein PII, reine Konstanten-Bausteine)
# ---------------------------------------------------------------------------


def _hour_series(
    days: list[tuple[datetime, list[float]]], interval_minutes: int = 15
) -> list[dict]:
    """Baut [{ts, kwh}, …] aus (Tag, 24-Stunden-kWh-Array)-Paaren.

    ``hourly[h]`` ist die GESAMTE kWh-Summe dieser Stunde; wird gleichmäßig
    auf die Slots verteilt (Stufenfunktion je Stunde reicht für die
    median-/summenbasierten Signale völlig aus).
    """
    slots_per_hour = 60 // interval_minutes
    records: list[dict] = []
    for day, hourly in days:
        for hour in range(24):
            slot_kwh = hourly[hour] / slots_per_hour
            for slot in range(slots_per_hour):
                ts = datetime(day.year, day.month, day.day, hour, slot * interval_minutes)
                records.append({"ts": ts.isoformat(), "kwh": round(slot_kwh, 6)})
    return records


def _consumption_tuples(records: list[dict]) -> list[tuple[datetime, float]]:
    return [(datetime.fromisoformat(r["ts"]), r["kwh"]) for r in records]


def _flat_hourly(value: float) -> list[float]:
    return [value] * 24


def _days(start: datetime, count: int) -> list[datetime]:
    return [start + timedelta(days=i) for i in range(count)]


# ---------------------------------------------------------------------------
# (a) Rechen-Kern: Winter-lastiges Profil -> electric_heating LIKELY
# ---------------------------------------------------------------------------


def test_compute_signals_winter_lastig_ergibt_electric_heating_likely() -> None:
    winter_days = [(d, _flat_hourly(0.30)) for d in _days(datetime(2025, 1, 5), 4)]
    summer_days = [(d, _flat_hourly(0.10)) for d in _days(datetime(2025, 7, 5), 4)]
    records = _hour_series(winter_days + summer_days)
    cons = _consumption_tuples(records)

    signals = compute_signals(cons)

    assert signals.winter_summer_ratio == pytest.approx(3.0, abs=0.05)
    assert signals.winter_summer_ratio >= ELECTRIC_HEAT_RATIO
    assert signals.electric_heating is Signal.LIKELY


# ---------------------------------------------------------------------------
# (b) Rechen-Kern: Mittags-Delle -> pv_self_consumption LIKELY
# ---------------------------------------------------------------------------


def test_compute_signals_mittagsdelle_ergibt_pv_signal_likely() -> None:
    hourly = _flat_hourly(0.20)
    for h in range(10, 16):
        hourly[h] = 0.05  # deutliche Mittags-Delle
    days = [(d, list(hourly)) for d in _days(datetime(2025, 6, 2), 5)]
    records = _hour_series(days)
    cons = _consumption_tuples(records)

    signals = compute_signals(cons)

    assert signals.midday_dip_ratio is not None
    assert signals.midday_dip_ratio < PV_DIP_RATIO
    assert signals.pv_self_consumption is Signal.LIKELY


def test_compute_signals_feedin_ueberschreibt_dip_ratio() -> None:
    """feedin > 0 macht pv_self_consumption LIKELY unabhängig von der Delle."""
    days = [(d, _flat_hourly(0.20)) for d in _days(datetime(2025, 6, 2), 3)]
    records = _hour_series(days)
    cons = _consumption_tuples(records)

    signals = compute_signals(cons, pv_feedin_kwh=42.0)

    assert signals.pv_self_consumption is Signal.LIKELY
    assert signals.pv_feedin_kwh == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# (c) Rechen-Kern: flaches, hohes Nacht-Profil -> high_continuous_load LIKELY
# ---------------------------------------------------------------------------


def test_compute_signals_hohe_nachtgrundlast_ergibt_dauerlaeufer_likely() -> None:
    hourly = _flat_hourly(0.02)
    for h in range(0, 5):
        hourly[h] = 0.5  # 500 Wh/h Nacht-Grundlast -> 500 W >= 300 W Schwelle
    days = [(d, list(hourly)) for d in _days(datetime(2025, 3, 3), 3)]
    records = _hour_series(days)
    cons = _consumption_tuples(records)

    signals = compute_signals(cons)

    assert signals.night_base_w >= HIGH_BASE_W
    assert signals.night_base_w == 500
    assert signals.high_continuous_load is Signal.LIKELY


def test_compute_signals_niedrige_nachtgrundlast_ergibt_dauerlaeufer_unlikely() -> None:
    days = [(d, _flat_hourly(0.02)) for d in _days(datetime(2025, 3, 3), 3)]
    records = _hour_series(days)
    cons = _consumption_tuples(records)

    signals = compute_signals(cons)

    assert signals.night_base_w < HIGH_BASE_W
    assert signals.high_continuous_load is Signal.UNLIKELY


# ---------------------------------------------------------------------------
# Guards (L.1.3): leere Serie + Granularität
# ---------------------------------------------------------------------------


def test_compute_signals_leere_serie_wirft_capability_error() -> None:
    with pytest.raises(CapabilityError, match="Leerer Lastgang"):
        compute_signals([])


def test_compute_signals_stundenwerte_wirft_capability_error() -> None:
    cons = [(datetime(2025, 1, 1, 0, 0), 1.0)]
    with pytest.raises(CapabilityError, match="Q15"):
        compute_signals(cons, interval_minutes=60)


# ---------------------------------------------------------------------------
# select_rueckfragen: Peak-Frage immer dabei, PV-Frage nennt Einspeise-Consent
# ---------------------------------------------------------------------------


def test_select_rueckfragen_enthaelt_immer_peak_frage() -> None:
    days = [(d, _flat_hourly(0.1)) for d in _days(datetime(2025, 5, 1), 2)]
    signals = compute_signals(_consumption_tuples(_hour_series(days)))

    fragen = select_rueckfragen(signals)

    assert any(f.feld == "behavior.appliance_timing" for f in fragen)


def test_select_rueckfragen_pv_frage_nennt_einspeise_consent() -> None:
    hourly = _flat_hourly(0.20)
    for h in range(10, 16):
        hourly[h] = 0.02
    days = [(d, list(hourly)) for d in _days(datetime(2025, 6, 2), 3)]
    signals = compute_signals(_consumption_tuples(_hour_series(days)))
    assert signals.pv_self_consumption is Signal.LIKELY

    fragen = select_rueckfragen(signals)
    pv_frage = next(f for f in fragen if f.feld == "asset.pv.kwp")
    assert "Einspeise-Consent" in pv_frage.frage or "Einspeise-Zählpunkt" in pv_frage.frage


# ---------------------------------------------------------------------------
# PV-Guards (L.1.4, DoD-Kriterium 4) + False-Positive-Regressionstest
# ---------------------------------------------------------------------------


def _prosumer_hohe_ws_ratio_consumption() -> list[dict]:
    """Netzbezug-Serie mit hohem Winter/Sommer-Verhältnis (~3.3), analog zum
    anonymisierten Ledger-F24-Muster (WS=3,16) — dort war die reale Heizung
    PELLETS, keine E-Heizung. Rein synthetisch, kein echter Zählpunkt."""
    winter_days = [(d, _flat_hourly(1.0)) for d in _days(datetime(2025, 1, 5), 4)]
    summer_days = [(d, _flat_hourly(0.30)) for d in _days(datetime(2025, 7, 5), 4)]
    return _hour_series(winter_days + summer_days)


def test_pv_guard_setzt_netzbezug_label_und_guarded_heating() -> None:
    records = _prosumer_hohe_ws_ratio_consumption()
    signals = compute_signals(_consumption_tuples(records))
    assert signals.electric_heating is Signal.LIKELY  # Ausgangslage: ungeguarded LIKELY

    guard = apply_pv_guards(signals, is_pv=True, grundlast_kw=0.06)

    assert guard.basis_label == "Netzbezug"
    assert guard.electric_heating_guarded is True
    assert guard.electric_heating is Signal.UNKNOWN
    assert guard.roh_ws_ratio == signals.winter_summer_ratio
    assert guard.grundlast_p15_pv_artefakt is True
    assert any("NETZBEZUG" in c for c in guard.caveats)
    assert any("F24" in c for c in guard.caveats)


def test_pv_guard_gegenprobe_ohne_pv_bleibt_unguarded() -> None:
    """Ledger-F14: reiner Verbrauchskanal (is_pv=False) — Guards greifen NICHT,
    selbst wenn dieselbe hohe WS-Ratio vorliegt und grundlast_kw übergeben wird."""
    records = _prosumer_hohe_ws_ratio_consumption()
    signals = compute_signals(_consumption_tuples(records))

    guard = apply_pv_guards(signals, is_pv=False, grundlast_kw=0.06)

    assert guard.basis_label == "Verbrauch"
    assert guard.electric_heating_guarded is False
    assert guard.electric_heating is Signal.LIKELY
    assert guard.roh_ws_ratio is None
    assert guard.grundlast_p15_pv_artefakt is False
    assert guard.caveats == []


def test_pv_guard_rueckfragen_ersetzt_heating_frage_durch_neutrale_frage() -> None:
    records = _prosumer_hohe_ws_ratio_consumption()
    signals = compute_signals(_consumption_tuples(records))
    fragen_roh = select_rueckfragen(signals)
    guard = apply_pv_guards(signals, is_pv=True, grundlast_kw=None)

    fragen = guard_rueckfragen(fragen_roh, guard=guard)

    heating_fragen = [f for f in fragen if f.feld == "asset.heating.type"]
    assert len(heating_fragen) == 1
    assert "KEIN verlässliches Zeichen" in heating_fragen[0].frage
    assert "F24" in heating_fragen[0].motiviert_durch


def test_pv_guard_capability_pellets_false_positive_regression() -> None:
    """DoD-Kriterium 4 / Ledger-F24-Muster (anonymisiert): eine PV-Prosumer-
    Serie mit hohem Winter/Sommer-Verhältnis darf im FINALEN Capability-
    Result NIEMALS electric_heating=='likely' behaupten — das wäre exakt der
    reale False-Positive (WS=3,16, echte Heizung war Pellets). Das Signal
    muss als Rückfrage erscheinen, nicht als Behauptung."""
    records = _prosumer_hohe_ws_ratio_consumption()

    result = LastgangSignalsCapability().run(
        consumption=records, is_pv=True, grundlast_kw=0.06
    )

    assert result.ok is True
    data = result.data
    assert data["electric_heating"] != "likely"
    assert data["electric_heating"] == "unknown"
    assert data["electric_heating_guarded"] is True
    assert data["basis_label"] == "Netzbezug"
    assert data["roh_ws_ratio"] is not None and data["roh_ws_ratio"] >= ELECTRIC_HEAT_RATIO
    assert data["grundlast_p15_pv_artefakt"] is True

    heating_fragen = [f for f in data["rueckfragen"] if f["feld"] == "asset.heating.type"]
    assert len(heating_fragen) == 1
    assert "?" in heating_fragen[0]["frage"]
    assert "F24" in heating_fragen[0]["motiviert_durch"]

    # Caveats müssen die drei PV-Guard-Textbausteine enthalten (a/b/c aus L.1.4)
    caveats_joined = " ".join(data["caveats"])
    assert "NETZBEZUG" in caveats_joined
    assert "F24" in caveats_joined
    assert "Grundlast(P15)" in caveats_joined


def test_pv_flag_widerspruch_bei_untypischer_mittag_nacht_signatur() -> None:
    """Mittag > Nacht ist untypisch für PV-Bezug -> Warnfeld, kein Hard-Fail."""
    hourly = _flat_hourly(0.05)  # Nacht niedrig
    for h in range(10, 16):
        hourly[h] = 0.5  # Mittag deutlich höher als Nacht (untypisch für PV)
    days = [(d, list(hourly)) for d in _days(datetime(2025, 5, 1), 3)]
    signals = compute_signals(_consumption_tuples(_hour_series(days)))
    assert signals.midday_dip_ratio is not None and signals.midday_dip_ratio > 1

    guard = apply_pv_guards(signals, is_pv=True, grundlast_kw=None)

    assert guard.pv_flag_widerspruch is True
    assert any("Konsistenz" in c for c in guard.caveats)


# ---------------------------------------------------------------------------
# Referenz-Fixture Fall B (structural, gegen out_09.json — synthetisch nachgebaut)
# ---------------------------------------------------------------------------


def _fall_b_hourly(factor: float) -> list[float]:
    """(Monat-unabhängiger) Stundenverlauf, skaliert um ``factor`` AUSSER in
    Nacht-/Mittagsstunden (die bleiben über Winter/Sommer konstant, damit
    night_base_w/midday_dip_ratio unabhängig vom Jahreszeiten-Mix sind —
    winter_summer_ratio ergibt sich rein aus dem skalierten Rest des Tages)."""
    hourly = [0.0] * 24
    for h in range(0, 5):
        hourly[h] = 0.20  # Nacht: konstant (0-4h, F9-Fenster)
    for h in range(10, 16):
        hourly[h] = 0.254  # Mittag: konstant, dip-ratio 0.254/0.05(slot) = 1.27
    for h in (5, 6, 7, 8, 9, 16, 17, 18, 20, 21, 22, 23):
        hourly[h] = 0.20 * factor
    hourly[19] = 0.50 * factor  # Abend-Peak
    return hourly


def test_referenz_fall_b_reproduziert_out_09_signatur() -> None:
    """Synthetische Nachbildung der Struktur aus ``out_09.json`` (Fall B,
    reiner Verbrauchskanal, kein PV): winter_summer_ratio≈1.29,
    midday_dip≈1.27, evening_peak_hour==19, beide Signale 'unlikely'.
    ``night_base_w`` wird NICHT gegen die alten 88 W (1-4h-Fenster) geprüft,
    sondern gegen den mit dem NEUEN 0-5h-Fenster selbst berechneten Wert
    (Spec L.1.5/L.1.8 — Referenz-Fixtures müssen regeneriert werden)."""
    winter_factor = 1.5261  # kalibriert für Tages-Ratio ≈ 1.29 (siehe Docstring-Herleitung)
    summer_factor = 1.0

    winter_days = [(d, _fall_b_hourly(winter_factor)) for d in _days(datetime(2025, 1, 6), 3)]
    summer_days = [(d, _fall_b_hourly(summer_factor)) for d in _days(datetime(2025, 7, 6), 3)]
    records = _hour_series(winter_days + summer_days)
    cons = _consumption_tuples(records)

    signals = compute_signals(cons)

    assert signals.winter_summer_ratio == pytest.approx(1.29, abs=0.03)
    assert signals.midday_dip_ratio == pytest.approx(1.27, abs=0.02)
    assert signals.evening_peak_hour == 19
    assert signals.electric_heating is Signal.UNLIKELY
    assert signals.pv_self_consumption is Signal.UNLIKELY

    # night_base_w: regenerierter Wert (0-5h), kein Vergleich gegen alte 88 W.
    # Nacht-Slot-Wert konstant 0.20/4 = 0.05 kWh -> night_base_w = 0.05*4*1000.
    assert signals.night_base_w == 200


# ---------------------------------------------------------------------------
# Envelope + Registry-Smoke
# ---------------------------------------------------------------------------


def test_capability_envelope_ok_ohne_pv() -> None:
    days = [(d, _flat_hourly(0.15)) for d in _days(datetime(2025, 4, 1), 3)]
    records = _hour_series(days)

    result = LastgangSignalsCapability().run(consumption=records)

    assert result.ok is True
    assert result.data["is_pv"] is False
    assert result.data["basis_label"] == "Verbrauch"
    assert result.data["electric_heating_guarded"] is False
    assert isinstance(result.data["rueckfragen"], list)
    assert len(result.data["rueckfragen"]) >= 1
    assert result.meta.get("quelle")


def test_capability_leere_consumption_liefert_ok_false() -> None:
    result = LastgangSignalsCapability().run(consumption=[])
    assert result.ok is False
    assert result.data is None
    assert "Leerer Lastgang" in (result.error or "")


def test_capability_registry_smoke() -> None:
    cap = default_registry().get("lastgang_signals")
    assert isinstance(cap, LastgangSignalsCapability)
    assert cap.name == "lastgang_signals"


def test_capability_result_field_paths_deckt_top_level_skalare_ab() -> None:
    cap = LastgangSignalsCapability()
    pfade = cap.result_field_paths()
    for feld in ("electric_heating", "night_base_w", "is_pv", "basis_label"):
        assert feld in pfade


# ---------------------------------------------------------------------------
# L.6 — Nenner-Disziplin: jede Verhältnis-Kennzahl trägt ihre Nenner-Definition
# ---------------------------------------------------------------------------


def test_nenner_deckt_alle_verhaeltnis_kennzahlen_ab() -> None:
    days = [(d, _flat_hourly(0.15)) for d in _days(datetime(2025, 4, 1), 3)]
    result = LastgangSignalsCapability().run(consumption=_hour_series(days))
    assert result.ok is True

    ratio_felder = [
        f
        for f in result.data
        if f.endswith("_ratio") and not f.startswith("roh_")
    ]
    assert ratio_felder, "Testserie muss mindestens ein *_ratio-Feld enthalten"
    for feld in ratio_felder:
        assert feld in result.data["nenner"], f"Nenner-Eintrag fehlt für {feld}"
        assert result.data["nenner"][feld]  # nicht-leerer Text
