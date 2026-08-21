# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Geräte-Rückschau (``capabilities/lastgang/rueckschau.py``).

Gegenstück zu ``test_lastgang_ereignisse.py``: dort wird ein 7-Tage-Fenster
gegen eine Baseline geprüft, hier ein ganzes Jahr gegen eine Signatur, die der
Haushalt schon einmal bestätigt hat (Bens Auftrag 20.08.2026: „aus usersicht
ist mir nicht klar warum ich das beantworten sollte" — die Rückschau ist die
Antwort darauf: wer antwortet, bekommt sofort etwas zurück).

Getestet wird deshalb, was eine Rückschau ausmacht und keine bloße Wiederholung
der Alarm-Logik ist: das ROLLIERENDE (nicht feste) Ruheniveau, der Saisonfilter
gegen ``deutung.KANDIDATEN``, die Bündelung zusammenhängender Tage, die
Abdeckungs-Untergrenze und dass ohne Preis keine Euro-Zahl entsteht.
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
)
from energietools.capabilities.lastgang.rueckschau import rueckschau

_START = date(2026, 1, 1)


def _serie(
    tage: int,
    *,
    start: date = _START,
    nacht_w=lambda i: 60.0,
    tag_w=lambda i: 150.0,
    spitze=lambda i: None,  # (stunde, kw) oder None
) -> list[tuple[datetime, float]]:
    """Baut eine Q15-Serie über ``tage`` Tage aus Nacht-/Tagniveau + optionaler Spitze.

    ``nacht_w``/``tag_w``/``spitze`` sind Funktionen des Tag-Index — so lassen
    sich Sockel, die sich über das Jahr ändern (Sommer/Winter), und einzelne
    Ereignistage bauen, ohne jeden Slot von Hand zu setzen.
    """
    punkte: list[tuple[datetime, float]] = []
    for i in range(tage):
        tag = start + timedelta(days=i)
        sp = spitze(i)
        for slot in range(96):
            stunde = slot // 4
            ts = datetime(tag.year, tag.month, tag.day) + timedelta(minutes=15 * slot)
            if sp is not None and stunde == sp[0]:
                w = sp[1] * 1000
            elif stunde < 5:
                w = nacht_w(i)
            else:
                w = tag_w(i)
            # Leichtes deterministisches Rauschen, sonst ist die MAD null und
            # jede robuste Schwelle degeneriert (wie in test_lastgang_ereignisse).
            w *= 1.0 + 0.02 * ((i * 7 + slot * 13) % 11 - 5) / 5.0
            punkte.append((ts, round(w / 1000 / 4, 5)))
    return punkte


# --- Eingabe-Validierung -------------------------------------------------------


def test_leere_serie_wird_abgelehnt():
    with pytest.raises(CapabilityError):
        rueckschau([], typ=DAUERLAST_NACHT, leistung_w=200, stunden=(0, 1, 2, 3, 4))


def test_tagesaufloesung_wird_abgelehnt():
    with pytest.raises(CapabilityError):
        rueckschau(
            _serie(90),
            typ=DAUERLAST_NACHT,
            leistung_w=200,
            stunden=(0, 1, 2, 3, 4),
            interval_minutes=1440,
        )


def test_unbekannte_ereignisart_wird_abgelehnt():
    with pytest.raises(CapabilityError):
        rueckschau(_serie(90), typ="staubsauger", leistung_w=200, stunden=(0,))


# --- Abdeckung ------------------------------------------------------------------


def test_zu_duenne_abdeckung_gibt_none():
    """Unter 60 Tagen mit Daten ist jede Jahresaussage geraten (L30) — lieber None."""
    serie = _serie(40)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=39),
    )
    assert ergebnis is None


# --- Rollierendes Fenster statt Kalenderjahr (Review 20.08.2026) ----------------


def test_fenster_rollt_ueber_den_jahreswechsel_statt_auf_none_zu_fallen():
    """Befund 2 (Nachprüfung 2, Review 20.08.2026): ein Kalenderjahr-Fenster
    (``von = 1.1.``) fiel jedes Jahr am 1.1. auf null — an Bens Serie
    gemessen lieferte ``rueckschau()`` am 20.01. ``None``, die erste
    Rückschau kam erst ab ~1.3. Das rollierende Fenster zieht die
    Vorgeschichte aus dem Vorjahr mit: am 20.01. liegen schon ~140 Tage
    Historie aus dem September davor, weit über ``MIN_ABDECKUNG_TAGE``."""
    start = date(2025, 9, 1)
    heute = date(2026, 1, 20)
    tage_bis_heute = (heute - start).days + 1

    serie = _serie(tage_bis_heute, start=start)
    ergebnis = rueckschau(serie, typ=ABWESENHEIT, leistung_w=0, stunden=(), heute=heute)

    assert ergebnis is not None  # nicht mehr None nur weil das Jahr neu ist
    assert ergebnis.tage_mit_daten >= tage_bis_heute - 1
    assert ergebnis.von < date(2026, 1, 1)  # das Fenster reicht ins Vorjahr zurück


def test_default_ist_rollierend_explizites_von_zielt_auf_ein_bestimmtes_fenster():
    """Ohne ``von`` ist das Fenster rollierend (die letzten 365 Tage vor
    ``heute``) und verliert deshalb ein Ereignis, das weiter zurückliegt —
    mit explizitem ``von`` lässt sich trotzdem ein bestimmtes Fenster (z.B.
    ein einzelnes Kalenderjahr) gezielt auswerten, ohne dass die
    Vorgeschichte fehlt (Review 20.08.2026, Nachprüfung 2: die Kalibrierung
    an Bens Serie braucht genau dieses gezielte Fenster)."""
    start = date(2025, 1, 1)
    abwesend_tage = set(range(20, 25))  # Ende Januar 2025

    def tag_w(i):
        return 40.0 if i in abwesend_tage else 150.0

    def spitze(i):
        return None if i in abwesend_tage else (18, 1.2)

    serie = _serie(730, start=start, tag_w=tag_w, spitze=spitze)
    heute = start + timedelta(days=729)  # Ende 2026

    rollierend = rueckschau(serie, typ=ABWESENHEIT, leistung_w=0, stunden=(), heute=heute)
    assert rollierend is not None
    assert rollierend.tage_gesamt == 0  # das Ereignis liegt > 365 Tage zurück

    gezielt = rueckschau(
        serie,
        typ=ABWESENHEIT,
        leistung_w=0,
        stunden=(),
        von=start,
        heute=start + timedelta(days=364),
    )
    assert gezielt is not None
    assert gezielt.tage_gesamt == 5  # dasselbe Fenster, gezielt angesteuert


# --- dauerlast_nacht --------------------------------------------------------------


def test_dauerlast_nacht_findet_vorkommen():
    """Drei Nächte mit +200 W über dem (konstanten) Ruheniveau werden zu einem Vorkommen."""

    def nacht(i):
        return 260.0 if 120 <= i <= 122 else 60.0

    serie = _serie(200, nacht_w=nacht)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=199),
    )
    assert ergebnis is not None
    assert len(ergebnis.vorkommen) == 1, ergebnis.vorkommen
    v = ergebnis.vorkommen[0]
    assert v.tage == 3
    assert v.von == _START + timedelta(days=120)
    assert v.bis == _START + timedelta(days=122)
    # 200 W Zusatzlast × 5 Nachtstunden × 3 Nächte = 3,0 kWh
    assert 2.7 <= v.kwh <= 3.3
    assert ergebnis.tage_gesamt == 3
    assert ergebnis.verworfen_saison == 0
    assert ergebnis.rechenweg  # jede Zahl mit ihrer Herkunft


def test_zusammenhaengende_tage_werden_zu_einem_vorkommen():
    """Ein 3-Tage-Block und ein isolierter Tag bleiben ZWEI Vorkommen, nicht eines."""

    def nacht(i):
        if 120 <= i <= 122:
            return 260.0
        if i == 160:
            return 260.0
        return 60.0

    serie = _serie(200, nacht_w=nacht)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=199),
    )
    assert ergebnis is not None
    assert len(ergebnis.vorkommen) == 2, ergebnis.vorkommen
    tage_je_vorkommen = sorted(v.tage for v in ergebnis.vorkommen)
    assert tage_je_vorkommen == [1, 3]
    assert ergebnis.tage_gesamt == 4


def test_dauerlast_nacht_ohne_preis_kein_euro():
    def nacht(i):
        return 260.0 if 120 <= i <= 122 else 60.0

    serie = _serie(200, nacht_w=nacht)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=199),
    )
    assert ergebnis is not None
    assert ergebnis.eur_gesamt is None


def test_dauerlast_nacht_mit_preis_gibt_es_euro():
    def nacht(i):
        return 260.0 if 120 <= i <= 122 else 60.0

    serie = _serie(200, nacht_w=nacht)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=199),
        arbeitspreis_ct_kwh=25.0,
    )
    assert ergebnis is not None
    assert ergebnis.eur_gesamt is not None
    # kwh_gesamt × 25 ct/kWh / 100 — Rechenweg entsteht im Modul, nicht hier.
    erwartet = round(ergebnis.kwh_gesamt * 25.0 / 100, 2)
    assert ergebnis.eur_gesamt == erwartet


# --- Saisonfilter -----------------------------------------------------------------


def test_saisonfilter_verwirft_treffer_ausserhalb_der_kandidaten_monate():
    """label='klimageraet' hat ein Sommer-Fenster in deutung.KANDIDATEN — Winter-
    Treffer fallen raus und werden gezählt, nicht stillschweigend behalten."""

    def nacht(i):
        tag = _START + timedelta(days=i)
        if tag.month == 7 and 10 <= tag.day <= 12:
            return 260.0
        if tag.month == 2 and 10 <= tag.day <= 11:
            return 260.0
        return 60.0

    serie = _serie(250, nacht_w=nacht)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        label="klimageraet",
        heute=_START + timedelta(days=249),
    )
    assert ergebnis is not None
    assert ergebnis.verworfen_saison == 2
    assert len(ergebnis.vorkommen) == 1
    assert ergebnis.vorkommen[0].tage == 3
    assert ergebnis.vorkommen[0].von.month == 7


def test_saisonfilter_greift_nicht_ohne_bekanntes_label():
    """Kein/unbekanntes Label -> kein Saisonfenster -> nichts wird verworfen."""

    def nacht(i):
        tag = _START + timedelta(days=i)
        if tag.month == 2 and 10 <= tag.day <= 11:
            return 260.0
        return 60.0

    serie = _serie(250, nacht_w=nacht)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=249),
    )
    assert ergebnis is not None
    assert ergebnis.verworfen_saison == 0
    assert len(ergebnis.vorkommen) == 1


# --- Rollierendes Ruheniveau --------------------------------------------------


def test_rollierendes_ruheniveau_schlaegt_festen_jahreswert():
    """Sommer/Winter-Sockel: ein dauerhafter Sprung im Ruheniveau selbst ist KEIN
    Ereignis (die rollierende Baseline holt ihn binnen 30 Tagen ein) — nur ein
    ECHTES Zusatzgerät oberhalb des jeweils aktuellen Ruheniveaus wird gemeldet.
    Ein fester Jahreswert (z.B. globaler p20) läge zwischen 60 W und 140 W und
    würde entweder die ganze zweite Jahreshälfte oder das injizierte Gerät falsch
    behandeln — die rollierende Schwelle tut keines von beidem.
    """

    def nacht(i):
        sockel = 60.0 if i < 100 else 140.0
        if 150 <= i <= 152:
            sockel += 120.0
        return sockel

    serie = _serie(200, nacht_w=nacht)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=199),
    )
    assert ergebnis is not None
    # Nur der injizierte Block, keine Treffer aus dem reinen Sockel-Sprung.
    assert len(ergebnis.vorkommen) == 1, ergebnis.vorkommen
    v = ergebnis.vorkommen[0]
    assert v.von == _START + timedelta(days=150)
    assert v.tage == 3


# --- 24-h-Sockel: Tagesbetrieb (NACHTRAG 1, Bens Einwand "wir haben klima auch
# untertags betrieben") -----------------------------------------------------------

# Die einfache Nacht/Tag-Aufteilung von ``_serie()`` reicht für den 24-h-Sockel
# nicht: bei genau 5 Nachtstunden (20 von 96 Q15-Slots) liegt p20 EXAKT an der
# Grenze zwischen dem Nacht- und dem Tagblock (idx=round(0.2*95)=19). Mit nur
# ZWEI Tagesniveaus kippt dadurch, welcher Block als "der niedrige" gilt,
# sobald die Nacht über den Tag steigt — echte Serien mit kontinuierlicher
# Streuung haben dieses Kippen nicht. Der Helfer hier bildet deshalb DREI
# Bereiche ab (Nacht, ruhige Tagesstunden, aktive Tagesstunden), wie ein
# echter Tagesverlauf: ein Gerät, das durchgehend läuft, hebt auch die
# RUHIGEN Tagesstunden an — allgemeine Betriebsamkeit in den AKTIVEN Stunden
# (Kochen, Wäsche) dagegen nicht, weil p20 als unterstes Quantil von den
# oberen 76 % gar nicht berührt wird (genau die Robustheit, die NACHTRAG 1
# von p20 statt eines Mittelwerts verlangt).
_RUHIGE_TAGESSTUNDEN = tuple(range(5, 11))  # 6 h = 24 Q15-Slots


def _serie_tagesform(
    tage: int,
    *,
    start: date = _START,
    nacht_w=lambda i: 60.0,
    ruhig_w=lambda i: 60.0,
    aktiv_w=lambda i: 400.0,
) -> list[tuple[datetime, float]]:
    punkte: list[tuple[datetime, float]] = []
    for i in range(tage):
        tag = start + timedelta(days=i)
        for slot in range(96):
            stunde = slot // 4
            ts = datetime(tag.year, tag.month, tag.day) + timedelta(minutes=15 * slot)
            if stunde < 5:
                w = nacht_w(i)
            elif stunde in _RUHIGE_TAGESSTUNDEN:
                w = ruhig_w(i)
            else:
                w = aktiv_w(i)
            punkte.append((ts, round(w / 1000 / 4, 6)))
    return punkte


def test_24h_sockel_erkennt_durchgehenden_betrieb():
    """Läuft das Gerät durchgehend (Nacht UND die ruhigen Tagesstunden heben
    sich gemeinsam ab), wird das Vorkommen `durchgehend` markiert und über 24
    statt 5 Stunden gerechnet. Nachgerechnet: Sockel-Zusatz 200 W (60 → 260 W,
    identisch mit der Nachtzusatzlast, weil hier der GESAMTE Tag gleichmäßig
    um 200 W steigt) × 24 h × 3 Tage / 1000 = 14,4 kWh — exakt das 4,8-fache
    der reinen Nachtrechnung (200 W × 5 h × 3 / 1000 = 3,0 kWh)."""

    def nacht(i):
        return 260.0 if 150 <= i <= 152 else 60.0

    def ruhig(i):
        return 260.0 if 150 <= i <= 152 else 60.0

    serie = _serie_tagesform(200, nacht_w=nacht, ruhig_w=ruhig)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=199),
    )
    assert ergebnis is not None
    assert len(ergebnis.vorkommen) == 1, ergebnis.vorkommen
    v = ergebnis.vorkommen[0]
    assert v.tage == 3
    assert v.durchgehend is True
    assert v.kwh == pytest.approx(14.4, abs=0.05)
    assert ergebnis.tage_durchgehend == 3
    assert ergebnis.tage_nur_signaturstunden == 0
    assert any("rund um die Uhr" in z for z in ergebnis.rechenweg)


def test_reine_nachtlast_bleibt_nur_signaturstunden():
    """Läuft das Gerät NUR nachts (die ruhigen Tagesstunden bleiben unverändert
    bei 60 W), bleibt `durchgehend` False und die kWh-Rechnung bei den
    Signaturstunden — wie vor NACHTRAG 1. Der 24-h-Sockel selbst bleibt bei
    60 W (die ruhigen Tagesstunden allein tragen schon p20, unabhängig davon,
    wie hoch die Nacht steigt), Zusatz = 0 < 100-W-Schwelle."""

    def nacht(i):
        return 260.0 if 120 <= i <= 122 else 60.0

    serie = _serie_tagesform(200, nacht_w=nacht)  # ruhig_w/aktiv_w unverändert
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=199),
    )
    assert ergebnis is not None
    assert len(ergebnis.vorkommen) == 1, ergebnis.vorkommen
    v = ergebnis.vorkommen[0]
    assert v.durchgehend is False
    assert v.kwh == pytest.approx(3.0, abs=0.02)  # 200 W × 5 h × 3 Nächte / 1000
    assert ergebnis.tage_durchgehend == 0
    assert ergebnis.tage_nur_signaturstunden == 3
    assert any(
        "24-h-Sockel an keinem dieser Tage über der Schwelle" in z for z in ergebnis.rechenweg
    )


def test_gemischtes_vorkommen_wird_an_der_flag_aenderung_gesplittet():
    """Ein durchgehender Block direkt gefolgt von einem Nur-Nacht-Block bleibt
    KALENDARISCH zusammenhängend, aber ist zwei Vorkommen — sonst würde die
    kWh-Summe zwei unterschiedliche Rechnungen vermischen."""

    def nacht(i):
        return 260.0 if 150 <= i <= 155 else 60.0

    def ruhig(i):
        return 260.0 if 150 <= i <= 152 else 60.0  # nur die ersten 3 Tage durchgehend

    serie = _serie_tagesform(200, nacht_w=nacht, ruhig_w=ruhig)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=199),
    )
    assert ergebnis is not None
    assert len(ergebnis.vorkommen) == 2, ergebnis.vorkommen
    erst, zweit = sorted(ergebnis.vorkommen, key=lambda v: v.von)
    assert erst.tage == 3 and erst.durchgehend is True
    assert zweit.tage == 3 and zweit.durchgehend is False
    assert ergebnis.tage_durchgehend == 3
    assert ergebnis.tage_nur_signaturstunden == 3


def test_rausch_kontrolle_betriebsamer_tag_ohne_dauerlast_wird_nicht_durchgehend():
    """PFLICHT-TEST (Spec NACHTRAG 1, Rausch-Kontrolle): eine synthetische Serie
    mit betriebsamen Tagen OHNE echte Dauerlast darf KEINE durchgehenden Tage
    ergeben. Die Nächte reißen hier real die Signaturschwelle (ein echtes
    Nachtgerät, +200 W), UND die ruhigen Tagesstunden sind selbst etwas
    unruhiger als sonst (+40 W — genau die Größenordnung, die die Spec als
    Rauschband nennt, 20–60 W), UND die aktiven Tagesstunden sind deutlich
    betriebsamer (+50 W, Kochen/Waschen). Der 24-h-Sockel bleibt trotzdem weit
    unter der 100-W-Schwelle (Zusatz = 40 W), weil p20 als unterstes Quantil
    von den AKTIVEN Stunden gar nicht berührt wird — genau die Robustheit,
    die NACHTRAG 1 von p20 statt einem Mittelwert verlangt."""

    def nacht(i):
        return 260.0 if 170 <= i <= 172 else 60.0

    def ruhig(i):
        return 100.0 if 170 <= i <= 172 else 60.0  # Rauschen, kein Gerät

    def aktiv(i):
        return 450.0 if 170 <= i <= 172 else 400.0  # betriebsamer, kein Gerät

    serie = _serie_tagesform(200, nacht_w=nacht, ruhig_w=ruhig, aktiv_w=aktiv)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=199),
    )
    assert ergebnis is not None
    assert len(ergebnis.vorkommen) == 1, ergebnis.vorkommen
    v = ergebnis.vorkommen[0]
    assert v.durchgehend is False
    assert ergebnis.tage_durchgehend == 0
    # kein einziger Tag "faellt" fälschlich in den Durchgehend-Zweig:
    assert all(not vk.durchgehend for vk in ergebnis.vorkommen)


# --- Abwesenheit ----------------------------------------------------------------


def test_abwesenheit_ueber_ein_jahr():
    abwesend_tage = set(range(100, 105))

    def tag_w(i):
        return 40.0 if i in abwesend_tage else 150.0

    def spitze(i):
        return None if i in abwesend_tage else (18, 1.2)

    serie = _serie(220, tag_w=tag_w, spitze=spitze)
    ergebnis = rueckschau(
        serie,
        typ=ABWESENHEIT,
        leistung_w=0,
        stunden=(),
        heute=_START + timedelta(days=219),
    )
    assert ergebnis is not None
    assert len(ergebnis.vorkommen) == 1, ergebnis.vorkommen
    v = ergebnis.vorkommen[0]
    assert v.tage == 5
    assert ergebnis.tage_gesamt == 5
    assert ergebnis.kwh_gesamt > 0
    assert ergebnis.kwh_jahr is not None
    assert ergebnis.grundlast_anteil is not None
    assert 0 < ergebnis.grundlast_anteil < 1


def test_abwesenheit_ohne_preis_kein_euro_aber_kwh_jahr_bleibt():
    abwesend_tage = set(range(100, 105))

    def tag_w(i):
        return 40.0 if i in abwesend_tage else 150.0

    def spitze(i):
        return None if i in abwesend_tage else (18, 1.2)

    serie = _serie(220, tag_w=tag_w, spitze=spitze)
    ergebnis = rueckschau(
        serie,
        typ=ABWESENHEIT,
        leistung_w=0,
        stunden=(),
        heute=_START + timedelta(days=219),
    )
    assert ergebnis is not None
    assert ergebnis.eur_gesamt is None
    assert ergebnis.eur_jahr is None
    assert ergebnis.kwh_jahr is not None


def test_einzelner_ruhiger_tag_zaehlt_als_eigenes_vorkommen():
    """Anders als beim Alarm: ein isolierter Tag ist hier kein Rauschen, das man
    verwirft, sondern ein gültiger Messpunkt für die Jahressumme — der Alarm
    verwirft ihn nur, weil eine einzelne Mail für einen Tag keine Nachricht
    wert ist. Nachgemessen an Bens Serie: ohne diesen Unterschied wären drei
    reale Abwesenheitstage (u.a. 19.05.) aus der Jahressumme gefallen und
    25 Tage/68,5 kWh wären zu 22 Tagen/60,8 kWh geworden."""
    abwesend_tage = {150}

    def tag_w(i):
        return 40.0 if i in abwesend_tage else 150.0

    def spitze(i):
        return None if i in abwesend_tage else (18, 1.2)

    serie = _serie(220, tag_w=tag_w, spitze=spitze)
    ergebnis = rueckschau(
        serie,
        typ=ABWESENHEIT,
        leistung_w=0,
        stunden=(),
        heute=_START + timedelta(days=219),
    )
    assert ergebnis is not None
    assert len(ergebnis.vorkommen) == 1
    assert ergebnis.vorkommen[0].tage == 1
    assert ergebnis.vorkommen[0].von == _START + timedelta(days=150)
    assert ergebnis.tage_gesamt == 1


# --- verbrauch_hoch ---------------------------------------------------------------


def test_verbrauch_hoch_findet_tage_ueber_der_robusten_grenze():
    hoch_tage = {150, 151}

    def tag_w(i):
        return 450.0 if i in hoch_tage else 150.0

    def spitze(i):
        return (18, 4.0) if i in hoch_tage else (18, 1.2)

    serie = _serie(220, tag_w=tag_w, spitze=spitze)
    ergebnis = rueckschau(
        serie,
        typ=VERBRAUCH_HOCH,
        leistung_w=0,
        stunden=(),
        heute=_START + timedelta(days=219),
        arbeitspreis_ct_kwh=25.0,
    )
    assert ergebnis is not None
    assert ergebnis.tage_gesamt == 2
    assert ergebnis.kwh_gesamt > 0
    assert ergebnis.eur_gesamt == round(ergebnis.kwh_gesamt * 25.0 / 100, 2)


# --- neue_spitze -------------------------------------------------------------------


# --- Jahres-Hochrechnung: Feldname + eigene Schwelle (Review 20.08.2026) ---------


def test_grundlast_anteil_ist_richtig_benannt_und_bezogen():
    """`grundlast_anteil` (vormals `anteil_am_verbrauch`) ist der Anteil, den
    die HOCHGERECHNETE GRUNDLAST am hochgerechneten Jahresverbrauch hat —
    NICHT der Anteil, den die Abwesenheitstage am gemessenen Fensterverbrauch
    haben (das wäre eine andere, viel kleinere Zahl). Nachgerechnet an Bens
    Serie (Review 20.08.2026): kwh_jahr/anteil muss den hochgerechneten
    Jahresverbrauch ergeben (mittlerer Tagesverbrauch × 365), nicht den
    gemessenen Fensterverbrauch."""
    abwesend_tage = set(range(100, 105))

    def tag_w(i):
        return 40.0 if i in abwesend_tage else 150.0

    def spitze(i):
        return None if i in abwesend_tage else (18, 1.2)

    serie = _serie(220, tag_w=tag_w, spitze=spitze)
    ergebnis = rueckschau(
        serie,
        typ=ABWESENHEIT,
        leistung_w=0,
        stunden=(),
        heute=_START + timedelta(days=219),
    )
    assert ergebnis is not None
    assert hasattr(ergebnis, "grundlast_anteil")
    assert ergebnis.grundlast_anteil is not None
    hochgerechneter_jahresverbrauch = ergebnis.kwh_jahr / ergebnis.grundlast_anteil
    # Der TATSÄCHLICHE Anteil, den die 5 Abwesenheitstage am GEMESSENEN
    # Fensterverbrauch haben, ist eine ganz andere, viel kleinere Zahl — würde
    # `grundlast_anteil` diese meinen (der Fehler vor dem Review), läge er
    # nahe daran. Er tut es nicht: die Grundlast trägt einen Vielfachen davon.
    tatsaechlicher_anteil_am_fenster = ergebnis.kwh_gesamt / (
        hochgerechneter_jahresverbrauch * 220 / 365
    )
    assert ergebnis.grundlast_anteil > tatsaechlicher_anteil_am_fenster * 3
    # Und die Rechenweg-Zeile nennt jetzt explizit "Grundlast", nicht mehr
    # den irreführenden "Anteil am Verbrauch des Fensters".
    assert any("Grundlast-Anteil am hochgerechneten Jahresverbrauch" in z for z in ergebnis.rechenweg)


def test_jahreshochrechnung_erst_ab_160_tagen_abdeckung():
    """Sweep über Bens eigene Serie (Review 20.08.2026, Nachprüfung 2): bei
    120 Tagen Abdeckung liegt der Fehler der Jahres-Hochrechnung 2026 noch bei
    +16,4 % (die alte Schwelle 120 hielt nur an 2025, nicht an 2026). Erst ab
    ~165 Tagen liegt er in BEIDEN geprüften Haushaltsjahren durchgehend unter
    7 % — die Schwelle ist deshalb 160, nicht 120. Unterhalb 160 Tagen darf
    `kwh_jahr` nicht entstehen, die reine Vorkommens-Zählung
    (`tage_gesamt`/`kwh_gesamt`) bleibt davon unberührt und ab 60 Tagen
    erhalten (L30)."""
    abwesend_tage = {10, 11, 12}

    def tag_w(i):
        return 40.0 if i in abwesend_tage else 150.0

    def spitze(i):
        return None if i in abwesend_tage else (18, 1.2)

    knapp_darunter = _serie(159, tag_w=tag_w, spitze=spitze)
    unter_schwelle = rueckschau(
        knapp_darunter,
        typ=ABWESENHEIT,
        leistung_w=0,
        stunden=(),
        heute=_START + timedelta(days=158),
    )
    assert unter_schwelle is not None  # über der 60-Tage-Existenzschwelle
    assert unter_schwelle.tage_gesamt == 3  # Vorkommens-Zählung bleibt erhalten
    assert unter_schwelle.kwh_jahr is None  # aber unter 160 Tagen keine Jahreszahl
    assert unter_schwelle.eur_jahr is None
    assert unter_schwelle.grundlast_anteil is None

    genau_darauf = _serie(160, tag_w=tag_w, spitze=spitze)
    ab_schwelle = rueckschau(
        genau_darauf,
        typ=ABWESENHEIT,
        leistung_w=0,
        stunden=(),
        heute=_START + timedelta(days=159),
    )
    assert ab_schwelle is not None
    assert ab_schwelle.kwh_jahr is not None  # ab 160 Tagen darf sie entstehen
    assert ab_schwelle.grundlast_anteil is not None


# --- Blindtage am Fensterkopf (rollierendes Ruheniveau) -------------------------


def test_blindtage_am_fensterkopf_werden_von_tage_mit_daten_abgezogen():
    """Die ersten `ROLLIEREND_MIN_WERTE`-1=9 Tage nach Fensterbeginn haben zu
    wenige Vortage für das rollierende p20-Ruheniveau und werden bei
    `dauerlast_nacht` still übersprungen (kein Treffer möglich, auch wenn
    dort real eine Dauerlast lief). `tage_mit_daten` muss das ausweisen,
    statt volle Abdeckung zu behaupten (Review 20.08.2026)."""

    def nacht(i):
        # Eine echte 8-Tage-Dauerlast GENAU am Fensterkopf — dort, wo das
        # rollierende Ruheniveau noch keine 10 Vortage hat.
        return 260.0 if i <= 7 else 60.0

    serie = _serie(200, nacht_w=nacht)
    ergebnis = rueckschau(
        serie,
        typ=DAUERLAST_NACHT,
        leistung_w=200,
        stunden=(0, 1, 2, 3, 4),
        heute=_START + timedelta(days=199),
    )
    assert ergebnis is not None
    # Die injizierte Dauerlast verschwindet komplett (unbestimmbares Ruheniveau).
    assert ergebnis.vorkommen == ()
    assert ergebnis.tage_gesamt == 0
    # 200 volle Tage im Fenster, 10 davon (Index 0..9) ohne genug Vortage.
    assert ergebnis.tage_mit_daten == 190


def test_neue_spitze_hat_keine_euro_summe():
    """Eine Spitze ist ein Leistungswert, kein Verbrauch — auch mit Preis keine €."""

    def spitze(i):
        return (17, 4.0) if i == 150 else (18, 1.2)

    serie = _serie(220, spitze=spitze)
    ergebnis = rueckschau(
        serie,
        typ=NEUE_SPITZE,
        leistung_w=4000,
        stunden=(17,),
        heute=_START + timedelta(days=219),
        arbeitspreis_ct_kwh=25.0,
    )
    assert ergebnis is not None
    assert ergebnis.tage_gesamt == 1
    assert ergebnis.vorkommen[0].von == _START + timedelta(days=150)
    assert ergebnis.eur_gesamt is None
    assert ergebnis.eur_jahr is None
