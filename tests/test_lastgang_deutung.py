# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Ereignis-Deutung (``capabilities/lastgang/deutung.py``).

Die Deutung darf nichts behaupten, was sie nicht belegen kann. Getestet wird
deshalb vor allem, WANN sie schweigt bzw. fragt statt zu erklären, und dass
eine einmal gegebene Antwort beim nächsten gleichartigen Ereignis wirkt.
"""

from __future__ import annotations

from datetime import date

import pytest

from energietools.capabilities.lastgang.deutung import (
    FruehereAntwort,
    deute,
)
from energietools.capabilities.lastgang.ereignisse import (
    ABWESENHEIT,
    DAUERLAST_NACHT,
    NEUE_SPITZE,
    VERBRAUCH_HOCH,
    Ereignis,
)
from energietools.capabilities.profile import FaktWert, InMemoryProfileFacts


def _nachtlast(w: int = 180, tage: int = 1, von: date = date(2026, 8, 8)) -> Ereignis:
    return Ereignis(
        typ=DAUERLAST_NACHT,
        von=von,
        bis=von,
        tage=tage,
        stunden=(0, 1, 2, 3, 4),
        zusatz_leistung_w=w,
        zusatz_kwh=round(w / 1000 * 5 * tage, 2),
        kwh_tag=5.6,
        baseline_kwh_tag=4.84,
        staerke=20.2,
    )


# --- Fragen statt behaupten ---------------------------------------------------


def test_unbekanntes_ereignis_ergibt_eine_frage_mit_optionen():
    d = deute(_nachtlast())
    assert d.erklaerung is None
    assert d.frage
    assert len(d.optionen) >= 2
    # "weiß nicht" muss immer dabei sein — sonst erzwingt die Mail eine Antwort,
    # die der Haushalt nicht hat.
    assert any(o.label == "unbekannt" for o in d.optionen)


def test_optionen_passen_zur_leistung():
    """180 W nachts ist kein E-Auto, 2.300 W nachts ist kein Aquarium."""
    klein = {o.label for o in deute(_nachtlast(w=180)).optionen}
    gross = {o.label for o in deute(_nachtlast(w=2300, tage=1)).optionen}
    assert "kuehlgeraet" in klein
    assert "eauto" not in klein
    assert "eauto" in gross


def test_jahreszeit_schlaegt_sich_in_den_optionen_nieder():
    sommer = {o.label for o in deute(_nachtlast(von=date(2026, 7, 20))).optionen}
    winter = {o.label for o in deute(_nachtlast(von=date(2026, 1, 20))).optionen}
    assert "klimageraet" in sommer
    assert "klimageraet" not in winter
    assert "heizgeraet" in winter


# --- Wissen schlägt Raten -----------------------------------------------------


def test_bekannter_profil_fakt_erklaert_statt_zu_fragen():
    profil = InMemoryProfileFacts(
        [FaktWert(feld="asset.continuous_loads", wert="Klimagerät im Schlafzimmer")]
    )
    d = deute(_nachtlast(von=date(2026, 7, 20)), profil=profil)
    assert d.erklaerung is not None
    assert "Klimagerät" in d.erklaerung
    assert d.quelle == "profil"
    assert d.frage is None


def test_fruehere_antwort_auf_aehnliches_ereignis_wird_wiederverwendet():
    """Der Kern von Bens Idee: einmal beantwortet, beim nächsten Mal gewusst."""
    frueher = [
        FruehereAntwort(
            typ=DAUERLAST_NACHT,
            label="klimageraet",
            text="Klimagerät",
            leistung_w=190,
            stunden=(0, 1, 2, 3, 4),
            beantwortet_am=date(2026, 8, 2),
        )
    ]
    d = deute(_nachtlast(w=180), gedaechtnis=frueher)
    assert d.quelle == "gedaechtnis"
    assert "Klimagerät" in (d.erklaerung or "")
    assert d.frage is None


def test_frueheres_ereignis_mit_anderer_signatur_wird_nicht_uebertragen():
    """190 W nachts erklärt keine 2.300 W nachts — sonst lernt das System
    Unsinn und behauptet ihn dann selbstbewusst."""
    frueher = [
        FruehereAntwort(
            typ=DAUERLAST_NACHT,
            label="klimageraet",
            text="Klimagerät",
            leistung_w=190,
            stunden=(0, 1, 2, 3, 4),
            beantwortet_am=date(2026, 8, 2),
        )
    ]
    d = deute(_nachtlast(w=2300), gedaechtnis=frueher)
    assert d.quelle != "gedaechtnis"
    assert d.frage


def test_frueheres_ereignis_anderer_art_wird_nicht_uebertragen():
    frueher = [
        FruehereAntwort(
            typ=VERBRAUCH_HOCH,
            label="besuch",
            text="Besuch",
            leistung_w=180,
            stunden=(0, 1, 2, 3, 4),
            beantwortet_am=date(2026, 8, 2),
        )
    ]
    assert deute(_nachtlast(w=180), gedaechtnis=frueher).quelle != "gedaechtnis"


# --- Kalender-Kontext ---------------------------------------------------------


def test_feiertag_wird_als_kontext_genannt():
    e = Ereignis(
        typ=VERBRAUCH_HOCH,
        von=date(2025, 12, 24),
        bis=date(2025, 12, 25),
        tage=2,
        stunden=(12, 16, 17, 18),
        zusatz_kwh=20.73,
        zusatz_leistung_w=2591,
        kwh_tag=15.84,
        baseline_kwh_tag=5.48,
        staerke=8.24,
    )
    d = deute(e)
    assert any("Weihnacht" in k for k in d.kontext)


def test_wochenende_wird_als_kontext_genannt():
    e = Ereignis(
        typ=VERBRAUCH_HOCH,
        von=date(2026, 6, 27),  # Samstag
        bis=date(2026, 6, 27),
        tage=1,
        stunden=(10, 14),
        zusatz_kwh=5.33,
        zusatz_leistung_w=2665,
        kwh_tag=10.69,
        baseline_kwh_tag=5.36,
        staerke=3.03,
    )
    assert any("Wochenende" in k for k in deute(e).kontext)


# --- Abwesenheit --------------------------------------------------------------


def test_abwesenheit_fragt_nicht_nach_einem_geraet():
    """Bei Abwesenheit ist die interessante Zahl der Standby-Verbrauch, nicht
    die Frage nach einem Gerät."""
    e = Ereignis(
        typ=ABWESENHEIT,
        von=date(2026, 8, 4),
        bis=date(2026, 8, 6),
        tage=3,
        stunden=(),
        zusatz_leistung_w=112,
        kwh_tag=2.69,
        baseline_kwh_tag=4.84,
        staerke=1.23,
    )
    d = deute(e, arbeitspreis_ct_kwh=25.0)
    assert d.hochrechnung_kwh_jahr is not None
    assert d.hochrechnung_eur_jahr is not None
    # 2,69 kWh am Tag × 365 = 982 kWh/Jahr — hochgerechnet wird die gemessene
    # Energie, nicht eine Leistung (die bei taktenden Geräten nicht konstant ist).
    assert d.hochrechnung_kwh_jahr == pytest.approx(2.69 * 365, abs=1.0)


# --- Kosten -------------------------------------------------------------------


def test_kosten_nur_mit_arbeitspreis():
    """Ohne Preis keine Euro-Zahl — geraten wird hier nichts."""
    assert deute(_nachtlast()).kosten_eur is None
    d = deute(_nachtlast(w=200, tage=3), arbeitspreis_ct_kwh=25.0)
    # 200 W × 5 h × 3 Tage = 3 kWh × 0,25 € = 0,75 €
    assert d.kosten_eur == pytest.approx(0.75, abs=0.02)


def test_neue_spitze_wird_gedeutet():
    e = Ereignis(
        typ=NEUE_SPITZE,
        von=date(2026, 3, 3),
        bis=date(2026, 3, 3),
        tage=1,
        stunden=(18,),
        peak_kw=7.4,
        baseline_peak_kw=3.1,
        kwh_tag=9.0,
        baseline_kwh_tag=5.4,
        staerke=2.39,
    )
    d = deute(e)
    assert d.frage
    assert {o.label for o in d.optionen} & {"herd", "durchlauferhitzer", "wallbox"}


def test_feiertag_steht_bei_den_optionen_vorn():
    """Am 24. Dezember ist der Feiertag die naheliegendste Erklärung — und der
    Kalender weiß das, ohne zu fragen."""
    e = Ereignis(
        typ=VERBRAUCH_HOCH,
        von=date(2025, 12, 24),
        bis=date(2025, 12, 25),
        tage=2,
        stunden=tuple(range(24)),
        zusatz_kwh=20.73,
        zusatz_leistung_w=431,
        kwh_tag=15.84,
        baseline_kwh_tag=5.48,
        staerke=8.24,
    )
    optionen = deute(e).optionen
    assert optionen[0].label == "feiertag"


def test_feiertagsoption_erscheint_nicht_an_werktagen():
    e = Ereignis(
        typ=VERBRAUCH_HOCH,
        von=date(2026, 1, 21),  # Mittwoch, kein Feiertag
        bis=date(2026, 1, 21),
        tage=1,
        stunden=tuple(range(24)),
        zusatz_kwh=6.3,
        zusatz_leistung_w=262,
        kwh_tag=12.68,
        baseline_kwh_tag=6.35,
        staerke=3.2,
    )
    assert "feiertag" not in {o.label for o in deute(e).optionen}


def test_nicht_elektrische_heizung_schliesst_die_waermepumpe_aus():
    """Wer laut Profil mit Fernwärme heizt, bekommt keine Wärmepumpe
    angeboten — der Heizlüfter bleibt, den kann auch dieser Haushalt haben."""
    e = Ereignis(
        typ=VERBRAUCH_HOCH,
        von=date(2026, 1, 21),
        bis=date(2026, 1, 21),
        tage=1,
        stunden=(11, 12, 13, 14),
        zusatz_kwh=4.1,
        zusatz_leistung_w=1025,
        kwh_tag=9.4,
        baseline_kwh_tag=5.3,
        staerke=3.1,
    )
    profil = InMemoryProfileFacts(
        [FaktWert(feld="asset.heating.type", wert="fernwaerme")]
    )
    labels = {o.label for o in deute(e, profil=profil).optionen}
    assert "waermepumpe" not in labels
    assert "heizgeraet" in labels
