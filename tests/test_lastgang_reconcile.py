# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für den Fakt-Präzedenz-Reconciler (``lastgang/reconcile.py``,
Fakt-vor-Heuristik).

Alle Serien sind synthetisch (Sinus/Konstante-Bausteine) — KEINE echten
Zählpunkte (MIT-Repo-Pflicht, DoD-Kriterium 13).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from energietools.capabilities.lastgang.guards import apply_pv_guards
from energietools.capabilities.lastgang.reconcile import (
    ABGLEICH_KEIN_FAKT,
    ABGLEICH_KONSISTENT,
    ABGLEICH_NICHT_PRUEFBAR,
    ABGLEICH_WIDERSPRUCH,
    PRAEZEDENZ,
    SIGNAL_FELD_MAPPING,
    reconcile_rueckfragen,
    reconcile_signals,
)
from energietools.capabilities.lastgang.signals import (
    Rueckfrage,
    Signal,
    compute_signals,
    select_rueckfragen,
)
from energietools.capabilities.profile import FaktWert, InMemoryProfileFacts, parse_profil_fakten

# ---------------------------------------------------------------------------
# Synthetische Serien-Bausteine (kein PII)
# ---------------------------------------------------------------------------


def _flat_hourly(value: float) -> list[float]:
    return [value] * 24


def _days(start: datetime, count: int) -> list[datetime]:
    return [start + timedelta(days=i) for i in range(count)]


def _consumption_from_days(
    days: list[tuple[datetime, list[float]]], interval_minutes: int = 15
) -> list[tuple[datetime, float]]:
    slots_per_hour = 60 // interval_minutes
    records: list[tuple[datetime, float]] = []
    for day, hourly in days:
        for hour in range(24):
            slot_kwh = hourly[hour] / slots_per_hour
            for slot in range(slots_per_hour):
                ts = datetime(day.year, day.month, day.day, hour, slot * interval_minutes)
                records.append((ts, round(slot_kwh, 6)))
    return records


def _ws_ratio_2_7_consumption() -> list[tuple[datetime, float]]:
    """Winter/Sommer = 0.27/0.10 = 2.70 — exakt der Referenzfall aus dem Bauplan."""
    winter_days = [(d, _flat_hourly(0.27)) for d in _days(datetime(2025, 1, 5), 4)]
    summer_days = [(d, _flat_hourly(0.10)) for d in _days(datetime(2025, 7, 5), 4)]
    return _consumption_from_days(winter_days + summer_days)


def _keine_mittagsdelle_consumption() -> list[tuple[datetime, float]]:
    """Flacher Tagesverlauf -> midday_dip_ratio ~= 1 (kein PV-Hinweis)."""
    days = [(d, _flat_hourly(0.2)) for d in _days(datetime(2025, 5, 1), 3)]
    return _consumption_from_days(days)


def _niedrige_nachtgrundlast_consumption() -> list[tuple[datetime, float]]:
    """Niedrige, flache Nachtgrundlast -> high_continuous_load UNLIKELY."""
    days = [(d, _flat_hourly(0.02)) for d in _days(datetime(2025, 3, 3), 3)]
    return _consumption_from_days(days)


def _alle_drei_signale_likely_consumption() -> list[tuple[datetime, float]]:
    """Ein Tagesprofil, das ALLE drei bedingten Rückfragen gleichzeitig
    feuert: hohe WS-Ratio (Heizung), Mittags-Delle (PV), hohe
    Nacht-Grundlast (Dauerläufer)."""

    def _hourly(other: float) -> list[float]:
        hourly = [other] * 24
        for h in range(0, 5):  # Nacht: konstant hoch (0-4h, F9-Fenster)
            hourly[h] = 0.5
        for h in range(10, 16):  # Mittag: konstant niedrig (Delle)
            hourly[h] = 0.05
        return hourly

    winter_days = [(d, _hourly(1.0)) for d in _days(datetime(2025, 1, 5), 4)]
    summer_days = [(d, _hourly(0.1)) for d in _days(datetime(2025, 7, 5), 4)]
    return _consumption_from_days(winter_days + summer_days)


def _guard_ohne_pv(signals):
    return apply_pv_guards(signals, is_pv=False, grundlast_kw=None)


def _finde(abgleich, antwort: str):
    return next(a for a in abgleich.abgleiche if a.antwort == antwort)


# ---------------------------------------------------------------------------
# Referenzfall: Fakt gas schlägt WS-Ratio-2.7-Heuristik
# ---------------------------------------------------------------------------


def test_fakt_gas_schlaegt_ws_ratio_heuristik() -> None:
    signals = compute_signals(_ws_ratio_2_7_consumption())
    assert signals.winter_summer_ratio == pytest.approx(2.7, abs=0.01)
    assert signals.electric_heating is Signal.LIKELY  # ungeguardete Ausgangslage

    guard = _guard_ohne_pv(signals)
    fakten = InMemoryProfileFacts(
        [FaktWert(feld="asset.heating.type", wert="gas", quelle="profil")]
    )

    abgleich = reconcile_signals(signals, guard, fakten)
    heizung = _finde(abgleich, "heizung")

    assert heizung.wert == "gas"
    assert heizung.quelle == "profil"
    assert heizung.status == ABGLEICH_WIDERSPRUCH
    assert heizung.heuristik_schaetzung == "vermutlich_elektrisch"
    assert heizung.signal_roh == "likely"
    assert heizung.signal_effektiv == "unlikely"
    assert heizung.kennzahl == "winter_summer_ratio=2.7 (Schwelle 2.5)"
    assert heizung.caveat is not None
    assert "Heizung" in heizung.caveat
    assert abgleich.anzahl_widersprueche == 1
    assert abgleich.verfuegbar is True


def test_fakt_elektrisch_bei_hoher_ws_ratio_ist_konsistent() -> None:
    signals = compute_signals(_ws_ratio_2_7_consumption())
    guard = _guard_ohne_pv(signals)
    fakten = InMemoryProfileFacts(
        [FaktWert(feld="asset.heating.type", wert="waermepumpe", quelle="profil")]
    )

    abgleich = reconcile_signals(signals, guard, fakten)
    heizung = _finde(abgleich, "heizung")

    assert heizung.status == ABGLEICH_KONSISTENT
    assert heizung.signal_roh == heizung.signal_effektiv == "likely"
    assert heizung.caveat is None
    assert abgleich.anzahl_widersprueche == 0


def test_fakt_pv_kwp_schlaegt_fehlende_mittagsdelle() -> None:
    signals = compute_signals(_keine_mittagsdelle_consumption())
    assert signals.pv_self_consumption is Signal.UNLIKELY
    guard = _guard_ohne_pv(signals)
    fakten = InMemoryProfileFacts([FaktWert(feld="asset.pv.kwp", wert=5.0, quelle="profil")])

    abgleich = reconcile_signals(signals, guard, fakten)
    pv = _finde(abgleich, "pv")

    assert pv.wert == 5.0
    assert pv.status == ABGLEICH_WIDERSPRUCH
    assert pv.signal_roh == "unlikely"
    assert pv.signal_effektiv == "likely"
    assert pv.heuristik_schaetzung == "vermutlich_keine_pv"
    assert pv.caveat is not None


def test_fakt_continuous_loads_bei_niedriger_nachtgrundlast_widerspruch() -> None:
    signals = compute_signals(_niedrige_nachtgrundlast_consumption())
    assert signals.high_continuous_load is Signal.UNLIKELY
    guard = _guard_ohne_pv(signals)
    fakten = InMemoryProfileFacts(
        [FaktWert(feld="asset.continuous_loads", wert="Poolpumpe", quelle="profil")]
    )

    abgleich = reconcile_signals(signals, guard, fakten)
    dauerlast = _finde(abgleich, "dauerlast")

    assert dauerlast.wert == "Poolpumpe"
    assert dauerlast.status == ABGLEICH_WIDERSPRUCH
    assert dauerlast.signal_roh == "unlikely"
    assert dauerlast.signal_effektiv == "likely"


# ---------------------------------------------------------------------------
# E1: 'sonstiges' ist unkategorisiert -> UNKNOWN, nicht UNLIKELY (Overclaim-Fix)
# ---------------------------------------------------------------------------


def test_fakt_sonstiges_ergibt_nicht_pruefbar_und_heuristik_bleibt() -> None:
    """'sonstiges' ist NICHT 'keine' — ein Overclaim würde 'nicht elektrisch'
    behaupten (z.B. Infrarot-/Nachtspeicherheizung wäre real elektrisch). Der
    Fakt impliziert UNKNOWN: die Heuristik bleibt die Antwort (signal_effektiv
    == signal_roh, quelle=='heuristik'), der Wert 'sonstiges' bleibt im
    Abgleich sichtbar, status wird 'nicht_pruefbar' (kein Widerspruch)."""
    signals = compute_signals(_ws_ratio_2_7_consumption())
    assert signals.electric_heating is Signal.LIKELY  # ungeguardete Ausgangslage
    guard = _guard_ohne_pv(signals)
    fakten = InMemoryProfileFacts(
        [FaktWert(feld="asset.heating.type", wert="sonstiges", quelle="profil")]
    )

    abgleich = reconcile_signals(signals, guard, fakten)
    heizung = _finde(abgleich, "heizung")

    assert heizung.wert == "sonstiges"  # Fakt bleibt sichtbar
    assert heizung.quelle == "heuristik"  # Heuristik bleibt die Antwort
    assert heizung.status == ABGLEICH_NICHT_PRUEFBAR
    assert heizung.signal_roh == "likely"
    assert heizung.signal_effektiv == "likely"  # == signal_roh, kein Overclaim auf 'unlikely'
    assert heizung.heuristik_schaetzung == "vermutlich_elektrisch"
    assert heizung.caveat is None
    assert abgleich.anzahl_widersprueche == 0

    # 'keine' bleibt weiterhin klar UNLIKELY (unverändert durch den Fix).
    fakten_keine = InMemoryProfileFacts(
        [FaktWert(feld="asset.heating.type", wert="keine", quelle="profil")]
    )
    heizung_keine = _finde(reconcile_signals(signals, guard, fakten_keine), "heizung")
    assert heizung_keine.signal_effektiv == "unlikely"
    assert heizung_keine.status == ABGLEICH_WIDERSPRUCH

    # Rückfrage bleibt trotzdem unterdrückt: der User HAT geantwortet, auch
    # wenn die Antwort 'sonstiges' war (reconcile_rueckfragen prüft nur, ob
    # ein Fakt existiert — nicht welchen Wert er trägt).
    rueckfragen = [Rueckfrage(feld="asset.heating.type", frage="?", motiviert_durch="x")]
    verbleibend, unterdrueckt = reconcile_rueckfragen(rueckfragen, fakten)
    assert verbleibend == []
    assert unterdrueckt == ["asset.heating.type"]


# ---------------------------------------------------------------------------
# E5: enum-Kanonisierung greift bis in die reconcile-Klassifikation durch
# ---------------------------------------------------------------------------


def test_fakt_elektrisch_grossschreibung_wird_kanonisch_klassifiziert() -> None:
    """'Elektrisch' (Großschreibung) wird beim Parsen zu 'elektrisch'
    kanonisiert (E5) — die reconcile-Klassifikation sieht dadurch korrekt
    LIKELY, ohne dass reconcile.py selbst case-tolerant sein müsste."""
    signals = compute_signals(_ws_ratio_2_7_consumption())
    guard = _guard_ohne_pv(signals)
    fakten = parse_profil_fakten({"asset.heating.type": "Elektrisch"})

    abgleich = reconcile_signals(signals, guard, fakten)
    heizung = _finde(abgleich, "heizung")

    assert heizung.wert == "elektrisch"
    assert heizung.status == ABGLEICH_KONSISTENT
    assert heizung.signal_effektiv == "likely"


# ---------------------------------------------------------------------------
# PV-Guard -> nicht_pruefbar-Stufenordnung
# ---------------------------------------------------------------------------


def test_pv_guard_unknown_ergibt_nicht_pruefbar() -> None:
    signals = compute_signals(_ws_ratio_2_7_consumption())
    assert signals.electric_heating is Signal.LIKELY

    guard = apply_pv_guards(signals, is_pv=True, grundlast_kw=None)
    assert guard.electric_heating is Signal.UNKNOWN  # PV-Guard hat herabgestuft

    fakten = InMemoryProfileFacts(
        [FaktWert(feld="asset.heating.type", wert="gas", quelle="profil")]
    )
    abgleich = reconcile_signals(signals, guard, fakten)
    heizung = _finde(abgleich, "heizung")

    assert heizung.status == ABGLEICH_NICHT_PRUEFBAR
    assert heizung.signal_roh == "unknown"
    assert heizung.caveat is None
    assert abgleich.anzahl_widersprueche == 0
    # Kennzahl bleibt trotzdem die ECHTE WS-Ratio aus signals (Fenster-Falle!).
    assert heizung.kennzahl == "winter_summer_ratio=2.7 (Schwelle 2.5)"


# ---------------------------------------------------------------------------
# Kein Fakt -> Heuristik-Labels + kein_fakt-Status
# ---------------------------------------------------------------------------


def test_kein_fakt_liefert_heuristik_labels_und_kein_fakt_status() -> None:
    signals = compute_signals(_ws_ratio_2_7_consumption())
    guard = _guard_ohne_pv(signals)
    leer = InMemoryProfileFacts()

    abgleich = reconcile_signals(signals, guard, leer)

    assert abgleich.verfuegbar is False
    for eintrag in abgleich.abgleiche:
        assert eintrag.status == ABGLEICH_KEIN_FAKT
        assert eintrag.quelle == "heuristik"
        assert eintrag.wert is None
        assert eintrag.stand is None
        assert eintrag.caveat is None

    heizung = _finde(abgleich, "heizung")
    assert heizung.heuristik_schaetzung == "vermutlich_elektrisch"
    assert heizung.signal_effektiv == heizung.signal_roh == "likely"


# ---------------------------------------------------------------------------
# reconcile_rueckfragen
# ---------------------------------------------------------------------------


def test_reconcile_rueckfragen_unterdrueckt_beantwortete_felder() -> None:
    rueckfragen = [
        Rueckfrage(feld="asset.heating.type", frage="?", motiviert_durch="x"),
        Rueckfrage(feld="asset.pv.kwp", frage="?", motiviert_durch="x"),
        Rueckfrage(feld="asset.continuous_loads", frage="?", motiviert_durch="x"),
        Rueckfrage(feld="behavior.appliance_timing", frage="?", motiviert_durch="x"),
    ]
    fakten = InMemoryProfileFacts(
        [
            FaktWert(feld="asset.heating.type", wert="gas", quelle="profil"),
            FaktWert(feld="behavior.appliance_timing", wert="flexibel", quelle="profil"),
        ]
    )

    verbleibend, unterdrueckt = reconcile_rueckfragen(rueckfragen, fakten)

    assert {f.feld for f in verbleibend} == {"asset.pv.kwp", "asset.continuous_loads"}
    assert set(unterdrueckt) == {"asset.heating.type", "behavior.appliance_timing"}


def test_reconcile_rueckfragen_ohne_fakten_liefert_identische_liste() -> None:
    rueckfragen = [Rueckfrage(feld="asset.heating.type", frage="?", motiviert_durch="x")]
    verbleibend, unterdrueckt = reconcile_rueckfragen(rueckfragen, InMemoryProfileFacts())

    assert verbleibend == rueckfragen
    assert unterdrueckt == []


# ---------------------------------------------------------------------------
# Fenster-Falle: kennzahl nutzt NUR signals-eigene Fenster (nie 22:00-Fenster)
# ---------------------------------------------------------------------------


def test_kennzahl_nennt_signals_eigenes_nachtfenster() -> None:
    signals = compute_signals(_niedrige_nachtgrundlast_consumption())
    guard = _guard_ohne_pv(signals)
    abgleich = reconcile_signals(signals, guard, InMemoryProfileFacts())
    dauerlast = _finde(abgleich, "dauerlast")

    assert "00:00–04:59" in dauerlast.kennzahl
    assert "22:00" not in dauerlast.kennzahl


# ---------------------------------------------------------------------------
# SSOT-Drift-Guard: PRAEZEDENZ deckt genau die 3 signal-getriebenen
# select_rueckfragen-Felder ab (behavior.appliance_timing ausgenommen — kein
# Signal-Gegenstück, "immer" gestellt).
# ---------------------------------------------------------------------------


def test_praezedenz_tabelle_deckt_select_rueckfragen_signal_felder() -> None:
    signals = compute_signals(_alle_drei_signale_likely_consumption())
    assert signals.electric_heating is Signal.LIKELY
    assert signals.pv_self_consumption is Signal.LIKELY
    assert signals.high_continuous_load is Signal.LIKELY

    fragen = select_rueckfragen(signals)
    bedingte_felder = {f.feld for f in fragen} - {"behavior.appliance_timing"}

    assert bedingte_felder == {p.fakt_feld for p in PRAEZEDENZ}
    assert set(SIGNAL_FELD_MAPPING) == {p.signal for p in PRAEZEDENZ}
