# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Ereignis-Erkennung im Lastgang (``capabilities/lastgang/ereignisse.py``).

Der Zweck des Moduls ist ein Alarm an einen Haushalt — deshalb ist die
wichtigste getestete Eigenschaft nicht die Trefferquote, sondern die **Ruhe**:
eine unauffällige Serie muss NULL Ereignisse ergeben. Der dokumentierte
Vorfall in ``tests/test_anomalie_schwelle.py`` (57,8 % der Tage als Anomalie
markiert) ist genau der Fehler, den ein Melde-Pfad nicht machen darf — dort
war es ein Label in einem Report, hier wäre es eine E-Mail.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.lastgang.ereignisse import (
    ABWESENHEIT,
    DAUERLAST_NACHT,
    NEUE_SPITZE,
    VERBRAUCH_HOCH,
    finde_ereignisse,
)

_START = date(2026, 1, 1)


def _tagesform(stunde: int) -> float:
    """kWh je Viertelstunde eines unauffälligen Haushaltstags (~4,4 kWh/Tag).

    Grundlast 120 W, Morgenspitze 7 Uhr, Abendspitze 19 Uhr — die Form, die
    ein Wohnungshaushalt ohne Elektroheizung typischerweise zeigt."""
    grund = 0.03  # 120 W
    if stunde == 7:
        return grund + 0.15
    if stunde in (18, 19, 20):
        return grund + 0.12
    if 9 <= stunde <= 16:
        return grund + 0.02
    return grund


def _serie(
    tage: int,
    *,
    start: date = _START,
    eingriff=None,
) -> list[tuple[datetime, float]]:
    """Baut eine Q15-Serie über ``tage`` Tage.

    ``eingriff(tag_index, ts, wert) -> wert`` darf einzelne Werte verändern —
    so werden die Ereignisse in eine sonst unauffällige Serie eingebaut.
    """
    punkte: list[tuple[datetime, float]] = []
    for i in range(tage):
        tag = start + timedelta(days=i)
        for slot in range(96):
            ts = datetime(tag.year, tag.month, tag.day) + timedelta(minutes=15 * slot)
            wert = _tagesform(ts.hour)
            # Leichtes deterministisches Rauschen: ohne Streuung ist die MAD
            # null und jede Schwelle degeneriert (s. _ueber_robuster_schwelle).
            wert *= 1.0 + 0.04 * ((i * 7 + slot * 13) % 11 - 5) / 5.0
            if eingriff is not None:
                wert = eingriff(i, ts, wert)
            punkte.append((ts, round(wert, 4)))
    return punkte


def _typen(ereignisse) -> list[str]:
    return [e.typ for e in ereignisse]


# --- Ruhe ---------------------------------------------------------------------


def test_unauffaellige_serie_meldet_nichts():
    """Die Eigenschaft, an der der Melde-Pfad hängt: keine Nachricht ohne Anlass."""
    ereignisse = finde_ereignisse(_serie(90), heute=_START + timedelta(days=89))
    assert ereignisse == []


def test_zu_kurze_historie_meldet_nichts():
    """Ohne Vergleichszeitraum ist jede Schwelle geraten — dann lieber schweigen."""
    ereignisse = finde_ereignisse(_serie(10), heute=_START + timedelta(days=9))
    assert ereignisse == []


def test_tagesaufloesung_wird_abgelehnt():
    """Wie ``compute_signals``: Tageswerte tragen keine Intraday-Aussage."""
    with pytest.raises(CapabilityError):
        finde_ereignisse(_serie(90), interval_minutes=1440)


def test_leere_serie_wird_abgelehnt():
    with pytest.raises(CapabilityError):
        finde_ereignisse([])


# --- Dauerlast über Nacht -----------------------------------------------------


def test_neue_nachtlast_wird_erkannt():
    """+250 W in drei aufeinanderfolgenden Nächten, Tagesniveau sonst unverändert."""

    def eingriff(i, ts, wert):
        if 85 <= i <= 87 and ts.hour < 5:
            return wert + 0.0625  # 250 W über eine Viertelstunde
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    nacht = [e for e in ereignisse if e.typ == DAUERLAST_NACHT]
    assert len(nacht) == 1, _typen(ereignisse)
    e = nacht[0]
    assert e.von == _START + timedelta(days=85)
    assert e.bis == _START + timedelta(days=87)
    assert 200 <= e.zusatz_leistung_w <= 300
    # 250 W über 5 Nachtstunden an 3 Tagen ≈ 3,75 kWh
    assert 3.0 <= e.zusatz_kwh <= 4.5


def test_nachtlast_unter_der_mindeststaerke_wird_nicht_gemeldet():
    """+30 W ist Messrauschen und Alltag — kein Anlass für eine E-Mail."""

    def eingriff(i, ts, wert):
        if 85 <= i <= 87 and ts.hour < 5:
            return wert + 0.0075  # 30 W
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    assert [e for e in ereignisse if e.typ == DAUERLAST_NACHT] == []


# --- Abwesenheit --------------------------------------------------------------


def test_abwesenheit_wird_als_ein_zeitraum_erkannt():
    """Vier flache Tage sind EIN Ereignis, nicht vier."""

    def eingriff(i, ts, wert):
        if 84 <= i <= 87:
            return 0.03  # nur Grundlast, kein Alltagsmuster
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    abw = [e for e in ereignisse if e.typ == ABWESENHEIT]
    assert len(abw) == 1, _typen(ereignisse)
    assert abw[0].von == _START + timedelta(days=84)
    assert abw[0].bis == _START + timedelta(days=87)
    assert abw[0].tage == 4


def test_taktender_kuehlschrank_verhindert_die_abwesenheit_nicht():
    """Regression aus einer realen Serie (16.–18.07., 03.–06.08., 14./15.08.2026).

    Während der Abwesenheit taktet der Kühlschrank weiter: 52 W aus, 176 W an.
    Ein Flachheitsmaß, das die Tagesspitze gegen die Grundlast DESSELBEN Tages
    hält, misst dieses Taktverhältnis (3,1–3,4) und nicht die Anwesenheit — es
    hat alle drei Urlaubsphasen verworfen. Der Vergleich muss gegen die
    typische Tagesspitze der Vergleichstage gehen.
    """

    def eingriff(i, ts, wert):
        if 84 <= i <= 87:
            # Kühlschrank-Takt: jede vierte Viertelstunde an.
            return 0.044 if ts.minute == 0 else 0.013
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    abw = [e for e in ereignisse if e.typ == ABWESENHEIT]
    assert len(abw) == 1, _typen(ereignisse)
    assert abw[0].tage == 4


def test_abwesenheit_meldet_keine_neue_nachtlast():
    """Ohne Tagesbetrieb steigt der Nacht-Median — das ist eine Folge der
    Abwesenheit, kein neues Gerät (realer Fall 23.05.2026)."""

    def eingriff(i, ts, wert):
        if 84 <= i <= 87:
            return 0.044 if ts.minute == 0 else 0.013
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    assert DAUERLAST_NACHT not in _typen(ereignisse)


def test_einzelner_ruhiger_tag_ist_keine_abwesenheit():
    """Ein Tag außer Haus ist Alltag — erst eine Serie ist eine Nachricht wert."""

    def eingriff(i, ts, wert):
        if i == 87:
            return 0.03
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    assert [e for e in ereignisse if e.typ == ABWESENHEIT] == []


# --- Verbrauchssprung ---------------------------------------------------------


def test_verbrauchssprung_wird_erkannt():
    """Drei Tage mit rund dem Doppelten des üblichen Tagesverbrauchs."""

    def eingriff(i, ts, wert):
        if 85 <= i <= 87:
            return wert * 2.2
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    hoch = [e for e in ereignisse if e.typ == VERBRAUCH_HOCH]
    assert len(hoch) == 1, _typen(ereignisse)
    assert hoch[0].von == _START + timedelta(days=85)
    assert hoch[0].bis == _START + timedelta(days=87)
    assert hoch[0].zusatz_kwh > 5


def test_kleiner_haushalt_alarmiert_nicht_wegen_relativer_schwankung():
    """+1 kWh auf 4 kWh ist prozentual viel und in Euro nichts — kein Alarm.

    Ohne absolute Mindesthöhe wäre der Alarm bei kleinen Haushalten am
    lautesten, obwohl dort am wenigsten dahintersteckt.
    """

    def eingriff(i, ts, wert):
        if 85 <= i <= 87:
            return wert * 1.22
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    assert [e for e in ereignisse if e.typ == VERBRAUCH_HOCH] == []


# --- Neue Spitze --------------------------------------------------------------


def test_neue_leistungsspitze_wird_erkannt():
    """Eine Viertelstunde mit 5 kW, wo bisher nie mehr als ~1 kW war."""

    def eingriff(i, ts, wert):
        if i == 86 and ts.hour == 17 and ts.minute == 30:
            return 1.25  # 5 kW über eine Viertelstunde
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    spitzen = [e for e in ereignisse if e.typ == NEUE_SPITZE]
    assert len(spitzen) == 1, _typen(ereignisse)
    assert spitzen[0].von == _START + timedelta(days=86)
    assert 4.5 <= spitzen[0].peak_kw <= 5.5
    assert spitzen[0].stunden == (17,)


# --- Fenster ------------------------------------------------------------------


def test_altes_ereignis_wird_nicht_erneut_gemeldet():
    """Was vor dem Beobachtungsfenster liegt, ist Vergangenheit — es zählt zur
    Baseline, aber es wird nicht alarmiert."""

    def eingriff(i, ts, wert):
        if 20 <= i <= 23:
            return 0.03
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff),
        heute=_START + timedelta(days=89),
        fenster_tage=14,
    )
    assert ereignisse == []


def test_signatur_traegt_die_betroffenen_stunden():
    """Die Deutung braucht die Uhrzeit — eine Last um 3 Uhr bedeutet etwas
    anderes als dieselbe Last um 13 Uhr."""

    def eingriff(i, ts, wert):
        if 85 <= i <= 87 and ts.hour < 5:
            return wert + 0.0625
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    nacht = [e for e in ereignisse if e.typ == DAUERLAST_NACHT][0]
    assert nacht.stunden == (0, 1, 2, 3, 4)


def test_abwesenheits_sockel_kommt_aus_der_energie_nicht_aus_dem_median():
    """Regression: der Sockel eines leeren Haushalts wird vom taktenden
    Kühlgerät dominiert. Ein Median über taktende Werte liegt immer auf einem
    der beiden Zustände — an vier Einschaltquoten gemessen lag die frühere
    Median-Hochrechnung zwischen 27 % zu niedrig und 36 % zu hoch."""

    def eingriff(i, ts, wert):
        if 84 <= i <= 87:
            # 30 W Dauerlast + Kühlgerät, das die Hälfte der Zeit mit 88 W läuft.
            an = (ts.hour * 4 + ts.minute // 15) % 12 < 6
            return (30 + (88 if an else 26)) / 4000
        return wert

    ereignisse = finde_ereignisse(
        _serie(90, eingriff=eingriff), heute=_START + timedelta(days=89)
    )
    abw = [e for e in ereignisse if e.typ == ABWESENHEIT][0]
    # Wahre mittlere Leistung: 30 + (26+88)/2 = 87 W
    assert 84 <= abw.zusatz_leistung_w <= 91
    # Der Median läge bei 30+88 = 118 W und damit 36 % zu hoch.
    assert abw.zusatz_leistung_w < 100
