# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Kühl-/Heizgradtag-Regression (``capabilities/lastgang/temperatur.py``).

Nachtrag 2 zur Rückschau-Spec (Bens Einwand 20.08.2026): eine Tages-Suche ohne
Temperatur trennt nicht (Sommer 22 Treffer, Winter-Gegenprobe 27 Treffer — MEHR
als im Sommer). Was trägt, ist eine Kühlgradtag-Regression nach IPMVP Option C:

    Tagesverbrauch = Grundverbrauch + a · max(0, T_mittel − T_basis)

Getestet wird deshalb, was diese Regression von einer naiven Korrelation
unterscheidet: die FESTE Basistemperatur (kein Overfitting auf das beste R²),
der Ausschluss von Abwesenheitstagen (dieselben Kriterien wie
``rueckschau._markiere_abwesenheit``), das Signifikanz-Gate (t ≥ 3,0 UND
mindestens 15 Tage über der Basis) und die Umkehrbarkeit für Heizgradtage.
Reproduziert an Bens echter Serie (separat, nicht Teil dieser Testdatei, s.
Abschlussbericht): Grundverbrauch 4,86 kWh/Tag, a = 0,296 kWh/Grad-Tag,
t = 5,46, R² = 0,24, Band 56,0–81,2 kWh (Mai–September 2026, 95 Tage nach
Abwesenheits-Ausschluss) — exakt die Zahlen aus NACHTRAG 6 der Spec.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import pytest

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.lastgang.temperatur import (
    ALT_BASIS_OFFSET_C,
    HEIZEN,
    KUEHLEN,
    MIN_ABDECKUNG_TAGE_SAISON,
    MIN_KALENDER_ANTEIL,
    MIN_T_WERT,
    MIN_TAGE_UEBER_BASIS,
    T_BASIS_HEIZEN,
    T_BASIS_KUEHLEN,
    gradtag_regression,
)

_START = date(2026, 1, 1)


def _tag_punkte(tag: date, kwh_gesamt: float, peak_kw: float, peak_slot: int = 52):
    """Verteilt ``kwh_gesamt`` über 96 Q15-Slots: ein Slot trägt ``peak_kw``
    (als Leistung, also ``peak_kw / 4`` kWh in diesem einen Slot), der Rest
    gleichmäßig — genug, um ``_Tag.kwh`` und ``_Tag.peak_kw`` unabhängig
    voneinander zu steuern (für die Abwesenheits-Kriterien, die auf beiden
    Feldern gleichzeitig prüfen)."""
    peak_anteil = round(peak_kw / 4, 6)
    rest = round((kwh_gesamt - peak_anteil) / 95, 6)
    punkte = []
    for slot in range(96):
        ts = datetime(tag.year, tag.month, tag.day) + timedelta(minutes=15 * slot)
        wert = peak_anteil if slot == peak_slot else rest
        punkte.append((ts, wert))
    return punkte


def _serie(
    tage: int,
    kwh_tag,  # Funktion(i) -> Tagesverbrauch in kWh
    *,
    start: date = _START,
    peak_kw=lambda i: 0.6,
):
    punkte = []
    for i in range(tage):
        tag = start + timedelta(days=i)
        punkte.extend(_tag_punkte(tag, kwh_tag(i), peak_kw(i)))
    return punkte


def _rauschen(i: int) -> float:
    return 0.1 * ((i * 7) % 5 - 2) / 2.0


# --- Eingabe-Validierung -------------------------------------------------------


def test_leere_serie_wird_abgelehnt():
    with pytest.raises(CapabilityError):
        gradtag_regression([], {}, von=_START, bis=_START)


def test_tagesaufloesung_wird_abgelehnt():
    serie = _serie(30, lambda i: 5.0)
    with pytest.raises(CapabilityError):
        gradtag_regression(
            serie, {}, von=_START, bis=_START + timedelta(days=29), interval_minutes=1440
        )


def test_unbekannte_richtung_wird_abgelehnt():
    serie = _serie(30, lambda i: 5.0)
    with pytest.raises(CapabilityError):
        gradtag_regression(
            serie, {}, von=_START, bis=_START + timedelta(days=29), richtung="lueften"
        )


# --- Kühlgradtag-Regression: Kern-Ergebnis --------------------------------------

_GRUND_TRUE = 5.0
_A_TRUE = 0.3
_HEISSE_TAGE = range(120, 160)  # 40 Tage über der Basis


def _temp_kuehlen(i: int) -> float:
    # Zentrum bei T_BASIS_KUEHLEN + 3,0 °C (vor der Anhebung auf 25 °C stand
    # hier fest "24.0" = 21 + 3 — bewusst relativ zur Konstante, damit die
    # Fixture nicht erneut hinterherhinkt, falls die Basis sich nochmal
    # ändert): dieselbe Spannweite und dieselben Gradtage wie vorher, nur um
    # den Betrag der Basis-Anhebung verschoben.
    return T_BASIS_KUEHLEN + 3.0 + 0.05 * (i - 140) if i in _HEISSE_TAGE else 8.0


def _kwh_kuehlen(i: int) -> float:
    cdd = max(0.0, _temp_kuehlen(i) - T_BASIS_KUEHLEN)
    return _GRUND_TRUE + _A_TRUE * cdd + _rauschen(i)


def _baue_kuehl_serie(tage: int = 220):
    consumption = _serie(tage, _kwh_kuehlen)
    temperaturen = {_START + timedelta(days=i): _temp_kuehlen(i) for i in range(tage)}
    return consumption, temperaturen


def test_kuehlgradtag_regression_findet_grundverbrauch_und_koeffizient():
    consumption, temperaturen = _baue_kuehl_serie()
    ergebnis = gradtag_regression(
        consumption,
        temperaturen,
        von=_START,
        bis=_START + timedelta(days=219),
        richtung=KUEHLEN,
    )
    assert ergebnis is not None
    assert ergebnis.t_basis == T_BASIS_KUEHLEN
    assert ergebnis.grundverbrauch_kwh_tag == pytest.approx(_GRUND_TRUE, abs=0.3)
    assert ergebnis.a_kwh_pro_gradtag == pytest.approx(_A_TRUE, abs=0.05)
    assert ergebnis.t_wert >= MIN_T_WERT
    assert ergebnis.tage_ueber_basis == len(_HEISSE_TAGE)
    assert ergebnis.tage_mit_daten == 220
    # Band aus dem Standardfehler, nicht eine Punktzahl:
    assert ergebnis.kwh_band_von < ergebnis.kwh_band_bis
    wahre_summe = sum(
        _A_TRUE * max(0.0, _temp_kuehlen(i) - T_BASIS_KUEHLEN) for i in range(220)
    )
    assert ergebnis.kwh_band_von <= wahre_summe <= ergebnis.kwh_band_bis


def test_ohne_preis_keine_eur_zahl():
    consumption, temperaturen = _baue_kuehl_serie()
    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=219)
    )
    assert ergebnis is not None
    assert ergebnis.eur_band_von is None
    assert ergebnis.eur_band_bis is None


def test_mit_preis_eur_band_aus_kwh_band():
    consumption, temperaturen = _baue_kuehl_serie()
    ergebnis = gradtag_regression(
        consumption,
        temperaturen,
        von=_START,
        bis=_START + timedelta(days=219),
        arbeitspreis_ct_kwh=27.35,
    )
    assert ergebnis is not None
    assert ergebnis.eur_band_von == round(ergebnis.kwh_band_von * 27.35 / 100, 2)
    assert ergebnis.eur_band_bis == round(ergebnis.kwh_band_bis * 27.35 / 100, 2)


def test_rechenweg_ist_nicht_leer_und_nennt_die_basistemperatur():
    consumption, temperaturen = _baue_kuehl_serie()
    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=219)
    )
    assert ergebnis is not None
    assert ergebnis.rechenweg
    assert any("25" in zeile for zeile in ergebnis.rechenweg)


# --- Basistemperatur ist FEST, kein Overfitting (Nachtrag 6) --------------------


def test_explizite_basistemperatur_wird_uebernommen():
    consumption, temperaturen = _baue_kuehl_serie()
    ergebnis = gradtag_regression(
        consumption,
        temperaturen,
        von=_START,
        bis=_START + timedelta(days=219),
        t_basis=24.0,
    )
    assert ergebnis is not None
    assert ergebnis.t_basis == 24.0


# --- Signifikanz-Gate: t ≥ 3,0 UND ≥ 15 Tage über der Basis ---------------------


def test_zu_wenig_tage_ueber_basis_gibt_none():
    """Nur 5 heiße Tage — auch bei starkem Zusammenhang zu dünn für eine
    Jahresaussage (Spec: mindestens 15 Tage über der Basis)."""
    heisse_tage = range(120, 125)

    def temp(i):
        return 26.0 if i in heisse_tage else 8.0

    def kwh(i):
        cdd = max(0.0, temp(i) - T_BASIS_KUEHLEN)
        return _GRUND_TRUE + _A_TRUE * cdd + _rauschen(i)

    consumption = _serie(220, kwh)
    temperaturen = {_START + timedelta(days=i): temp(i) for i in range(220)}
    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=219)
    )
    assert ergebnis is None


def test_schwacher_zusammenhang_gibt_none():
    """Verbrauch hängt NICHT von der Temperatur ab (a_true=0) — auch mit
    genug heißen Tagen darf daraus keine Aussage werden (t < 3,0)."""

    def kwh(i):
        return _GRUND_TRUE + _rauschen(i) * 3  # reines Rauschen, kein CDD-Anteil

    consumption = _serie(220, kwh)
    temperaturen = {_START + timedelta(days=i): _temp_kuehlen(i) for i in range(220)}
    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=219)
    )
    assert ergebnis is None


def test_placebo_kuehlgradtage_im_winter_gibt_none():
    """Kühlgradtage im Winter: keine Tage über der Basis -> None (Spec-Placebo)."""

    def temp(i):
        return 5.0  # nie über 21 °C Basis

    consumption = _serie(220, lambda i: _GRUND_TRUE + _rauschen(i))
    temperaturen = {_START + timedelta(days=i): temp(i) for i in range(220)}
    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=219)
    )
    assert ergebnis is None


# --- Abwesenheitstage werden ausgeschlossen (dieselben Kriterien wie die Erkennung) --


def test_abwesenheitstag_verzerrt_die_regression_nicht():
    """Ein heißer Tag, an dem der Haushalt nachweislich weg war (Bens 5.8.:
    31,9 °C, nur 2,72 kWh), darf die Regression nicht nach unten ziehen."""
    consumption, temperaturen = _baue_kuehl_serie()
    abwesenheitstag = _START + timedelta(days=130)  # liegt in den heißen Tagen
    i = 130

    # Ersetzt den Tag durch einen klaren Abwesenheitstag: sehr niedriger
    # Verbrauch UND sehr niedrige Spitze (< 60 % bzw. < 40 % des Medians der
    # ±45-Tage-Umgebung, wie in ereignisse.ABWESEND_MAX_ANTEIL/PEAK_ANTEIL).
    consumption = [
        (ts, wert) for ts, wert in consumption if ts.date() != abwesenheitstag
    ]
    consumption.extend(_tag_punkte(abwesenheitstag, kwh_gesamt=1.0, peak_kw=0.1))

    ergebnis = gradtag_regression(
        consumption,
        temperaturen,
        von=_START,
        bis=_START + timedelta(days=219),
        richtung=KUEHLEN,
    )
    assert ergebnis is not None
    # Der Abwesenheitstag zählt nicht mehr zur Abdeckung.
    assert ergebnis.tage_mit_daten == 219
    # Trotz des Ausreißers bleibt der Koeffizient nahe am wahren Wert — eine
    # Regression, die den Tag NICHT ausschließt, würde ihn spürbar verzerren
    # (der Tag hat mit CDD ≈ 3–4,5 einen hohen Hebel und einen stark zu
    # niedrigen y-Wert).
    assert ergebnis.a_kwh_pro_gradtag == pytest.approx(_A_TRUE, abs=0.05)

    # Gegenprobe: dieselbe Rechnung von Hand, OHNE Ausschluss, weicht deutlich
    # stärker vom wahren Koeffizienten ab als das Ergebnis der Funktion.
    xs, ys = [], []
    for tag, temp in temperaturen.items():
        cdd = max(0.0, temp - T_BASIS_KUEHLEN)
        tagesdaten = [w for ts, w in consumption if ts.date() == tag]
        xs.append(cdd)
        ys.append(sum(tagesdaten))
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    a_naiv = sxy / sxx
    abweichung_funktion = abs(ergebnis.a_kwh_pro_gradtag - _A_TRUE)
    abweichung_naiv = abs(a_naiv - _A_TRUE)
    assert abweichung_funktion < abweichung_naiv


def test_rechenweg_benennt_gerechnete_tage_nicht_das_fenster():
    """Linse Zahlen Befund 3: „Summe der Gradtage im Fenster" war falsch
    benannt — im Fenster lagen mehr Tage als in der Regression, weil
    Abwesenheitstage still herausfielen. Die Zeile muss die GERECHNETEN Tage
    benennen und die ausgeschlossenen explizit ausweisen."""
    consumption, temperaturen = _baue_kuehl_serie()
    abwesenheitstag = _START + timedelta(days=130)
    consumption = [(ts, wert) for ts, wert in consumption if ts.date() != abwesenheitstag]
    consumption.extend(_tag_punkte(abwesenheitstag, kwh_gesamt=1.0, peak_kw=0.1))

    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=219)
    )
    assert ergebnis is not None
    summe_zeile = next(z for z in ergebnis.rechenweg if z.startswith("Summe der Gradtage"))
    # Nennt die GERECHNETEN Tage (219), nicht die Kalendertage im Fenster (220):
    assert f"an den {ergebnis.tage_mit_daten} gerechneten Tagen" in summe_zeile
    assert "im Fenster" not in summe_zeile
    # Und weist den einen ausgeschlossenen Abwesenheitstag explizit aus:
    assert "1 Tage ohne Anwesenheit sind nicht dabei" in summe_zeile


# --- Spezifikationsunsicherheit der Basistemperatur (Linse Zahlen Befund 1) -----------


def test_rechenweg_warnt_wenn_die_basiswahl_das_band_ueberholt():
    """Ben-ähnlicher Fall: schwache Reaktion zwischen 21 und 25 °C, starke ab
    25 °C (Kink). Bei Basis 21 °C vermischt die Regression beide Bereiche —
    eine 4 °C höhere Vergleichs-Basis ergibt ein Band, das NICHT mit dem
    ausgelieferten überlappt. Der Rechenweg muss das ausdrücklich sagen,
    nicht nur das schmalere Sampling-Band zeigen."""
    heisse_tage = range(100, 200)

    def temp(i):
        return 15.0 + (i - 100) * (18.0 / 99) if i in heisse_tage else 8.0

    def kwh(i):
        t = temp(i)
        grad21 = max(0.0, t - T_BASIS_KUEHLEN)
        if t <= 25.0:
            y = 5.0 + 0.05 * grad21
        else:
            y = 5.0 + 0.05 * 4.0 + 1.0 * (t - 25.0)
        return y + _rauschen(i) * 0.5

    tage = 220
    consumption = _serie(tage, kwh)
    temperaturen = {_START + timedelta(days=i): temp(i) for i in range(tage)}
    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=tage - 1)
    )
    assert ergebnis is not None
    warnzeilen = [z for z in ergebnis.rechenweg if "Zur Einordnung" in z]
    assert warnzeilen, ergebnis.rechenweg
    assert _zahl(T_BASIS_KUEHLEN + ALT_BASIS_OFFSET_C) in warnzeilen[0]
    assert "überschneidet sich NICHT" in warnzeilen[0]
    assert "stärker als die" in warnzeilen[0]


def _zahl(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


# --- Mindest-Abdeckung (Review 20.08.2026, Linse Zahlen Befund 7) ---------------------


def test_zu_wenig_abdeckung_gibt_none_auch_bei_starkem_signal():
    """Ein 26-Tage-Fenster lieferte vor diesem Gate eine Jahresaussage. Selbst
    ein starkes, echtes Signal darf unter ``MIN_ABDECKUNG_TAGE_SAISON`` (60)
    Tagen mit Daten keine Aussage werden — zu dünn, um Zufall von einem
    echten Zusammenhang zu unterscheiden."""
    consumption, temperaturen = _baue_kuehl_serie()
    kurzes_fenster_tage = MIN_ABDECKUNG_TAGE_SAISON - 1
    von = _START + timedelta(days=110)  # mitten in den heißen Tagen (120-159)
    bis = von + timedelta(days=kurzes_fenster_tage - 1)

    ergebnis = gradtag_regression(consumption, temperaturen, von=von, bis=bis)
    assert ergebnis is None


def test_ab_der_abdeckungsschwelle_liefert_dasselbe_signal_ein_ergebnis():
    """Gegenprobe: genau ab ``MIN_ABDECKUNG_TAGE_SAISON`` Tagen liefert
    dasselbe Signal wieder ein Ergebnis — das Gate filtert nur die Abdeckung,
    nicht das Signal selbst."""
    consumption, temperaturen = _baue_kuehl_serie()
    von = _START + timedelta(days=110)  # mitten in den heißen Tagen (120-159)
    bis = von + timedelta(days=MIN_ABDECKUNG_TAGE_SAISON - 1)

    ergebnis = gradtag_regression(consumption, temperaturen, von=von, bis=bis)
    assert ergebnis is not None
    assert ergebnis.tage_mit_daten == MIN_ABDECKUNG_TAGE_SAISON


# --- Gate 3: Steigung mit Monats-Dummies (Review 20.08.2026, Linse Zahlen Befund 2) --

_EINZUG_TAG = 181  # ~1. Juli bei _START = 1. Jänner


def _temp_saisonal(i: int) -> float:
    """Ein glatter Jahresgang (Minimum ~Jänner, Maximum ~Juli) — genug, damit
    ein reiner Kalendersprung zufällig mit der warmen Jahreszeit korreliert,
    ohne dass irgendein Gradtag-Term im Verbrauch steckt."""
    return 10.0 + 12.0 * math.sin(2 * math.pi * (i - 90) / 365.0)


def _kwh_kalenderstufe(i: int) -> float:
    """Reine Kalenderstufe: Einzug am ~1.7., Verbrauch springt von 6 auf
    9 kWh — KEIN Gradtag-Term. Der Sprung korreliert nur zufällig mit dem
    Sommer, weil ``_EINZUG_TAG`` in der warmen Jahreszeit liegt."""
    basis = 9.0 if i >= _EINZUG_TAG else 6.0
    return basis + _rauschen(i)


def test_reiner_kalendereffekt_ohne_temperaturabhaengigkeit_gibt_none():
    """Konstruierter Fall (Linse Zahlen Befund 2): ein Haushalt OHNE jede
    Temperaturabhängigkeit besteht Gate 1 (t ≈ 4,95 ≥ 3,0) und Gate 2 (48 ≥ 15
    Tage über der Basis) — beide Gates allein hätten eine falsche Aussage
    ausgeliefert. Erst Gate 3 (Monats-Dummies) fängt es: die Steigung ohne
    Kalendereffekt fällt auf ~0 (kein Vorzeichenwechsel nötig, ~0 ist schon
    weit unter der Hälfte des rohen Betrags), das Ergebnis wird ``None``."""
    tage = 220
    consumption = _serie(tage, _kwh_kalenderstufe)
    temperaturen = {_START + timedelta(days=i): _temp_saisonal(i) for i in range(tage)}
    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=tage - 1)
    )
    assert ergebnis is None


def test_echter_temperatureffekt_uebersteht_das_monats_dummy_gate():
    """Gegenprobe: ein ECHTER Temperatureffekt (Bens Fall, hier synthetisch
    nachgebaut über ``_baue_kuehl_serie``) bleibt bestehen — Gate 3 darf
    reale Signale nicht mit-eliminieren, nur Kalendereffekte."""
    consumption, temperaturen = _baue_kuehl_serie()
    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=219)
    )
    assert ergebnis is not None
    a = ergebnis.a_kwh_pro_gradtag
    a2 = ergebnis.a_ohne_kalendereffekt_kwh_pro_gradtag
    assert (a > 0) == (a2 > 0)
    assert abs(a2) >= MIN_KALENDER_ANTEIL * abs(a)


def test_rechenweg_nennt_die_steigung_ohne_kalendereffekt():
    consumption, temperaturen = _baue_kuehl_serie()
    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=219)
    )
    assert ergebnis is not None
    assert any("Monats-Dummies" in z for z in ergebnis.rechenweg)


# --- White-HC3-Standardfehler statt klassischem OLS-SE (Linse Zahlen Befund 6) --------


def test_hc3_band_ist_breiter_als_das_klassische_ols_band_bei_streuender_streuung():
    """Residuen, die mit den Gradtagen streuen (Heteroskedastizität): die
    Streuung ist bei niedrigen Gradtagen klein und bei hohen groß — der
    klassische OLS-SE unterschätzt das, HC3 nicht. Das HC3-Band muss deshalb
    mindestens so breit sein wie ein von Hand gerechnetes klassisches Band."""
    tage = 220

    def temp(i):
        return _temp_kuehlen(i)

    def kwh(i):
        cdd = max(0.0, temp(i) - T_BASIS_KUEHLEN)
        # Streuung wächst mit den Gradtagen (nicht mehr das kleine, flache
        # Rauschen der übrigen Tests) — genau die Heteroskedastizität, die
        # HC3 einfängt und der klassische SE ignoriert.
        skala = 1.0 + 0.6 * cdd
        return _GRUND_TRUE + _A_TRUE * cdd + _rauschen(i) * skala

    consumption = _serie(tage, kwh)
    temperaturen = {_START + timedelta(days=i): temp(i) for i in range(tage)}
    ergebnis = gradtag_regression(
        consumption, temperaturen, von=_START, bis=_START + timedelta(days=tage - 1)
    )
    assert ergebnis is not None
    hc3_breite = ergebnis.kwh_band_bis - ergebnis.kwh_band_von

    # Klassisches OLS-Band von Hand, auf denselben Datenpunkten wie das Modul.
    xs, ys = [], []
    for i in range(tage):
        cdd = max(0.0, temp(i) - T_BASIS_KUEHLEN)
        xs.append(cdd)
        ys.append(kwh(i))
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    a_naiv = sxy / sxx
    b_naiv = my - a_naiv * mx
    sse = sum((y - (b_naiv + a_naiv * x)) ** 2 for x, y in zip(xs, ys))
    se_klassisch = (sse / (n - 2)) ** 0.5 / sxx**0.5
    summe_gradtage = sum(xs)
    klassisch_breite = 2 * se_klassisch * summe_gradtage

    assert hc3_breite > klassisch_breite


# --- Heizgradtage: Richtung umgekehrt (dieselbe Funktion, Spec-Pflicht) ---------


_KALTE_TAGE = range(30, 70)  # 40 Tage unter der Basis


def _temp_heizen(i: int) -> float:
    return -2.0 + 0.1 * (i - 50) if i in _KALTE_TAGE else 20.0


def _kwh_heizen(i: int) -> float:
    hdd = max(0.0, T_BASIS_HEIZEN - _temp_heizen(i))
    return _GRUND_TRUE + _A_TRUE * hdd + _rauschen(i)


def test_heizgradtag_regression_kehrt_die_richtung_um():
    consumption = _serie(220, _kwh_heizen)
    temperaturen = {_START + timedelta(days=i): _temp_heizen(i) for i in range(220)}
    ergebnis = gradtag_regression(
        consumption,
        temperaturen,
        von=_START,
        bis=_START + timedelta(days=219),
        richtung=HEIZEN,
    )
    assert ergebnis is not None
    assert ergebnis.t_basis == T_BASIS_HEIZEN
    assert ergebnis.a_kwh_pro_gradtag == pytest.approx(_A_TRUE, abs=0.05)
    assert ergebnis.tage_ueber_basis == len(_KALTE_TAGE)
    assert ergebnis.t_wert >= MIN_T_WERT


def test_heizgradtag_ohne_elektrische_heizung_gibt_none():
    """Ben heizt nicht elektrisch: kalte Tage senken die Basistemperatur-
    Differenz, ohne dass der Verbrauch mitzieht — t < 3,0, also None."""

    def kwh(i):
        return _GRUND_TRUE + _rauschen(i) * 3

    consumption = _serie(220, kwh)
    temperaturen = {_START + timedelta(days=i): _temp_heizen(i) for i in range(220)}
    ergebnis = gradtag_regression(
        consumption,
        temperaturen,
        von=_START,
        bis=_START + timedelta(days=219),
        richtung=HEIZEN,
    )
    assert ergebnis is None


# --- Ein kaputter Fremd-Messwert darf keine nan-Aussage ausliefern (Sicherheitsbefund
# HOCH 2, Review 21.08.2026) -----------------------------------------------------
#
# ``float()`` in ``gridbert/netz/wetter.py`` akzeptierte bisher ``inf``. Ein
# einziger solcher Tag macht ``sxx``/``se_a``/``t_wert`` zu ``nan``, und die
# Gates sind gegen ``nan`` wirkungslos (``nan < 3.0`` ist ``False``, also
# "besteht" das Gate). Verteidigung hier zusätzlich zum Fix in
# ``gridbert/netz/wetter.py`` — dieselbe Funktion darf nicht allein vom
# Aufrufer abhängen, ob ein kaputter Fremdwert je hereinkommt.


def test_ein_unendlicher_temperaturwert_liefert_kein_nan_ergebnis():
    consumption, temperaturen = _baue_kuehl_serie()
    kaputt = dict(temperaturen)
    vergifteter_tag = _START + timedelta(days=125)  # liegt in den heissen Tagen
    kaputt[vergifteter_tag] = math.inf
    ergebnis = gradtag_regression(
        consumption, kaputt, von=_START, bis=_START + timedelta(days=219), richtung=KUEHLEN
    )
    # Entweder das Gate haelt trotzdem (weil der Rest der Serie traegt) -
    # dann muessen ALLE Zahlen endlich sein - oder es gibt sauber None,
    # niemals ein nan-Ergebnis.
    if ergebnis is not None:
        assert math.isfinite(ergebnis.a_kwh_pro_gradtag)
        assert math.isfinite(ergebnis.t_wert)
        assert math.isfinite(ergebnis.kwh_band_von)
        assert math.isfinite(ergebnis.kwh_band_bis)
