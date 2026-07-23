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

from datetime import date, datetime, timedelta

import pytest

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.lastgang.capability import (
    LastgangSignalsCapability,
    LoadTrendCapability,
    SpotBacktestCapability,
)
from energietools.capabilities.lastgang.guards import (
    CAVEAT_PV_WIDERSPRUCH,
    CAVEAT_PV_WIDERSPRUCH_AUS_FAKT,
    apply_pv_guards,
    guard_rueckfragen,
)
from energietools.capabilities.lastgang.signals import (
    ELECTRIC_HEAT_RATIO,
    HIGH_BASE_W,
    PV_DIP_RATIO,
    Signal,
    compute_signals,
    select_rueckfragen,
)
from energietools.capabilities.lastgang.spot import (
    DEFAULT_SPOT_AUFSCHLAG_CT,
    GRUND_KEIN_FIXPREIS,
    GRUND_KEIN_SPOT,
    GRUND_KEIN_VERBRAUCH,
    GRUND_TARIF_ERSPARNIS_LEER,
    compute_spot_backtest,
    extract_tarif_ersparnis,
)
from energietools.capabilities.lastgang.trend import (
    FULL_YEAR_DAY_THRESHOLD,
    MIN_TREND_FENSTER_TAGE,
    aligned_window_yoy,
    compute_load_trend,
    per_year,
)
from energietools.capabilities.registry import default_registry
from energietools.capabilities.tariff_compare.capability import TariffCompareCapability

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


def test_pv_widerspruch_caveat_neutral_wenn_pv_kenntnis_nur_aus_fakt_stammt() -> None:
    """E2: stammt die PV-Kenntnis AUSSCHLIESSLICH aus einem gespeicherten
    Fakt (kein Flag, keine Einspeise-Summe), ist 'PV-Flag ggf. falsch
    gesetzt' irreführend — es gibt kein Flag, das falsch gesetzt sein
    könnte. Der neutrale Text ersetzt ihn, bestehende Flag-Semantik
    (Default False) bleibt unverändert."""
    hourly = _flat_hourly(0.05)
    for h in range(10, 16):
        hourly[h] = 0.5
    days = [(d, list(hourly)) for d in _days(datetime(2025, 5, 1), 3)]
    signals = compute_signals(_consumption_tuples(_hour_series(days)))
    assert signals.midday_dip_ratio is not None and signals.midday_dip_ratio > 1

    guard = apply_pv_guards(
        signals, is_pv=True, grundlast_kw=None, pv_kenntnis_nur_aus_fakt=True
    )

    assert guard.pv_flag_widerspruch is True
    assert CAVEAT_PV_WIDERSPRUCH_AUS_FAKT in guard.caveats
    assert CAVEAT_PV_WIDERSPRUCH not in guard.caveats


def test_capability_pv_widerspruch_caveat_neutral_bei_pv_fakt_ohne_flag() -> None:
    """Wie oben, aber über die volle Capability: profil_fakten liefert
    asset.pv.kwp OHNE is_pv-Flag/pv_feedin_kwh — die PV-Kenntnis stammt
    ausschließlich aus dem Fakt, der Caveat muss neutral sein."""
    hourly = _flat_hourly(0.05)
    for h in range(10, 16):
        hourly[h] = 0.5
    days = [(d, list(hourly)) for d in _days(datetime(2025, 5, 1), 3)]
    records = _hour_series(days)

    result = LastgangSignalsCapability().run(
        consumption=records, profil_fakten={"asset.pv.kwp": 5.0}
    )

    assert result.ok is True
    data = result.data
    assert data["is_pv"] is True
    assert data["pv_flag_widerspruch"] is True
    assert CAVEAT_PV_WIDERSPRUCH_AUS_FAKT in data["caveats"]
    assert CAVEAT_PV_WIDERSPRUCH not in data["caveats"]


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


# ---------------------------------------------------------------------------
# Fakt vor Heuristik (profil_fakten) — Kein-Fakt-Regression + Referenzfall
# (WP „Fakt-vor-Heuristik", Bauplan Achse 1 §1.3/§Referenz-JSON)
# ---------------------------------------------------------------------------


def test_capability_ohne_profil_fakten_identisch_zu_bisher() -> None:
    """Kein-Fakt-Regression: bestehende Felder bleiben WERTGLEICH zur
    Pellets-False-Positive-Regression oben, neue Felder liefern neutrale
    Defaults — Fakt-vor-Heuristik darf das Alt-Verhalten ohne profil_fakten
    nicht verändern."""
    records = _prosumer_hohe_ws_ratio_consumption()

    result = LastgangSignalsCapability().run(
        consumption=records, is_pv=True, grundlast_kw=0.06
    )

    assert result.ok is True
    data = result.data

    # E3: ALLE 3 Signal-Endfelder unabhängig gegen compute_signals/
    # apply_pv_guards neu berechnet (vorher nur electric_heating geprüft) —
    # pv_self_consumption/high_continuous_load lässt der PV-Guard unangefasst
    # (s. reconcile._signal_roh_werte-Doku), electric_heating kommt aus dem Guard.
    erwartete_signals = compute_signals(_consumption_tuples(records))
    erwarteter_guard = apply_pv_guards(erwartete_signals, is_pv=True, grundlast_kw=0.06)
    assert data["electric_heating"] == erwarteter_guard.electric_heating.value
    assert data["pv_self_consumption"] == erwartete_signals.pv_self_consumption.value
    assert data["high_continuous_load"] == erwartete_signals.high_continuous_load.value

    # Alt-Verhalten unverändert (identisch zur Pellets-Regression oben).
    assert data["electric_heating"] == "unknown"
    assert data["electric_heating_guarded"] is True
    assert data["basis_label"] == "Netzbezug"
    assert data["roh_ws_ratio"] is not None

    # Neue Felder: neutrale Defaults ohne profil_fakten.
    assert data["electric_heating_quelle"] == "heuristik"
    assert data["electric_heating_roh"] is None
    assert data["pv_self_consumption_quelle"] == "heuristik"
    assert data["pv_self_consumption_roh"] is None
    assert data["high_continuous_load_quelle"] == "heuristik"
    assert data["high_continuous_load_roh"] is None

    abgleich = data["profil_abgleich"]
    assert abgleich["verfuegbar"] is False
    assert abgleich["anzahl_widersprueche"] == 0
    assert abgleich["heizung"]["status"] == "kein_fakt"
    assert abgleich["heizung"]["wert"] is None
    assert abgleich["unterdrueckte_rueckfragen"] == []


def test_capability_fakt_gas_liefert_profil_antwort_im_envelope() -> None:
    """Referenzfall (Bauplan §Referenz-JSON): Fakt gas + WS-Ratio 2.7 — die
    Antwort folgt dem gespeicherten Fakt, nicht der Lastgang-Heuristik."""
    winter_days = [(d, _flat_hourly(0.27)) for d in _days(datetime(2025, 1, 5), 4)]
    summer_days = [(d, _flat_hourly(0.10)) for d in _days(datetime(2025, 7, 5), 4)]
    records = _hour_series(winter_days + summer_days)

    result = LastgangSignalsCapability().run(
        consumption=records, profil_fakten={"asset.heating.type": "gas"},
    )

    assert result.ok is True
    data = result.data
    assert data["winter_summer_ratio"] == pytest.approx(2.7, abs=0.01)
    assert data["electric_heating"] == "unlikely"
    assert data["electric_heating_quelle"] == "profil"
    assert data["electric_heating_roh"] == "likely"

    abgleich = data["profil_abgleich"]
    assert abgleich["verfuegbar"] is True
    assert abgleich["anzahl_widersprueche"] == 1
    heizung = abgleich["heizung"]
    assert heizung["wert"] == "gas"
    assert heizung["quelle"] == "profil"
    assert heizung["status"] == "widerspruch"
    assert heizung["heuristik_schaetzung"] == "vermutlich_elektrisch"
    assert heizung["kennzahl"] == "winter_summer_ratio=2.7 (Schwelle 2.5)"
    assert abgleich["unterdrueckte_rueckfragen"] == ["asset.heating.type"]

    heizungs_fragen = [f for f in data["rueckfragen"] if f["feld"] == "asset.heating.type"]
    assert heizungs_fragen == []  # Rückfrage entfällt, da Fakt vorhanden

    caveats_joined = " ".join(data["caveats"])
    assert "gespeicherter Profil-Fakt" in caveats_joined
    assert data["rechenweg"]["profil_abgleich"]["praezedenz"] == "fakt_vor_heuristik"
    assert data["rechenweg"]["profil_abgleich"]["heizung"]["status"] == "widerspruch"


def test_capability_pv_fakt_aktiviert_netzbezug_guards() -> None:
    """asset.pv.kwp ohne explizites is_pv-Flag aktiviert trotzdem die
    PV-Guards (Netzbezug-Label) — der Fakt IST der PV-Hinweis."""
    days = [(d, _flat_hourly(0.15)) for d in _days(datetime(2025, 4, 1), 3)]
    records = _hour_series(days)

    result = LastgangSignalsCapability().run(
        consumption=records, profil_fakten={"asset.pv.kwp": 4.5},
    )

    assert result.ok is True
    assert result.data["is_pv"] is True
    assert result.data["basis_label"] == "Netzbezug"
    assert result.data["profil_abgleich"]["pv"]["wert"] == 4.5
    assert result.data["profil_abgleich"]["pv"]["quelle"] == "profil"


def test_capability_kaputte_profil_fakten_liefert_ok_false() -> None:
    days = [(d, _flat_hourly(0.15)) for d in _days(datetime(2025, 4, 1), 3)]
    records = _hour_series(days)

    result = LastgangSignalsCapability().run(
        consumption=records, profil_fakten={"asset.heating.type": "kohle"},
    )

    assert result.ok is False
    assert result.data is None
    assert result.error


def test_result_field_paths_deckt_profil_abgleich_und_quelle_felder() -> None:
    pfade = LastgangSignalsCapability().result_field_paths()
    for feld in (
        "electric_heating_quelle",
        "electric_heating_roh",
        "pv_self_consumption_quelle",
        "pv_self_consumption_roh",
        "high_continuous_load_quelle",
        "high_continuous_load_roh",
        "profil_abgleich.verfuegbar",
        "profil_abgleich.anzahl_widersprueche",
        "profil_abgleich.heizung.wert",
        "profil_abgleich.heizung.quelle",
        "profil_abgleich.heizung.status",
        "profil_abgleich.pv.wert",
        "profil_abgleich.pv.quelle",
        "profil_abgleich.pv.status",
        "profil_abgleich.dauerlast.wert",
        "profil_abgleich.dauerlast.quelle",
        "profil_abgleich.dauerlast.status",
    ):
        assert feld in pfade, feld


# ---------------------------------------------------------------------------
# L.2 — load_trend: Mehrjahres-Trend mit Coverage-Guard (YoY)
#
# Alle Serien unten sind bewusst auf TAGES-Granularität vereinfacht (ein
# Reading pro Kalendertag, fixe Uhrzeit) statt echter Q15 — das hält die
# Tests schnell und die Zahlen exakt nachrechenbar; die deckungsgleiche
# (Monat,Tag,Std,Min)-Fenster-Logik ist granularitätsunabhängig (sie summiert
# nur über Slot-Schlüssel, die in beiden Jahren vorkommen — bei konstantem
# Tageswert liefert 1 Slot/Tag denselben delta_pct wie 96 Slots/Tag).
# ``gemeinsame_tage`` im Result nimmt Q15 (96 Slots/Tag) an und ist bei
# dieser vereinfachten Granularität daher nicht die reale Tageszahl — nur
# ``delta_pct``/``gemeinsame_slots`` werden geprüft. KEINE echten
# Zählpunkte/Namen (MIT-Repo-Pflicht, DoD-Kriterium 13).
# ---------------------------------------------------------------------------


def _daily_records(
    start: date, end: date, kwh_je_tag: float, *, hour: int = 12, minute: int = 0
) -> list[dict]:
    """Ein {ts, kwh}-Reading pro Kalendertag in [start, end] (inklusive)."""
    out: list[dict] = []
    tag = start
    while tag <= end:
        ts = datetime(tag.year, tag.month, tag.day, hour, minute)
        out.append({"ts": ts.isoformat(), "kwh": round(kwh_je_tag, 6)})
        tag += timedelta(days=1)
    return out


def _daily_tuples(records: list[dict]) -> list[tuple[datetime, float]]:
    return [(datetime.fromisoformat(r["ts"]), r["kwh"]) for r in records]


# --- Rechen-Kern: per_year (F11 — Tage != Slots) --------------------------


def test_per_year_full_year_threshold_ist_360_tage() -> None:
    assert FULL_YEAR_DAY_THRESHOLD == 360


def test_per_year_klassifiziert_volljahr_und_teiljahr() -> None:
    teil = _daily_records(date(2024, 4, 15), date(2024, 12, 31), 5.0)
    voll = _daily_records(date(2025, 1, 1), date(2025, 12, 31), 5.0)

    jahre = per_year(_daily_tuples(teil + voll))
    by_jahr = {j.jahr: j for j in jahre}

    assert by_jahr[2024].days == 261
    assert by_jahr[2024].full_year is False
    assert by_jahr[2024].von == "2024-04-15"
    assert by_jahr[2024].bis == "2024-12-31"
    assert by_jahr[2025].days == 365
    assert by_jahr[2025].full_year is True


def test_per_year_zaehlt_kalendertage_nicht_slots() -> None:
    """F11: mehrere Slots am selben Tag zählen als EIN Tag, nicht als N."""
    records = [
        {"ts": datetime(2025, 5, 1, 0, 0).isoformat(), "kwh": 1.0},
        {"ts": datetime(2025, 5, 1, 6, 0).isoformat(), "kwh": 1.0},
        {"ts": datetime(2025, 5, 1, 12, 0).isoformat(), "kwh": 1.0},
        {"ts": datetime(2025, 5, 1, 18, 0).isoformat(), "kwh": 1.0},
    ]

    jahre = per_year(_daily_tuples(records))

    assert jahre[0].slots == 4
    assert jahre[0].days == 1


# --- Rechen-Kern: aligned_window_yoy (deckungsgleiche Slots) --------------


def test_aligned_window_yoy_nur_deckungsgleiche_slots() -> None:
    # Beide Jahre bewusst NICHT-Schaltjahre (2022/2023), damit len(a) exakt die
    # gemeinsame Slot-Zahl ist -- der Schalttag-Fall (29.02.) wird separat in
    # der Fall-B-Referenz (2024->2025) mitgeprüft.
    a = _daily_records(date(2022, 1, 1), date(2022, 6, 30), 2.0)
    b = _daily_records(date(2023, 1, 1), date(2023, 12, 31), 2.2)

    w = aligned_window_yoy(_daily_tuples(a + b), 2022, 2023)

    assert w is not None
    assert w.gemeinsame_slots == len(a)
    assert w.delta_pct == pytest.approx(10.0, abs=0.05)


def test_aligned_window_yoy_disjunkte_monate_liefert_none() -> None:
    a = _daily_records(date(2024, 1, 1), date(2024, 3, 1), 2.0)
    b = _daily_records(date(2025, 4, 1), date(2025, 12, 31), 2.0)

    w = aligned_window_yoy(_daily_tuples(a + b), 2024, 2025)

    assert w is None


# --- Coverage-Guard: Kalender-YoY nur bei >=2 vollen Jahren ---------------


def test_calendar_yoy_bei_zwei_vollen_jahren() -> None:
    a = _daily_records(date(2030, 1, 1), date(2030, 12, 31), 4.0)
    b = _daily_records(date(2031, 1, 1), date(2031, 12, 31), 4.4)

    result = compute_load_trend(_daily_tuples(a + b))

    assert result.calendar_yoy is not None
    assert result.calendar_yoy.von_jahr == 2030
    assert result.calendar_yoy.bis_jahr == 2031
    assert result.calendar_yoy.delta_pct == pytest.approx(10.0, abs=0.05)
    assert result.calendar_yoy_verweigert_grund is None


def test_trend_pct_faellt_auf_calendar_yoy_zurueck_wenn_fenster_leer() -> None:
    """Zwei volle Jahre OHNE gemeinsame (Monat,Tag,Std,Min)-Slots (hier: fixe,
    unterschiedliche Uhrzeit je Jahr) -> window_yoy bleibt leer, aber
    calendar_yoy existiert -> trend_pct_pro_jahr faellt auf calendar_yoy
    zurueck (Fallback-Zweig in compute_load_trend)."""
    a = _daily_records(date(2040, 1, 1), date(2040, 12, 31), 4.0, hour=12)
    b = _daily_records(date(2041, 1, 1), date(2041, 12, 31), 4.4, hour=13)

    result = compute_load_trend(_daily_tuples(a + b))

    assert result.calendar_yoy is not None
    assert result.window_yoy == []
    assert result.trend_pct_pro_jahr == pytest.approx(result.calendar_yoy.delta_pct, abs=0.01)
    assert result.trend_aussage is not None


def test_calendar_yoy_verweigert_bei_nur_einem_vollen_jahr() -> None:
    voll = _daily_records(date(2030, 1, 1), date(2030, 12, 31), 4.0)
    teil = _daily_records(date(2031, 1, 1), date(2031, 6, 30), 4.0)

    result = compute_load_trend(_daily_tuples(voll + teil))

    assert result.calendar_yoy is None
    assert result.calendar_yoy_verweigert_grund is not None
    assert "1 volle" in result.calendar_yoy_verweigert_grund
    assert result.window_yoy != []


def test_trend_aussage_leer_bei_nur_einem_jahr_ohne_paar() -> None:
    nur_ein_jahr = _daily_records(date(2030, 1, 1), date(2030, 3, 1), 3.0)

    result = compute_load_trend(_daily_tuples(nur_ein_jahr))

    assert result.window_yoy == []
    assert result.calendar_yoy is None
    assert result.trend_aussage is None
    assert result.trend_pct_pro_jahr is None


# --- Mindest-Deckungs-Guard je Fenster (Korrektheits-Fix 2026-07-20) ------
#
# Echter Fehlbefund (Bens Serie, docs/ABNAHME-B2C.md C3): ein Fenster mit
# 4 Slots/0,0 gemeinsamen Tagen (ein Grenz-Slot am Jahreswechsel) und
# delta_pct +33,1 % ging gleichberechtigt mit einem echten Fenster
# (192,9 Tage, +9,7 %) in den Median ein -> "Verbrauch steigt ~21 %/Jahr"
# statt ehrlicher +9,7 %. Fix: Fenster unter MIN_TREND_FENSTER_TAGE
# gemeinsamen Kalendertagen bekommen in_trend=False + grund und fliessen
# nicht mehr in trend_pct_pro_jahr/trend_aussage ein (bleiben aber in
# window_yoy sichtbar). ``gemeinsame_tage`` zaehlt seit demselben Fix echte,
# granularitaetsunabhaengige Kalendertage statt gemeinsame_slots/96 -- die
# alte Q15-Schaetzung haette bei den Tages-Testserien hier (1 Slot/Tag) jedes
# Fenster faelschlich als "zu duenn" geflaggt (261 Tage waeren als 2,7
# "Tage" gezaehlt worden).
# ---------------------------------------------------------------------------


def test_load_trend_mini_fenster_unter_mindestdeckung_wird_ausgeschlossen() -> None:
    """(a) Repro des echten Falls: ein Mini-Fenster mit nur 1 gemeinsamen
    Kalendertag (Jahreswechsel-Grenzwert, +33,1 %) neben einem vollen Fenster
    (365 gemeinsame Tage, +9,7 %). trend_pct_pro_jahr kommt NUR vom vollen
    Fenster; das Mini-Fenster bleibt sichtbar, aber in_trend=False."""
    mini_2023 = [{"ts": datetime(2023, 12, 31, 12, 0).isoformat(), "kwh": 3.756}]
    voll_2024 = _daily_records(date(2024, 1, 1), date(2024, 12, 31), 5.0)
    voll_2025 = _daily_records(date(2025, 1, 1), date(2025, 12, 31), 5.0 * 1.097)

    result = compute_load_trend(_daily_tuples(mini_2023 + voll_2024 + voll_2025))

    assert len(result.window_yoy) == 2
    fenster_mini, fenster_voll = result.window_yoy

    assert (fenster_mini.von_jahr, fenster_mini.bis_jahr) == (2023, 2024)
    assert fenster_mini.gemeinsame_tage < MIN_TREND_FENSTER_TAGE
    assert fenster_mini.in_trend is False
    assert fenster_mini.grund is not None
    assert fenster_mini.delta_pct == pytest.approx(33.1, abs=0.5)

    assert (fenster_voll.von_jahr, fenster_voll.bis_jahr) == (2024, 2025)
    assert fenster_voll.gemeinsame_tage >= MIN_TREND_FENSTER_TAGE
    assert fenster_voll.in_trend is True
    assert fenster_voll.grund is None
    assert fenster_voll.delta_pct == pytest.approx(9.7, abs=0.05)

    # Kernaussage des Fixes: NUR das volle Fenster zaehlt, nicht der Median
    # aus beiden (der wuerde faelschlich ~21 statt 9,7 ergeben).
    assert result.trend_pct_pro_jahr == pytest.approx(9.7, abs=0.05)
    assert result.trend_aussage is not None
    assert "steigt" in result.trend_aussage
    assert "~10" in result.trend_aussage


def test_load_trend_alle_fenster_unter_schwelle_liefert_ehrlichen_grund_ohne_wert() -> None:
    """(b) Alle Fenster unter der Mindest-Deckung (und keine Kalender-YoY
    moeglich, da kein volles Jahr) -> trend_pct_pro_jahr bleibt None,
    trend_aussage verweigert ehrlich statt eines verzerrten Werts."""
    a = _daily_records(date(2030, 12, 1), date(2030, 12, 5), 4.0)
    b = _daily_records(date(2031, 12, 1), date(2031, 12, 5), 6.0)

    result = compute_load_trend(_daily_tuples(a + b))

    assert len(result.window_yoy) == 1
    fenster = result.window_yoy[0]
    assert fenster.gemeinsame_tage < MIN_TREND_FENSTER_TAGE
    assert fenster.in_trend is False
    assert fenster.grund is not None

    assert result.calendar_yoy is None
    assert result.trend_pct_pro_jahr is None
    assert result.trend_aussage is not None
    assert "Zu wenig Deckung" in result.trend_aussage


def test_load_trend_gemeinsame_tage_ist_granularitaetsunabhaengig() -> None:
    """gemeinsame_tage zaehlt echte Kalendertage, nicht gemeinsame_slots/96 --
    bei Tages-Granularitaet (1 Slot/Tag) muss die Zahl der echten Ueberlappung
    entsprechen (hier exakt 10 Tage), nicht 10/96 ~ 0,1."""
    a = _daily_records(date(2050, 1, 1), date(2050, 1, 10), 2.0)
    b = _daily_records(date(2051, 1, 1), date(2051, 1, 10), 2.0)

    w = aligned_window_yoy(_daily_tuples(a + b), 2050, 2051)

    assert w is not None
    assert w.gemeinsame_slots == 10
    assert w.gemeinsame_tage == pytest.approx(10.0, abs=0.01)


# --- Referenz Fall B (DoD-Kriterium 5): reproduziert +9,8 %/+9,7 % --------
# (results_09.md:36-37, CASE_09.md:31-33, out_09.json — nur Aggregate/
# Kalendergrenzen als Referenz, keine Rohserie, s. Spec §L.2.5/§6.)


def _fall_b_trend_records() -> list[dict]:
    """Synthetische Nachbildung der Mehrjahres-STRUKTUR aus ``out_09.json``
    (Case 09): 2024 Teiljahr ab 15.04. (261 Tage), 2025 Volljahr (365 Tage),
    2026 Teiljahr bis 28.06. (179 Tage) — dieselben Kalendergrenzen wie im
    Referenzfall (reine Datums-Struktur, kein Rohdaten-Bezug). Flache
    Tages-kWh je Jahr, kalibriert auf +9,8 %/+9,7 % Fenster-YoY (Spec L.2.5).
    Wert-Niveau (5 kWh/Tag) frei gewählt, kein echter Zählpunkt/PII."""
    basis_kwh_tag = 5.0
    faktor_2025 = 1.098  # +9,8 % ggü. 2024 (results_09.md: 1.298 -> 1.425 Mio kWh)
    faktor_2026 = faktor_2025 * 1.097  # +9,7 % ggü. 2025

    r2024 = _daily_records(date(2024, 4, 15), date(2024, 12, 31), basis_kwh_tag)
    r2025 = _daily_records(date(2025, 1, 1), date(2025, 12, 31), basis_kwh_tag * faktor_2025)
    r2026 = _daily_records(date(2026, 1, 1), date(2026, 6, 28), basis_kwh_tag * faktor_2026)
    return r2024 + r2025 + r2026


def test_compute_load_trend_referenz_fall_b_reproduziert_9_8_und_9_7_prozent() -> None:
    """DoD-Kriterium 5: Fenster-YoY reproduziert +9,8 %/+9,7 % (results_09.md:36-37)."""
    result = compute_load_trend(_daily_tuples(_fall_b_trend_records()))

    by_jahr = {j.jahr: j for j in result.per_year}
    assert by_jahr[2024].full_year is False
    assert by_jahr[2025].full_year is True
    assert by_jahr[2026].full_year is False

    assert result.calendar_yoy is None
    assert result.calendar_yoy_verweigert_grund is not None

    assert len(result.window_yoy) == 2
    w_24_25, w_25_26 = result.window_yoy
    assert (w_24_25.von_jahr, w_24_25.bis_jahr) == (2024, 2025)
    assert w_24_25.delta_pct == pytest.approx(9.8, abs=0.05)
    assert (w_25_26.von_jahr, w_25_26.bis_jahr) == (2025, 2026)
    assert w_25_26.delta_pct == pytest.approx(9.7, abs=0.05)

    assert result.trend_pct_pro_jahr == pytest.approx(9.8, abs=0.05)
    assert result.trend_aussage is not None
    assert "steigt" in result.trend_aussage
    assert "~10" in result.trend_aussage


def test_load_trend_fall_b_fenster_bleiben_in_trend_mit_echten_tageszahlen() -> None:
    """(c) Regressionscheck fuer den Mindest-Deckungs-Guard: Fall B (Tages-
    Granularitaet) bleibt komplett in_trend=True. Die Fenster haben echte
    261/179 gemeinsame Kalendertage (weit ueber MIN_TREND_FENSTER_TAGE=30) --
    NICHT die alte, granularitaetsabhaengige Q15-Schaetzung gemeinsame_slots/96
    (~2,7/~1,9), die den neuen Guard hier faelschlich haette ausloesen lassen."""
    result = compute_load_trend(_daily_tuples(_fall_b_trend_records()))

    w_24_25, w_25_26 = result.window_yoy
    assert w_24_25.gemeinsame_tage == pytest.approx(261.0, abs=0.5)
    assert w_24_25.in_trend is True
    assert w_24_25.grund is None
    assert w_25_26.gemeinsame_tage == pytest.approx(179.0, abs=0.5)
    assert w_25_26.in_trend is True
    assert w_25_26.grund is None


# --- Capability-Envelope + Registry + Nenner (L.6) ------------------------


def test_load_trend_capability_envelope_reproduziert_referenzfall() -> None:
    result = LoadTrendCapability().run(consumption=_fall_b_trend_records())

    assert result.ok is True
    data = result.data
    assert data["calendar_yoy"] is None
    assert data["calendar_yoy_verweigert_grund"] is not None
    assert len(data["window_yoy"]) == 2
    assert data["window_yoy"][0]["delta_pct"] == pytest.approx(9.8, abs=0.05)
    assert data["window_yoy"][1]["delta_pct"] == pytest.approx(9.7, abs=0.05)
    assert data["trend_pct_pro_jahr"] == pytest.approx(9.8, abs=0.05)
    assert "steigt" in data["trend_aussage"]
    assert data["rechenweg"]["full_year_threshold_tage"] == FULL_YEAR_DAY_THRESHOLD
    assert data["caveats"]
    assert result.meta.get("quelle")


def test_load_trend_capability_envelope_zeigt_mindest_deckungs_guard() -> None:
    """Der Mindest-Deckungs-Guard (Korrektheits-Fix 2026-07-20) muss im
    Envelope sichtbar sein: rechenweg dokumentiert die Schwelle, jedes
    window_yoy-Element traegt in_trend/grund."""
    result = LoadTrendCapability().run(consumption=_fall_b_trend_records())

    assert result.ok is True
    data = result.data
    assert data["rechenweg"]["min_fenster_tage"] == MIN_TREND_FENSTER_TAGE
    assert data["rechenweg"].get("min_fenster_tage_regel")
    for fenster in data["window_yoy"]:
        assert "in_trend" in fenster
        assert "grund" in fenster
        assert fenster["in_trend"] is True
        assert fenster["grund"] is None


def test_load_trend_capability_leere_consumption_liefert_ok_false() -> None:
    result = LoadTrendCapability().run(consumption=[])

    assert result.ok is False
    assert result.data is None
    assert result.error


def test_load_trend_capability_registry_smoke() -> None:
    cap = default_registry().get("load_trend")
    assert isinstance(cap, LoadTrendCapability)
    assert cap.name == "load_trend"


def test_load_trend_capability_result_field_paths_deckt_top_level_skalare_ab() -> None:
    pfade = LoadTrendCapability().result_field_paths()
    for feld in ("trend_aussage", "trend_pct_pro_jahr", "calendar_yoy_verweigert_grund"):
        assert feld in pfade


def test_load_trend_nenner_deckt_delta_pct_ab() -> None:
    result = LoadTrendCapability().run(consumption=_fall_b_trend_records())

    assert result.ok is True
    nenner = result.data["nenner"]
    assert nenner.get("window_yoy.delta_pct")
    assert nenner.get("trend_pct_pro_jahr")


# ---------------------------------------------------------------------------
# L.4 — spot_backtest / tarif_ersparnis (WP2-L Durchstich 2)
#
# spot_prices/consumption werden als Parameter injiziert (L.4.2, offline
# testbar) — KEINE DB-/Netz-Abhängigkeit im Rechen-Kern. Alle Serien
# synthetisch (Sinus/Konstante-Bausteine), KEINE echten Zählpunkte/Namen
# (MIT-Repo-Pflicht, DoD-Kriterium 13).
# ---------------------------------------------------------------------------


def _spot_price_series(start: datetime, hours: int, ct_day: float, ct_night: float) -> list[dict]:
    """Synthetische EPEX-Stundenreihe: günstige Nacht (0-3h), teurer Tag."""
    out: list[dict] = []
    for h in range(hours):
        ts = start + timedelta(hours=h)
        price = ct_night if ts.hour in (0, 1, 2, 3) else ct_day
        out.append({"timestamp": ts.isoformat(), "price_ct": price})
    return out


def _timestamp_consumption(start: datetime, hours: int, kwh_per_hour: float) -> list[dict]:
    """Consumption im Primitiv-Format ('timestamp'-Schlüssel), wie es
    ``compute_spot_effective``/``compute_annual_cost`` direkt erwarten (L.4.2)."""
    return [
        {"timestamp": (start + timedelta(hours=h)).isoformat(), "kwh": kwh_per_hour}
        for h in range(hours)
    ]


def _ts_consumption(start: datetime, hours: int, kwh_per_hour: float) -> list[dict]:
    """Wie ``_timestamp_consumption``, aber mit dem 'ts'-Schlüssel des
    Capability-Input-Schemas (``_CONSUMPTION_SERIES``, wie L.1/L.2) — UND in
    echter Q15-Auflösung (4 Slots/Stunde, Gesamt-kWh unverändert): diese
    Records laufen durch ``SpotBacktestCapability._run`` (anders als
    ``_timestamp_consumption``, das direkt an ``compute_spot_backtest``
    geht), also greift dort der Granularitäts-Guard (F29 (a)) — Stunden-Slots
    (60 min) gälten als zu grob und würden die Capability ok=False liefern."""
    slots_per_hour = 4
    kwh_per_slot = kwh_per_hour / slots_per_hour
    return [
        {"ts": (start + timedelta(hours=h, minutes=slot * 15)).isoformat(), "kwh": kwh_per_slot}
        for h in range(hours)
        for slot in range(slots_per_hour)
    ]


# --- Rechen-Kern: compute_spot_backtest (Guards, L.4.3) -------------------


def test_compute_spot_backtest_ohne_spot_prices_liefert_grund() -> None:
    core = compute_spot_backtest([], [], 24.0)

    assert core.verfuegbar is False
    assert core.grund == GRUND_KEIN_SPOT
    assert core.spot_netto_eur is None  # NIE 0 zeigen


def test_compute_spot_backtest_ohne_consumption_liefert_grund() -> None:
    spot_prices = _spot_price_series(datetime(2025, 1, 1), 24, ct_day=20.0, ct_night=5.0)

    core = compute_spot_backtest([], spot_prices, 24.0)

    assert core.verfuegbar is False
    assert core.grund == GRUND_KEIN_VERBRAUCH


def test_compute_spot_backtest_ohne_fixpreis_liefert_grund() -> None:
    start = datetime(2025, 1, 1)
    consumption = _timestamp_consumption(start, 24, 1.0)
    spot_prices = _spot_price_series(start, 24, ct_day=20.0, ct_night=5.0)

    core = compute_spot_backtest(consumption, spot_prices, None)

    assert core.verfuegbar is False
    assert core.grund == GRUND_KEIN_FIXPREIS


def test_compute_spot_backtest_disjunkte_zeitraeume_liefert_grund_statt_null() -> None:
    """Verbrauch (2024) und EPEX-Preise (2026) überlappen sich nicht -> Ablehnung
    MIT Begründung (nicht stillschweigend 0/None, L.4.5-Non-Overlap-Test)."""
    consumption = _timestamp_consumption(datetime(2024, 1, 1), 24, 1.0)
    spot_prices = _spot_price_series(datetime(2026, 1, 1), 24, ct_day=20.0, ct_night=5.0)

    core = compute_spot_backtest(consumption, spot_prices, 24.0)

    assert core.verfuegbar is False
    assert core.grund is not None
    assert "überlappen" in core.grund


def test_compute_spot_backtest_aufschlag_ct_immer_im_result_auch_ohne_daten() -> None:
    core = compute_spot_backtest([], [], None, aufschlag_ct=2.75)

    assert core.aufschlag_ct == 2.75


def test_compute_spot_backtest_happy_path_liefert_plausible_werte() -> None:
    start = datetime(2025, 1, 1, 0, 0)
    consumption = _timestamp_consumption(start, 72, 1.0)  # 3 Tage, konstant 1 kWh/h
    spot_prices = _spot_price_series(start, 72, ct_day=20.0, ct_night=5.0)

    core = compute_spot_backtest(
        consumption, spot_prices, energiepreis_brutto_ct_kwh=24.0, aufschlag_ct=1.5,
    )

    assert core.verfuegbar is True
    assert core.grund is None
    assert core.aufschlag_ct == 1.5
    assert core.basis == "eigene Verbrauchsdaten"
    assert core.effektiver_spot_ct is not None and core.effektiver_spot_ct > 0
    assert core.spot_netto_eur is not None and core.spot_netto_eur > 0
    # Fix: 24.0 brutto / 1.2 USt = 20.0 ct netto * 72 kWh / 100 = 14.40 EUR
    assert core.fix_netto_eur == pytest.approx(14.40, abs=0.01)
    assert core.differenz_eur == pytest.approx(core.fix_netto_eur - core.spot_netto_eur, abs=0.01)


# --- Rechen-Kern: extract_tarif_ersparnis (dünne Sicht, L.4.3) ------------


def test_extract_tarif_ersparnis_bei_abgelehntem_tariff_compare() -> None:
    core = extract_tarif_ersparnis(
        ok=False, error="plz ist erforderlich (4-stellige österreichische PLZ)",
        data=None, aktueller_lieferant="Alt AG",
    )

    assert core.verfuegbar is False
    assert "plz ist erforderlich" in core.grund


def test_extract_tarif_ersparnis_bei_leeren_alternativen() -> None:
    core = extract_tarif_ersparnis(
        ok=True, error=None,
        data={"alternativen": [], "aktueller_tarif": {}, "max_ersparnis_eur": 0.0},
        aktueller_lieferant="Alt AG",
    )

    assert core.verfuegbar is False
    assert core.grund == GRUND_TARIF_ERSPARNIS_LEER


def test_extract_tarif_ersparnis_happy_path() -> None:
    data = {
        "aktueller_tarif": {"jahreskosten_eur": 900.0},
        "alternativen": [
            {"jahreskosten_eur": 700.0, "lieferant": "Guenstig AG", "tarif_name": "Spar-Tarif"},
        ],
        "max_ersparnis_eur": 200.0,
        "netzkosten_vollstaendig": True,
    }

    core = extract_tarif_ersparnis(ok=True, error=None, data=data, aktueller_lieferant="Alt AG")

    assert core.verfuegbar is True
    assert core.grund is None
    assert core.ist_eur == 900.0
    assert core.best_eur == 700.0
    assert core.ersparnis_eur == 200.0
    assert core.lieferant_ist == "Alt AG"
    assert core.lieferant_best == "Guenstig AG"
    assert core.tarif_best == "Spar-Tarif"
    assert core.netzkosten_vollstaendig is True


def test_extract_tarif_ersparnis_netzkosten_unvollstaendig_faellt_auf_ep_anteil_zurueck() -> None:
    """tariff_compare markiert netzkosten_vollstaendig=false -> die Beträge
    kommen aus 'energiepreis_anteil_eur' statt 'jahreskosten_eur' (B.7-Marker)."""
    data = {
        "aktueller_tarif": {"energiepreis_anteil_eur": 500.0},
        "alternativen": [{"energiepreis_anteil_eur": 420.0, "lieferant": "B", "tarif_name": "T"}],
        "max_ersparnis_eur": 80.0,
        "netzkosten_vollstaendig": False,
    }

    core = extract_tarif_ersparnis(ok=True, error=None, data=data, aktueller_lieferant="Alt AG")

    assert core.verfuegbar is True
    assert core.ist_eur == 500.0
    assert core.best_eur == 420.0
    assert core.netzkosten_vollstaendig is False


# --- Capability-Envelope: beide Blöcke, unabhängig optional ---------------


class _FakeTariffSource:
    """Strukturelle TariffSource — In-Memory-Zeilen, kein Storage (wie
    ``test_tariff_compare.py::FakeTariffSource``, hier eigenständig gehalten)."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def get_latest(self, *, status: str, energy_type: str) -> list[dict]:
        return [r for r in self._rows if (r.get("energy_type") or "POWER") == energy_type]


def _guenstiger_tarif_katalog() -> list[dict]:
    return [
        {
            "key": "g1", "lieferant": "Guenstig AG", "tarif_name": "Spar-Tarif",
            "tariftyp": "Fixpreis", "energiepreis_ct_kwh": 8.0,
            "grundgebuehr_eur_monat": 3.0, "ist_oekostrom": False,
        },
    ]


def _tariff_compare_mit_fake_katalog() -> TariffCompareCapability:
    return TariffCompareCapability(tariff_source=_FakeTariffSource(_guenstiger_tarif_katalog()))


def test_spot_backtest_capability_envelope_beide_bloecke_verfuegbar() -> None:
    start = datetime(2025, 1, 1, 0, 0)
    consumption = _ts_consumption(start, 72, 1.0)
    spot_prices = _spot_price_series(start, 72, ct_day=20.0, ct_night=5.0)

    cap = SpotBacktestCapability(tariff_compare=_tariff_compare_mit_fake_katalog())
    result = cap.run(
        consumption=consumption,
        spot_prices=spot_prices,
        energiepreis_brutto_ct_kwh=24.0,
        plz="1010",
        jahresverbrauch_kwh=3500,
        aktueller_lieferant="Alt AG",
        aktuelle_grundgebuehr_brutto_eur_monat=8.0,
    )

    assert result.ok is True
    data = result.data
    assert data["spot_backtest"]["verfuegbar"] is True
    assert data["spot_backtest"]["effektiver_spot_ct"] > 0
    assert data["spot_backtest"]["aufschlag_ct"] == DEFAULT_SPOT_AUFSCHLAG_CT
    assert data["tarif_ersparnis"]["verfuegbar"] is True
    assert data["tarif_ersparnis"]["lieferant_best"] == "Guenstig AG"
    assert data["tarif_ersparnis"]["ersparnis_eur"] > 0
    assert data["caveats"]
    assert result.meta.get("quelle")


def test_tarif_ersparnis_ist_minus_best_bleibt_konsistent_mit_ersparnis_eur() -> None:
    """Folgeauftrag zu fix/ersparnis-gesamtkosten: seit tariff_compare's
    max_ersparnis_eur bei netzkosten_vollstaendig=true die GESAMTKOSTEN-
    Differenz ist (Energie + Netz + Gebrauchsabgabe), aber ist_eur/best_eur
    hier WEITERHIN die reine Energiepreis-Basis sind (s.
    _CAVEAT_TARIF_ERSPARNIS_ENERGIEBASIS), darf ersparnis_eur NICHT mehr
    blind von tariff_compare übernommen werden — sonst
    ``ist_eur − best_eur != ersparnis_eur`` (dasselbe "zwei Zahlenwelten"-
    Muster, eine Ebene tiefer). PLZ 1010 (Wien) löst einen Netzbetreiber auf
    -> netzkosten_vollstaendig=true, GENAU der Fall, in dem der Bug sichtbar
    würde. Pinnt die Konsistenz über die ECHTE Pipeline
    (SpotBacktestCapability -> TariffCompareCapability), keine Hand-Fixture."""
    start = datetime(2025, 1, 1, 0, 0)
    consumption = _ts_consumption(start, 72, 1.0)
    spot_prices = _spot_price_series(start, 72, ct_day=20.0, ct_night=5.0)

    cap = SpotBacktestCapability(tariff_compare=_tariff_compare_mit_fake_katalog())
    result = cap.run(
        consumption=consumption,
        spot_prices=spot_prices,
        energiepreis_brutto_ct_kwh=24.0,
        plz="1010",
        jahresverbrauch_kwh=3500,
        aktueller_lieferant="Alt AG",
        aktuelle_grundgebuehr_brutto_eur_monat=8.0,
    )

    assert result.ok is True
    block = result.data["tarif_ersparnis"]
    assert block["netzkosten_vollstaendig"] is True  # genau der Fall, in dem der Bug feuern würde
    assert block["ist_eur"] == pytest.approx(936.0, abs=0.01)
    assert block["best_eur"] == pytest.approx(379.2, abs=0.01)
    assert block["ersparnis_eur"] == pytest.approx(556.8, abs=0.01)
    assert block["ersparnis_eur"] == pytest.approx(block["ist_eur"] - block["best_eur"], abs=0.01)

    # Gegenprobe: tariff_compare's EIGENE max_ersparnis_eur ist (bewusst) NICHT
    # dieselbe Zahl — sie ist gesamtkosten-basiert (Energie+Netz+GAB), während
    # tarif_ersparnis hier auf der Energie-Basis bleibt. Würde ersparnis_eur
    # weiterhin blind von tariff_compare übernommen, wäre es 592.08 statt
    # 556.8 — genau die Divergenz, die dieser Test verhindert.
    tcmp = _tariff_compare_mit_fake_katalog().run(
        plz="1010", jahresverbrauch_kwh=3500, aktueller_lieferant="Alt AG",
        aktueller_energiepreis_brutto_ct_kwh=24.0,
        aktuelle_grundgebuehr_brutto_eur_monat=8.0,
    )
    assert tcmp.data["netzkosten_vollstaendig"] is True
    assert tcmp.data["max_ersparnis_eur"] == pytest.approx(592.08, abs=0.01)
    assert block["ersparnis_eur"] != pytest.approx(tcmp.data["max_ersparnis_eur"], abs=0.01)


def test_spot_backtest_capability_bloecke_unabhaengig_spot_ohne_tarif_felder() -> None:
    """DoD: beide Blöcke unabhängig optional — nur Spot-Eingaben -> Spot
    verfügbar, tarif_ersparnis lehnt MIT Begründung ab (fehlende Felder)."""
    start = datetime(2025, 1, 1, 0, 0)
    consumption = _ts_consumption(start, 48, 1.0)
    spot_prices = _spot_price_series(start, 48, ct_day=20.0, ct_night=5.0)

    result = SpotBacktestCapability().run(
        consumption=consumption, spot_prices=spot_prices, energiepreis_brutto_ct_kwh=24.0,
    )

    assert result.ok is True
    assert result.data["spot_backtest"]["verfuegbar"] is True
    assert result.data["tarif_ersparnis"]["verfuegbar"] is False
    assert "plz" in result.data["tarif_ersparnis"]["grund"]


def test_spot_backtest_capability_aufschlag_ct_null_wird_respektiert() -> None:
    """Review-Finding: explizites aufschlag_ct=0.0 darf nicht still durch den
    Default ersetzt werden (Falsy-Falle bei `or`) — sonst ist der €-Wert eines
    Null-Aufschlag-Backtests falsch."""
    start = datetime(2025, 1, 1, 0, 0)
    consumption = _ts_consumption(start, 48, 1.0)
    spot_prices = _spot_price_series(start, 48, ct_day=20.0, ct_night=5.0)

    result = SpotBacktestCapability().run(
        consumption=consumption,
        spot_prices=spot_prices,
        energiepreis_brutto_ct_kwh=24.0,
        aufschlag_ct=0.0,
    )

    assert result.ok is True
    assert result.data["spot_backtest"]["aufschlag_ct"] == 0.0


def test_spot_backtest_capability_bloecke_unabhaengig_tarif_ohne_spot_felder() -> None:
    cap = SpotBacktestCapability(tariff_compare=_tariff_compare_mit_fake_katalog())

    result = cap.run(
        plz="1010", jahresverbrauch_kwh=3500, aktueller_lieferant="Alt AG",
        energiepreis_brutto_ct_kwh=24.0, aktuelle_grundgebuehr_brutto_eur_monat=8.0,
    )

    assert result.ok is True
    assert result.data["spot_backtest"]["verfuegbar"] is False
    assert result.data["spot_backtest"]["grund"] == GRUND_KEIN_SPOT
    assert result.data["tarif_ersparnis"]["verfuegbar"] is True


def test_spot_backtest_capability_ungueltige_spot_prices_liefert_ok_false() -> None:
    result = SpotBacktestCapability().run(spot_prices=[{"foo": "bar"}])

    assert result.ok is False
    assert result.data is None


def test_spot_backtest_capability_registry_smoke() -> None:
    cap = default_registry().get("spot_backtest")
    assert isinstance(cap, SpotBacktestCapability)
    assert cap.name == "spot_backtest"


def test_spot_backtest_capability_result_field_paths_deckt_beide_bloecke_ab() -> None:
    pfade = SpotBacktestCapability().result_field_paths()
    for feld in (
        "spot_backtest.verfuegbar",
        "spot_backtest.profilkostenfaktor_pct",
        "tarif_ersparnis.verfuegbar",
        "tarif_ersparnis.ersparnis_eur",
    ):
        assert feld in pfade


def test_spot_backtest_capability_nenner_deckt_profilkostenfaktor_ab() -> None:
    start = datetime(2025, 1, 1, 0, 0)
    consumption = _ts_consumption(start, 48, 1.0)
    spot_prices = _spot_price_series(start, 48, ct_day=20.0, ct_night=5.0)

    result = SpotBacktestCapability().run(
        consumption=consumption, spot_prices=spot_prices, energiepreis_brutto_ct_kwh=24.0,
    )

    assert result.ok is True
    assert result.data["nenner"].get("spot_backtest.profilkostenfaktor_pct")


def test_spot_backtest_capability_meta_stand_kommt_aus_der_spot_reihe() -> None:
    """_meta: Datenstand der ÜBERGEBENEN Spot-Reihe (Muster
    SnapshotSpotPriceSource.meta) — nicht das (hier viel ältere)
    Verbrauchsfenster."""
    consumption = _ts_consumption(datetime(2020, 1, 1, 0, 0), 24, 1.0)
    spot_start = datetime(2025, 6, 1, 0, 0)
    spot_prices = _spot_price_series(spot_start, 24, ct_day=20.0, ct_night=5.0)

    result = SpotBacktestCapability().run(
        consumption=consumption, spot_prices=spot_prices, energiepreis_brutto_ct_kwh=24.0,
    )

    assert result.meta.get("stand", "").startswith("2025-06-01")


# ---------------------------------------------------------------------------
# spot_backtest — Granularitäts-Guard (F29 (a), Plan DURCHSTICH-2-PLAN.md §4
# F29 + §2 WP2-P Punkt 5): derselbe Laufzeit-Guard wie lastgang_signals
# (interval_minutes>=60 -> Ablehnung), hier aus den Timestamps der
# consumption-Serie abgeleitet (kein interval_minutes-Inputfeld auf dieser
# Capability).
# ---------------------------------------------------------------------------


def _tageswerte_consumption(start: datetime, tage: int, kwh_pro_tag: float) -> list[dict]:
    """Tageswerte-Serie: ein Slot/Tag (Slot-Abstand 1440 min) — kein Q15-Opt-in."""
    return [
        {"ts": (start + timedelta(days=d)).isoformat(), "kwh": kwh_pro_tag} for d in range(tage)
    ]


def test_spot_backtest_capability_tageswerte_serie_liefert_ok_false() -> None:
    """Tageswerte-Serie (Slot-Abstand >=60 min) -> ok=False mit klarer
    Begründung + Q15-Opt-in-Empfehlung (F29 (a))."""
    start = datetime(2025, 1, 1, 0, 0)
    consumption = _tageswerte_consumption(start, 30, 24.0)
    spot_prices = _spot_price_series(start, 30 * 24, ct_day=20.0, ct_night=5.0)

    result = SpotBacktestCapability().run(
        consumption=consumption, spot_prices=spot_prices, energiepreis_brutto_ct_kwh=24.0,
    )

    assert result.ok is False
    assert result.data is None
    assert "braucht 15-min-Auflösung" in result.error
    assert "f_q15_optin" in result.error


def test_spot_backtest_capability_q15_serie_bleibt_ok() -> None:
    """Gegenprobe: eine echte Q15-Serie wird NICHT vom Granularitäts-Guard
    abgelehnt — beide Blöcke laufen normal durch."""
    start = datetime(2025, 1, 1, 0, 0)
    consumption = _ts_consumption(start, 48, 1.0)
    spot_prices = _spot_price_series(start, 48, ct_day=20.0, ct_night=5.0)

    result = SpotBacktestCapability().run(
        consumption=consumption, spot_prices=spot_prices, energiepreis_brutto_ct_kwh=24.0,
    )

    assert result.ok is True
    assert result.data["spot_backtest"]["verfuegbar"] is True


def test_compute_spot_backtest_fix_und_spot_ueber_gleiches_volumen() -> None:
    """Volumen-Parität (Demo-Fund 2026-07-13): Verbrauch länger als die
    EPEX-Deckung → BEIDE Seiten rechnen nur über die EPEX-gedeckten Slots,
    sonst ist differenz_eur um das ungedeckte Volumen aufgebläht (Fix-Seite
    bepreiste 1,5 Jahre, Spot-Seite 1 Jahr)."""
    start = datetime(2025, 1, 1, 0, 0)
    consumption = _timestamp_consumption(start, 48, 1.0)  # 48 h à 1 kWh
    spot_prices = _spot_price_series(start, 24, ct_day=20.0, ct_night=5.0)  # nur Tag 1

    core = compute_spot_backtest(
        consumption, spot_prices, energiepreis_brutto_ct_kwh=24.0, aufschlag_ct=1.5,
    )

    assert core.verfuegbar is True
    # Fix: 20 ct netto × 24 GEDECKTE kWh = 4.80 € — nicht 9.60 € über alle 48 h.
    assert core.fix_netto_eur == pytest.approx(4.80, abs=0.01)
    assert core.differenz_eur == pytest.approx(core.fix_netto_eur - core.spot_netto_eur, abs=0.01)
    # Das Vergleichsfenster ist Teil des Results (Rechenweg-Ehrlichkeit).
    assert core.vergleichs_kwh == pytest.approx(24.0, abs=0.01)
    assert core.vergleich_von is not None and core.vergleich_von.startswith("2025-01-01")
    assert core.vergleich_bis is not None and core.vergleich_bis.startswith("2025-01-01")
