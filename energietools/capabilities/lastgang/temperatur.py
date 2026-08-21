# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Kühl-/Heizgradtag-Regression — hängt der Verbrauch an der Außentemperatur?

Nachtrag 2 zur Rückschau-Spec (Bens Einwand 20.08.2026, im Anschluss an
``rueckschau.py``): nachdem ein Haushalt „das war das Klimagerät" beantwortet
hat, ändert sich, wonach gesucht werden darf. Der naive Weg — Tagesstunden mit
demselben Sockel-Verfahren wie ``rueckschau.dauerlast_nacht`` absuchen —
wurde gebaut und verworfen, mit Beleg: an Bens Serie reißen 22 Sommertage die
Tages-Schwelle, aber die Winter-Gegenprobe (Klimagerät ausgeschlossen) reißt
sie an 27 Tagen — MEHR als im Sommer. Die Methode findet „an dem Tag war
jemand zu Hause", nicht „das Klimagerät lief". Sie trennt nicht.

Was trägt, ist eine **Kühlgradtag-Regression nach IPMVP Option C**, eine
etablierte Methode aus der Messung und Verifikation von Energieeinsparungen::

    Tagesverbrauch = Grundverbrauch + a · max(0, T_mittel − T_basis)

Reine Rechnung ohne Netzzugriff: Tagesserie und Tagestemperaturen rein,
Koeffizient und Güte raus. Die Wetterdaten selbst beschafft dieses Modul
nicht — das ist Sache des aufrufenden Systems (bei Gridbert
``gridbert.netz.wetter``).

**Basistemperatur ist FEST, kein Overfitting (Nachtrag 6).** Der naheliegende
nächste Schritt wäre, ``T_basis`` nach dem besten R² zu suchen. Genau das ist
Overfitting an die Stichprobe: an Bens Serie verändert allein die Wahl von
``T_basis`` (16 °C vs. 24 °C) das Kühlungs-Ergebnis um den Faktor 2 (94,7 kWh
vs. 49,5 kWh), ohne dass sich am zugrundeliegenden Verbrauch etwas geändert
hätte. ``T_BASIS_KUEHLEN = 21,0`` °C Tagesmittel (rund 27 °C Maximum, die
übliche Schwelle, ab der in Wohnungen gekühlt wird) ist deshalb eine
Konstante, keine gesuchte Zahl. Wer ``t_basis`` explizit übergibt, tut das
bewusst — die Konstante bleibt trotzdem der Default.

**Abwesenheitstage werden ausgeschlossen, mit denselben Kriterien wie die
Erkennung** (``rueckschau._markiere_abwesenheit`` — nicht neu geschrieben,
eine zweite Wahrheit wäre ein Wartungsrisiko). An Bens Serie verzerren sie
massiv: am 5.8.2026, 31,9 °C, maß der Zähler nur 2,72 kWh — nicht weil die
Wohnung an dem Tag kühl blieb, sondern weil niemand da war. Ohne Ausschluss
zieht so ein Tag die Regressionsgerade nach unten, mit dem größten Hebel
genau an den heißesten Tagen.

**Ergebnis nur, wenn DREI Bedingungen halten** (Nachtrag 6 + Review
20.08.2026, Linse Zahlen Befund 2): der Koeffizient ist mindestens
``MIN_T_WERT`` (3,0) Standardfehler von null entfernt, UND es gibt
mindestens ``MIN_TAGE_UEBER_BASIS`` (15) Tage über der Basistemperatur im
Auswertungsfenster, UND die Steigung bleibt bestehen, wenn jeder reine
Kalendereffekt herausgerechnet wird (drittes Gate, s.u.). Sonst ``None`` —
lieber keine Aussage als eine schwache. An Bens Serie hält das für
Kühlgradtage im Sommer (t = 5,46) und verweigert für Heizgradtage im Winter
(t ≈ 2,2, weil Ben nicht elektrisch heizt) — das ist ein Testfall, kein
Zufall.

**Drittes Gate: Steigung mit Monats-Dummies (Review 20.08.2026).** Die
ersten beiden Gates allein lassen eine nachweislich falsche Aussage durch:
ein Haushalt OHNE jede Temperaturabhängigkeit, bei dem am 1.7. jemand
einzieht und der Verbrauch von 6 auf 9 kWh springt (reine Kalenderstufe,
zufällig mit dem Sommer korreliert), erreicht t = 3,4 und würde sonst eine
Kühlgradtag-Aussage bekommen, die für ein Gerät gilt, das es nicht gibt.
Der Test: dieselbe Steigung, aber mit einem Monats-Fixeffekt (jede
Beobachtung wird um den Mittelwert IHRES Monats zentriert, s.
``_slope_ohne_kalendereffekt`` — der Fixed-Effects/Within-Schätzer, keine
neue Methode). Ein reiner Kalendereffekt erklärt sich vollständig über die
Monats-Mittelwerte, die verbleibende Steigung fällt gegen 0 oder dreht das
Vorzeichen. Ein echter Temperatureffekt bleibt bestehen, weil er auch
INNERHALB eines Monats mit den Gradtagen schwankt. Gemessen an beiden
Fällen: Bens Steigung roh +0,296 kWh/Grad-Tag wird ohne Kalendereffekt
+0,371 (bleibt, sogar stärker) — der konstruierte Fall roh +0,161 wird
ohne Kalendereffekt −0,019 (verschwindet, Vorzeichenwechsel). Das Gate:
gleiches Vorzeichen UND Betrag mindestens ``MIN_KALENDER_ANTEIL`` (die
Hälfte) der rohen Steigung.

**Mindest-Abdeckung (Review 20.08.2026, analog ``rueckschau.
MIN_ABDECKUNG_TAGE``).** Ein 20-26-Tage-Fenster lieferte vor diesem Review
eine Jahresaussage — zu wenig, um zwischen einem echten Zusammenhang und
Zufall zu unterscheiden. ``MIN_ABDECKUNG_TAGE_SAISON`` (60, dieselbe
Schwelle wie in ``rueckschau`` — L30/TEC-Fall, konsistent statt eine zweite
Zahl zu erfinden) verlangt mindestens 60 Tage mit (Verbrauch, Temperatur)-
Paaren, bevor überhaupt regressiert wird.

**Band statt Punktzahl.** Auch mit erfülltem Signifikanz-Gate bleibt der
Koeffizient unsicher. Statt einer einzelnen Zahl liefert dieses Modul ein
Band aus dem Standardfehler: ``(a − SE) · Σ Gradtage`` bis
``(a + SE) · Σ Gradtage``. Das ist ehrlicher als eine Punktschätzung, die
beim nächsten Sommer eine andere Zahl gezeigt hätte.

**White-HC3-Standardfehler statt klassischem OLS-SE (Review 20.08.2026,
Linse Zahlen Befund 6).** Die Residuen streuen NICHT gleichmäßig über die
Gradtage — an Bens Serie SD 1,29 kWh bei 0 Gradtagen, 1,44 kWh im
Mittelband, 1,93 kWh bei ≥4 Gradtagen (Heteroskedastizität). Der klassische
OLS-SE unterstellt konstante Streuung und unterschätzt den wahren SE dadurch
um 38 % (0,0543 statt 0,0750). ``_ols`` rechnet deshalb den White-HC3-SE
(least-squares mit hebelkorrigierten Residuen ``e_i / (1 − h_i)``, robust
gerade bei kleinen Stichproben) statt des klassischen — Bens t-Wert fällt
dadurch ehrlich von 5,46 auf 3,95 (hält das Gate immer noch), der
konstruierte Fall (roh t = 3,37) fällt mit HC3 durch beide Gates.
Autokorrelation ist NICHT die Ursache (ρ = 0,033, Durbin-Watson 1,92) —
reine Varianz-Heterogenität.

**Spezifikationsunsicherheit der Basistemperatur (Review 20.08.2026, Linse
Zahlen Befund 1).** ``T_BASIS_KUEHLEN`` bleibt fest bei 21 °C (kein
Overfitting, s.o.) — aber an Bens Serie zeigt eine segmentweise Regression,
dass zwischen 21 °C und 25 °C KEINE Kühlreaktion messbar ist (t = 1,35),
sie erst ab ~25 °C durchschlägt (t = 4,61); das SSE-Minimum über alle Basen
liegt bei 26,5 °C. Die Bänder bei Basis 21 (56,0–81,2 kWh) und Basis 25
(38,2–52,5 kWh) ÜBERLAPPEN NICHT — die Wahl der Basis bewegt das Ergebnis
(±40–50 %) STÄRKER als die Sampling-Unsicherheit, die das Band zeigt. Der
Rechenweg weist das aus (s. ``_rechenweg``), damit niemand das ausgegebene
Band für die vollständige Unsicherheit hält.

**Was diese Regression NICHT trennt.** Sie misst alles, was mit der Außen-
temperatur zusammenhängt — auch Ventilator, häufigeres Zuhausesein, ein
härter arbeitender Kühlschrank. Das ist die Obergrenze eines Bandes, nicht
die Kosten eines einzelnen Geräts (die Untergrenze liefert
``rueckschau.dauerlast_nacht`` für Geräte mit einer klaren Zeit-Signatur).
Der Vorbehalt gehört in den Anzeigetext, nicht nur hierher.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.lastgang.ereignisse import (
    _erwartete_slots,
    _tageskennzahlen,
)
from energietools.capabilities.lastgang.granularitaet import GRANULARITAET_SCHWELLE_MIN
from energietools.capabilities.lastgang.rueckschau import _markiere_abwesenheit

# --- Richtungen -----------------------------------------------------------------

KUEHLEN = "kuehlen"
HEIZEN = "heizen"
RICHTUNGEN: tuple[str, ...] = (KUEHLEN, HEIZEN)

# Feste Basistemperaturen (Tagesmittel °C) — NICHT nach bestem R² gesucht,
# siehe Modul-Docstring. 21 °C entspricht rund 27 °C Maximum (Kühlung); 15 °C
# ist die in der Heizgradtag-Praxis übliche Basis (Heizgrenztemperatur).
T_BASIS_KUEHLEN = 21.0
T_BASIS_HEIZEN = 15.0

# Signifikanz-Gate (Nachtrag 6 + Review 20.08.2026): DREI Bedingungen müssen
# halten, sonst None (s. Modul-Docstring).
MIN_T_WERT = 3.0
MIN_TAGE_UEBER_BASIS = 15

# Drittes Gate (Review 20.08.2026, Linse Zahlen Befund 2): die Steigung mit
# Monats-Dummies muss dasselbe Vorzeichen UND mindestens die Hälfte des
# Betrags der rohen Steigung behalten — sonst ist die rohe Steigung (auch)
# ein Kalendereffekt, keine Temperaturreaktion. An Bens Serie bleiben 0,371
# von 0,296 (125 %) — beim konstruierten Placebo-Fall werden aus +0,161
# −0,019 (Vorzeichenwechsel, fällt durch).
MIN_KALENDER_ANTEIL = 0.5

# Unter so vielen Tagen mit (Verbrauch, Temperatur)-Paaren im Fenster ist
# eine Jahresaussage nicht tragfähig (Review 20.08.2026, Linse Zahlen Befund
# 7) — dieselbe Schwelle wie ``rueckschau.MIN_ABDECKUNG_TAGE`` (L30/TEC-Fall:
# konsistent statt eine zweite, unbegründete Zahl zu erfinden). Ohne dieses
# Gate lieferte ein 20-26-Tage-Fenster einen ausgelieferten €-Betrag.
MIN_ABDECKUNG_TAGE_SAISON = 60

# Unter so vielen Tagen mit (Verbrauch, Temperatur)-Paaren ist eine Regression
# mit zwei Freiheitsgraden (Steigung + Achsenabschnitt) nicht mehr sinnvoll
# schätzbar — deutlich unter MIN_TAGE_UEBER_BASIS, greift also nur, wenn
# ohnehin schon zu wenig Daten da sind.
MIN_PUNKTE = 3

# Für die Spezifikationsunsicherheit (Review 20.08.2026, Linse Zahlen Befund
# 1): eine zweite, um dieses Grad höhere Basis wird zum VERGLEICH gerechnet
# (NICHT als Ersatz — T_BASIS_KUEHLEN bleibt fest, s. Modul-Docstring). An
# Bens Serie ist 4 °C genau der Abstand zwischen der festen Basis (21 °C) und
# der Basis, ab der die segmentweise Regression eine echte Kühlreaktion
# zeigt (25 °C, t = 4,61) — bei diesem Abstand überlappen die Bänder bereits
# nicht mehr.
ALT_BASIS_OFFSET_C = 4.0

_GRANULARITAET_FEHLER = (
    "Kühl-/Heizgradtag-Regression braucht Q15-Auflösung; "
    "interval_minutes={interval_minutes} (Tageswerte) ist zu grob."
)
_LEERER_LASTGANG_FEHLER = "Leerer Lastgang — keine Gradtag-Regression ableitbar."
_UNBEKANNTE_RICHTUNG_FEHLER = (
    "Unbekannte Richtung für die Gradtag-Regression: {richtung!r} "
    f"(erlaubt: {RICHTUNGEN})."
)


@dataclass(frozen=True, slots=True)
class Gradtagauswertung:
    """Ergebnis einer Kühl- oder Heizgradtag-Regression über ein Fenster.

    ``grundverbrauch_kwh_tag`` ist der Achsenabschnitt (Verbrauch an einem
    Tag ohne Gradtage), ``a_kwh_pro_gradtag`` die Steigung. ``kwh_band_von``/
    ``kwh_band_bis`` ist die hochgerechnete Zusatzenergie über das ganze
    Fenster aus dem White-HC3-Standardfehler der Steigung — keine Punktzahl
    (siehe Modul-Docstring). ``eur_band_*`` ist ``None`` ohne
    ``arbeitspreis_ct_kwh``. ``a_ohne_kalendereffekt_kwh_pro_gradtag`` ist die
    Steigung mit Monats-Dummies (drittes Gate, Review 20.08.2026) — bei einem
    ausgelieferten Ergebnis IMMER vorzeichengleich und mindestens halb so
    groß wie ``a_kwh_pro_gradtag``, sonst wäre das Ergebnis ``None`` gewesen.
    """

    richtung: str
    t_basis: float
    von: date
    bis: date
    tage_mit_daten: int
    tage_ueber_basis: int
    grundverbrauch_kwh_tag: float
    a_kwh_pro_gradtag: float
    a_ohne_kalendereffekt_kwh_pro_gradtag: float
    t_wert: float
    r2: float
    summe_gradtage: float
    kwh_band_von: float
    kwh_band_bis: float
    eur_band_von: float | None
    eur_band_bis: float | None
    rechenweg: tuple[str, ...]


def gradtag_regression(
    consumption: list[tuple[datetime, float]],
    temperaturen: Mapping[date, float] | Iterable[tuple[date, float]],
    *,
    von: date,
    bis: date,
    richtung: str = KUEHLEN,
    t_basis: float | None = None,
    interval_minutes: int = 15,
    arbeitspreis_ct_kwh: float | None = None,
) -> Gradtagauswertung | None:
    """Kühl- oder Heizgradtag-Regression über ``[von, bis]``.

    Args:
        consumption: (Zeitstempel, kWh)-Paare in Ortszeit.
        temperaturen: Tagesmittel °C je Kalendertag — eine ``Mapping`` oder
            eine Folge von (Tag, °C)-Paaren.
        von, bis: das Auswertungsfenster (beide Enden eingeschlossen). Kein
            Default: das aufrufende System entscheidet über den Zeitraum
            (z.B. die aktuelle Jahreszeit), dieses Modul rechnet nur.
        richtung: ``KUEHLEN`` (Standard) oder ``HEIZEN`` — kehrt um, ob
            Gradtage über oder unter der Basistemperatur gezählt werden.
        t_basis: Basistemperatur °C (Default je Richtung: 21,0 °C Kühlen,
            15,0 °C Heizen — s. Modul-Docstring, NICHT nach bestem R² suchen).
        interval_minutes: Mess-Intervall (Q15 = 15).
        arbeitspreis_ct_kwh: ohne diesen Wert entstehen keine Euro-Felder.

    Returns:
        ``None``, wenn eines von DREI Gates nicht hält (s. Modul-Docstring):
        unter ``MIN_ABDECKUNG_TAGE_SAISON`` Tagen mit Daten, t < ``MIN_T_WERT``
        oder weniger als ``MIN_TAGE_UEBER_BASIS`` Tage über der Basis, oder
        die Steigung mit Monats-Dummies dreht das Vorzeichen bzw. bricht auf
        unter die Hälfte des rohen Betrags ein — sonst eine
        ``Gradtagauswertung``.

    Raises:
        CapabilityError: bei leerer Serie, zu grober Auflösung oder
            unbekannter Richtung.
    """
    _validiere_eingabe(consumption, interval_minutes, richtung)
    basis = t_basis if t_basis is not None else _default_basis(richtung)
    temp_by_tag = dict(temperaturen)

    tage = _tageskennzahlen(consumption, interval_minutes)
    voll = [t for t in tage if t.slots >= _erwartete_slots(interval_minutes)]
    if not voll:
        return None

    nach_tag = {t.tag: t for t in voll}
    fenster_tage = {t.tag for t in voll if von <= t.tag <= bis}
    abwesend = {tag for tag, _, _, _ in _markiere_abwesenheit(nach_tag, fenster_tage)}

    xs, ys, monate = _punkte(voll, temp_by_tag, fenster_tage, abwesend, richtung, basis)
    tage_mit_daten = len(xs)
    tage_ueber_basis = sum(1 for x in xs if x > 0)

    # Gate 1 (Review 20.08.2026, Linse Zahlen Befund 7): Mindest-Abdeckung,
    # bevor überhaupt regressiert wird — s. Modul-Docstring.
    if tage_mit_daten < MIN_ABDECKUNG_TAGE_SAISON:
        return None

    regression = _ols(xs, ys)
    if regression is None:
        return None
    a, b, se_a, r2 = regression
    # ``not (se_a > 0)`` statt ``se_a <= 0`` (Sicherheitsbefund HOCH 2,
    # Review 21.08.2026): ein kaputter Fremd-Temperaturwert (z. B. ``inf``,
    # bislang durchgelassen von ``float()`` in ``gridbert/netz/wetter.py``)
    # macht ``se_a`` zu ``nan`` — und ``nan <= 0`` ist ``False``, das Gate
    # „besteht" also gerade dann, wenn es greifen müsste. Primär gefiltert
    # wird an der Quelle (``_parse_csv``); dieser Vergleich bleibt trotzdem
    # explizit nan-sicher.
    if not (se_a > 0):
        return None
    t_wert = a / se_a

    # Gate 2 (Nachtrag 6). Ebenfalls nan-sicher formuliert, aus demselben
    # Grund wie oben.
    if not (t_wert >= MIN_T_WERT) or tage_ueber_basis < MIN_TAGE_UEBER_BASIS:
        return None

    # Gate 3 (Review 20.08.2026, Linse Zahlen Befund 2): Steigung mit
    # Monats-Dummies — s. Modul-Docstring.
    a_ohne_kalender = _slope_ohne_kalendereffekt(monate, xs, ys)
    if a_ohne_kalender is None or not _besteht_kalender_gate(a, a_ohne_kalender):
        return None

    ausgeschlossen_n, ausgeschlossen_gradtage = _ausgeschlossene_abwesenheitstage(
        voll, temp_by_tag, fenster_tage, abwesend, richtung, basis
    )

    return _baue_ergebnis(
        richtung=richtung,
        basis=basis,
        von=von,
        bis=bis,
        tage_mit_daten=tage_mit_daten,
        tage_ueber_basis=tage_ueber_basis,
        a=a,
        b=b,
        a_ohne_kalender=a_ohne_kalender,
        se_a=se_a,
        t_wert=t_wert,
        r2=r2,
        summe_gradtage=round(sum(xs), 2),
        ausgeschlossen_n=ausgeschlossen_n,
        ausgeschlossen_gradtage=ausgeschlossen_gradtage,
        arbeitspreis_ct_kwh=arbeitspreis_ct_kwh,
        voll=voll,
        temp_by_tag=temp_by_tag,
        fenster_tage=fenster_tage,
        abwesend=abwesend,
    )


def _baue_ergebnis(
    *,
    richtung: str,
    basis: float,
    von: date,
    bis: date,
    tage_mit_daten: int,
    tage_ueber_basis: int,
    a: float,
    b: float,
    a_ohne_kalender: float,
    se_a: float,
    t_wert: float,
    r2: float,
    summe_gradtage: float,
    ausgeschlossen_n: int,
    ausgeschlossen_gradtage: float,
    arbeitspreis_ct_kwh: float | None,
    voll,
    temp_by_tag: dict[date, float],
    fenster_tage: set[date],
    abwesend: set[date],
) -> Gradtagauswertung:
    """Baut Band, Rechenweg und das Ergebnis-Objekt aus der fertigen Regression."""
    kwh_band_von = round((a - se_a) * summe_gradtage, 1)
    kwh_band_bis = round((a + se_a) * summe_gradtage, 1)
    eur_band_von, eur_band_bis = _eur_band(kwh_band_von, kwh_band_bis, arbeitspreis_ct_kwh)

    basis_zeile = _spezifikationsunsicherheit_zeile(
        voll,
        temp_by_tag,
        fenster_tage,
        abwesend,
        richtung,
        basis,
        kwh_band_von,
        kwh_band_bis,
    )

    rechenweg = _rechenweg(
        richtung=richtung,
        basis=basis,
        n=tage_mit_daten,
        tage_ueber_basis=tage_ueber_basis,
        grund=round(b, 2),
        a=round(a, 3),
        a_ohne_kalender=round(a_ohne_kalender, 3),
        se_a=se_a,
        t_wert=t_wert,
        r2=r2,
        summe_gradtage=summe_gradtage,
        ausgeschlossen_n=ausgeschlossen_n,
        ausgeschlossen_gradtage=ausgeschlossen_gradtage,
        kwh_band_von=kwh_band_von,
        kwh_band_bis=kwh_band_bis,
        eur_band_von=eur_band_von,
        eur_band_bis=eur_band_bis,
        arbeitspreis_ct_kwh=arbeitspreis_ct_kwh,
        basis_zeile=basis_zeile,
    )

    return Gradtagauswertung(
        richtung=richtung,
        t_basis=basis,
        von=von,
        bis=bis,
        tage_mit_daten=tage_mit_daten,
        tage_ueber_basis=tage_ueber_basis,
        grundverbrauch_kwh_tag=round(b, 2),
        a_kwh_pro_gradtag=round(a, 3),
        a_ohne_kalendereffekt_kwh_pro_gradtag=round(a_ohne_kalender, 3),
        t_wert=round(t_wert, 1),
        r2=round(r2, 2),
        summe_gradtage=summe_gradtage,
        kwh_band_von=kwh_band_von,
        kwh_band_bis=kwh_band_bis,
        eur_band_von=eur_band_von,
        eur_band_bis=eur_band_bis,
        rechenweg=rechenweg,
    )


# --- Eingabe-Validierung -----------------------------------------------------------


def _validiere_eingabe(
    consumption: list[tuple[datetime, float]], interval_minutes: int, richtung: str
) -> None:
    if not consumption:
        raise CapabilityError(_LEERER_LASTGANG_FEHLER)
    if interval_minutes >= GRANULARITAET_SCHWELLE_MIN:
        raise CapabilityError(
            _GRANULARITAET_FEHLER.format(interval_minutes=interval_minutes)
        )
    if richtung not in RICHTUNGEN:
        raise CapabilityError(_UNBEKANNTE_RICHTUNG_FEHLER.format(richtung=richtung))


def _default_basis(richtung: str) -> float:
    return T_BASIS_KUEHLEN if richtung == KUEHLEN else T_BASIS_HEIZEN


# --- Datenpunkte: Fenster, Abwesenheit raus, Temperatur da -------------------------


def _punkte(
    voll,
    temp_by_tag: dict[date, float],
    fenster_tage: set[date],
    abwesend: set[date],
    richtung: str,
    basis: float,
) -> tuple[list[float], list[float], list[int]]:
    """(Gradtage, Tagesverbrauch, Monat)-Tripel — Abwesenheitstage und Tage
    ohne Temperaturwert bleiben draußen (s. Modul-Docstring). Der Monat wird
    für das dritte Gate gebraucht (``_slope_ohne_kalendereffekt``)."""
    xs: list[float] = []
    ys: list[float] = []
    monate: list[int] = []
    for t in voll:
        if t.tag not in fenster_tage or t.tag in abwesend:
            continue
        temp = temp_by_tag.get(t.tag)
        if temp is None:
            continue
        grad = (temp - basis) if richtung == KUEHLEN else (basis - temp)
        xs.append(max(0.0, grad))
        ys.append(t.kwh)
        monate.append(t.tag.month)
    return xs, ys, monate


def _ausgeschlossene_abwesenheitstage(
    voll,
    temp_by_tag: dict[date, float],
    fenster_tage: set[date],
    abwesend: set[date],
    richtung: str,
    basis: float,
) -> tuple[int, float]:
    """(Anzahl, Summe Gradtage) der Tage, die NUR wegen Abwesenheit aus der
    Regression fliegen (Review 20.08.2026, Linse Zahlen Befund 3) — Tage ohne
    Temperaturwert zählen hier NICHT mit, die sind ein anderer Ausschlussgrund
    und würden die Zahl im Rechenweg falsch benennen."""
    anzahl = 0
    summe = 0.0
    for t in voll:
        if t.tag not in fenster_tage or t.tag not in abwesend:
            continue
        temp = temp_by_tag.get(t.tag)
        if temp is None:
            continue
        grad = (temp - basis) if richtung == KUEHLEN else (basis - temp)
        summe += max(0.0, grad)
        anzahl += 1
    return anzahl, round(summe, 2)


# --- Kleinste Quadrate --------------------------------------------------------------


def _ols(xs: list[float], ys: list[float]) -> tuple[float, float, float, float] | None:
    """(Steigung a, Achsenabschnitt b, White-HC3-Standardfehler von a, R²) —
    ``None`` bei zu wenigen Punkten oder ohne Streuung in ``xs`` (Placebo-
    Fall: keine Tage über der Basis, s. Modul-Docstring).

    HC3 statt des klassischen OLS-SE (Review 20.08.2026, Linse Zahlen
    Befund 6): die Residuen streuen NICHT gleichmäßig über die Gradtage — der
    klassische SE unterstellt das und unterschätzt dadurch (an Bens Serie um
    38 %). HC3 gewichtet jedes quadrierte Residuum mit seinem Hebel
    ``h_i = 1/n + (x_i − x̄)² / Sxx`` (``e_i / (1 − h_i)``, s. MacKinnon/White
    1985) — robust gerade bei kleinen Stichproben mit hohem Hebel an den
    Rändern (hier: den heißesten Tagen)."""
    n = len(xs)
    if n < MIN_PUNKTE:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    # ``not (sxx > 0)`` statt ``sxx <= 0`` (Sicherheitsbefund HOCH 2, Review
    # 21.08.2026): ein ``inf`` unter ``xs`` macht ``sxx`` zu ``nan``, und
    # ``nan <= 0`` ist ``False`` — dieselbe Lücke wie beim Signifikanz-Gate,
    # nur eine Ebene tiefer.
    if not (sxx > 0):
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    a = sxy / sxx
    b = mean_y - a * mean_x
    residuen = [y - (b + a * x) for x, y in zip(xs, ys)]
    sse = sum(e * e for e in residuen)
    sst = sum((y - mean_y) ** 2 for y in ys)
    dof = n - 2
    if dof <= 0:
        return None
    se_a = _hc3_se(xs, mean_x, sxx, residuen)
    if not (se_a > 0):
        return None
    r2 = 1 - sse / sst if sst > 0 else 0.0
    return a, b, se_a, r2


def _hc3_se(xs: list[float], mean_x: float, sxx: float, residuen: list[float]) -> float:
    """White-HC3-Standardfehler der Steigung einer einfachen Regression."""
    n = len(xs)
    summe = 0.0
    for x, e in zip(xs, residuen):
        hebel = 1.0 / n + (x - mean_x) ** 2 / sxx
        summe += (x - mean_x) ** 2 * (e / (1.0 - hebel)) ** 2
    return (summe / sxx**2) ** 0.5


# --- Gate 3: Steigung mit Monats-Dummies (Review 20.08.2026) ------------------------


def _slope_ohne_kalendereffekt(
    monate: list[int], xs: list[float], ys: list[float]
) -> float | None:
    """Fixed-Effects/Within-Schätzer: jede Beobachtung wird um den Mittelwert
    IHRES Monats zentriert, dann eine Steigung durch den Ursprung geschätzt
    (s. Modul-Docstring — keine neue Methode, äquivalent zu Monats-Dummies in
    der Regression). ``None`` ohne Streuung nach dem Zentrieren (dann ist
    auch dieses Gate nicht auswertbar — die Funktion lässt das Ergebnis dann
    NICHT durch, s. Aufrufer)."""
    gruppen: dict[int, list[int]] = defaultdict(list)
    for i, monat in enumerate(monate):
        gruppen[monat].append(i)
    sxy = 0.0
    sxx = 0.0
    for indices in gruppen.values():
        if len(indices) < 2:
            continue
        mx = sum(xs[i] for i in indices) / len(indices)
        my = sum(ys[i] for i in indices) / len(indices)
        for i in indices:
            dx = xs[i] - mx
            dy = ys[i] - my
            sxy += dx * dy
            sxx += dx * dx
    # nan-sicher, aus demselben Grund wie in ``_ols`` (Sicherheitsbefund
    # HOCH 2, Review 21.08.2026).
    if not (sxx > 0):
        return None
    return sxy / sxx


def _besteht_kalender_gate(a: float, a_ohne_kalender: float) -> bool:
    """Gleiches Vorzeichen UND Betrag mindestens ``MIN_KALENDER_ANTEIL`` der
    rohen Steigung — sonst ist die rohe Steigung (auch) ein Kalendereffekt."""
    if a == 0:
        return False
    gleiches_vorzeichen = (a > 0) == (a_ohne_kalender > 0)
    return gleiches_vorzeichen and abs(a_ohne_kalender) >= MIN_KALENDER_ANTEIL * abs(a)


# --- Preis --------------------------------------------------------------------------


def _eur_band(
    kwh_von: float, kwh_bis: float, preis: float | None
) -> tuple[float | None, float | None]:
    if preis is None:
        return None, None
    return round(kwh_von * preis / 100, 2), round(kwh_bis * preis / 100, 2)


# --- Spezifikationsunsicherheit der Basistemperatur (Review 20.08.2026) ------------


def _spezifikationsunsicherheit_zeile(
    voll,
    temp_by_tag: dict[date, float],
    fenster_tage: set[date],
    abwesend: set[date],
    richtung: str,
    basis: float,
    kwh_band_von: float,
    kwh_band_bis: float,
) -> str | None:
    """Rechnet dieselbe Regression bei ``basis + ALT_BASIS_OFFSET_C`` und
    vergleicht die Bänder — ``None`` nur bei der Standard-Basis (die feste
    Konstante ist der ausgelieferte Fall, nicht jede von einem Aufrufer
    explizit gewählte), und nur für Kühlen (die Heizgradtag-Basis hat dieses
    Problem an Bens Serie nicht gezeigt, s. Modul-Docstring). Liefert
    ``None``, wenn die Alt-Basis selbst keine auswertbare Regression ergibt
    (zu wenige Punkte/keine Streuung) — dann lässt sich der Vergleich nicht
    ehrlich ziehen, also lieber keine Zeile als eine geratene."""
    if richtung != KUEHLEN or basis != T_BASIS_KUEHLEN:
        return None
    alt_basis = basis + ALT_BASIS_OFFSET_C
    xs2, ys2, _ = _punkte(voll, temp_by_tag, fenster_tage, abwesend, richtung, alt_basis)
    regression2 = _ols(xs2, ys2)
    if regression2 is None:
        return None
    a2, _b2, se_a2, _r2_2 = regression2
    summe2 = sum(xs2)
    band2_von = round((a2 - se_a2) * summe2, 1)
    band2_bis = round((a2 + se_a2) * summe2, 1)
    ueberlappt = not (band2_bis < kwh_band_von or kwh_band_bis < band2_von)
    if ueberlappt:
        return (
            f"Zur Einordnung: bei {_zahl(alt_basis)} °C Basis ergäbe dieselbe Rechnung "
            f"{_zahl(band2_von)} bis {_zahl(band2_bis)} kWh — überschneidet sich mit dem "
            "Band oben."
        )
    return (
        f"Zur Einordnung: bei {_zahl(alt_basis)} °C Basis ergäbe dieselbe Rechnung "
        f"{_zahl(band2_von)} bis {_zahl(band2_bis)} kWh — überschneidet sich NICHT mit "
        "dem Band oben. Die Wahl der Basistemperatur bewegt das Ergebnis stärker als die "
        "Streuung der Messwerte, die das Band oben zeigt."
    )


# --- Rechenweg (No-LLM-Math: jede Zahl entsteht hier, nicht im Anzeigetext) ----------


def _rechenweg(
    *,
    richtung: str,
    basis: float,
    n: int,
    tage_ueber_basis: int,
    grund: float,
    a: float,
    a_ohne_kalender: float,
    se_a: float,
    t_wert: float,
    r2: float,
    summe_gradtage: float,
    ausgeschlossen_n: int,
    ausgeschlossen_gradtage: float,
    kwh_band_von: float,
    kwh_band_bis: float,
    eur_band_von: float | None,
    eur_band_bis: float | None,
    arbeitspreis_ct_kwh: float | None,
    basis_zeile: str | None,
) -> tuple[str, ...]:
    art = "Kühlgradtage" if richtung == KUEHLEN else "Heizgradtage"
    summe_zeile = f"Summe der Gradtage an den {n} gerechneten Tagen: {_zahl(summe_gradtage)}"
    if ausgeschlossen_n:
        summe_zeile += (
            f" ({ausgeschlossen_n} Tage ohne Anwesenheit sind nicht dabei, zusammen "
            f"{_zahl(ausgeschlossen_gradtage)} Gradtage)."
        )
    else:
        summe_zeile += "."
    zeilen = [
        f"{art} über {_zahl(basis)} °C Tagesmittel (fest, nicht nach bestem "
        f"R² gesucht), {n} Tage mit Daten, davon {tage_ueber_basis} über der Basis.",
        f"Regression Tagesverbrauch = {_zahl(grund)} kWh + {_zahl(a)} kWh/Grad-Tag "
        f"× Gradtage, White-HC3-Standardfehler = {f'{se_a:.4f}'.replace('.', ',')}, "
        f"t = {_zahl(t_wert)} "
        f"(≥ {_zahl(MIN_T_WERT)} nötig), R² = {_zahl(r2)}.",
        f"Steigung mit Monats-Dummies (Kalendereffekt raus): {_zahl(a_ohne_kalender)} "
        f"kWh/Grad-Tag — gleiches Vorzeichen und ≥ {int(MIN_KALENDER_ANTEIL * 100)} % von "
        f"{_zahl(a)} nötig, hält.",
        summe_zeile,
        f"Band aus dem HC3-Standardfehler der Steigung: {_zahl(kwh_band_von)} bis "
        f"{_zahl(kwh_band_bis)} kWh.",
    ]
    if eur_band_von is not None and arbeitspreis_ct_kwh is not None:
        zeilen.append(
            f"{_zahl(kwh_band_von)}–{_zahl(kwh_band_bis)} kWh × "
            f"{_zahl(arbeitspreis_ct_kwh)} ct/kWh / 100 = {_zahl(eur_band_von)}–"
            f"{_zahl(eur_band_bis)} €."
        )
    if basis_zeile is not None:
        zeilen.append(basis_zeile)
    return tuple(zeilen)


def _zahl(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")
