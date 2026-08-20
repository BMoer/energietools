# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Ereignis-Erkennung im Lastgang — was hat sich zuletzt geändert?

Abgrenzung zu den beiden benachbarten Modulen, die auf denselben Daten
arbeiten:

* :mod:`energietools.capabilities.lastgang.signals` beschreibt den Haushalt
  **strukturell** über die ganze Serie (heizt elektrisch, hat PV, hat
  Dauerläufer). Zeitpunkt-frei.
* ``tools.load_profile.tages_ausreisser_typisiert`` markiert **ungewöhnliche
  Tage** einer Serie (magnitude/shape) — als Label in einem Report.
* Dieses Modul beantwortet die Frage, die ein **Alarm** stellt: *ist in den
  letzten Tagen etwas passiert, das vorher nicht war, und wie sah es aus?*
  Es liefert deshalb Zeiträume statt Tage, eine benannte Ereignisart statt
  magnitude/shape, und die Signatur (Leistung, Stunden, Dauer), aus der
  :mod:`energietools.capabilities.lastgang.deutung` eine Hypothese baut.

**Warum keine Disaggregation.** Die Forschungslage zu NILM bei sehr niedriger
Abtastrate ist eindeutig: bei 15–60-Minuten-Werten fallen Kurzläufer
(Wasserkocher, Mikrowelle, Toaster) praktisch aus — Petralia et al. (ACM
e-Energy 2023) messen für den Wasserkocher einen Macro-F1 von ~0,45 bei 30-min-
Daten, also Münzwurf-Niveau, und einen mittleren Genauigkeitsverlust von ~0,1
(bester Klassifikator 0,15) beim Übergang von 1 min auf 30 min. Was bei grober
Auflösung bleibt, sind Verbraucher mit langer Laufzeit und hoher Leistung
(E-Auto, Wärmepumpe, Trockner, Kühlung) — und auch die erkennen Zhao et al.
(Applied Energy 2020) nur mit **Geräte-Wattage aus einer Haushaltsbefragung**
als Zusatzwissen. Genau das ist der Weg dieses Moduls: es benennt die Signatur
und überlässt die Zuordnung dem Haushalt, statt sie zu behaupten.

**Ruhe vor Trefferquote.** Die Schwellen sind so gebaut, dass eine
unauffällige Serie NICHTS ergibt. Der dokumentierte Vorfall in
``tests/test_anomalie_schwelle.py`` (57,8 % aller Tage als Anomalie markiert,
Schwelle unter dem Median) war ein Label in einem Report; auf einem Melde-Pfad
wäre derselbe Fehler eine E-Mail pro zweitem Tag. Jede Ereignisart verlangt
deshalb DREI unabhängige Bedingungen gleichzeitig: robust-statistische
Auffälligkeit (Median + k·MAD), eine relative Mindesthöhe und eine **absolute**
Mindesthöhe. Die absolute ist die wichtigste — ohne sie alarmiert ein
2.000-kWh-Haushalt am lautesten, obwohl dort am wenigsten dahintersteckt.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.lastgang.granularitaet import GRANULARITAET_SCHWELLE_MIN
from energietools.capabilities.lastgang.signals import _NIGHT

# --- Ereignisarten ------------------------------------------------------------

DAUERLAST_NACHT = "dauerlast_nacht"
VERBRAUCH_HOCH = "verbrauch_hoch"
ABWESENHEIT = "abwesenheit"
NEUE_SPITZE = "neue_spitze"

EREIGNISARTEN: tuple[str, ...] = (
    DAUERLAST_NACHT,
    VERBRAUCH_HOCH,
    ABWESENHEIT,
    NEUE_SPITZE,
)

# --- Schwellen (dokumentiert, keine Magic Numbers) ----------------------------

# Skalierung MAD → Sigma bei Normalverteilung. SSOT der Zahl ist
# ``tools.load_profile._MAD_ZU_SIGMA``; hier gespiegelt, weil dieses Paket
# nicht von ``tools`` abhängen soll (capabilities → tools wäre eine neue
# Kante in der Abhängigkeitsrichtung).
MAD_ZU_SIGMA = 1.4826

# Wie viele robuste Sigma ein Tag vom typischen Tag entfernt sein muss.
K_SIGMA = 3.0

# Mindestzahl Vergleichstage, ab der eine Verteilung überhaupt schätzbar ist.
# Darunter ist jede Schwelle geraten (gleiche Grenze wie load_profile).
MIN_BASELINE_TAGE = 14

# Beobachtungsfenster und Vergleichszeitraum in Tagen.
FENSTER_TAGE = 14
BASELINE_TAGE = 90

# Dauerlast über Nacht: 50 W ist die Grenze, unter der ein Unterschied im
# Nacht-Median nicht mehr von Messrauschen und Alltag zu trennen ist — ein
# Ladegerät, ein zusätzlich eingeschaltetes Netzteil liegen darunter.
NACHT_MIN_ABS_W = 50
NACHT_MIN_REL = 0.25

# Verbrauchssprung: unter 2 kWh Mehrverbrauch am Tag ist die Ursache in einem
# Haushalt nicht mehr auffindbar (ein Backofenlauf sind ~1,5 kWh) und die
# Nachricht wäre eine Zumutung statt einer Hilfe.
HOCH_MIN_ABS_KWH = 2.0
HOCH_MIN_REL = 1.4

# Abwesenheit: höchstens 60 % des üblichen Tagesverbrauchs UND eine
# eingebrochene Tagesspitze.
#
# Das zweite Kriterium war zuerst die "Flachheit" (Tagesspitze gegen die
# Grundlast desselben Tages) und lag damit falsch — nachgemessen an einer
# realen Serie: an drei belegten Urlaubsphasen (16.–18.07., 03.–06.08.,
# 14./15.08.2026) betrug dieses Verhältnis 3,1–3,4 und riss jede sinnvolle
# Grenze, obwohl an keinem der Tage jemand zu Hause war. Gemessen wurde nicht
# Anwesenheit, sondern das **Taktverhältnis des Kühlschranks** (52 W aus,
# 176 W an) — das bleibt gleich, ob jemand da ist oder nicht.
#
# Der Vergleich muss gegen die üblichen Tage gehen, nicht gegen denselben Tag:
# wer zu Hause ist, schaltet irgendwann etwas Größeres ein. Bricht die
# Tagesspitze auf unter 40 % der typischen Tagesspitze ein, hat den ganzen Tag
# kein einziges Haushaltsgerät gearbeitet.
ABWESEND_MAX_ANTEIL = 0.6
ABWESEND_MAX_PEAK_ANTEIL = 0.4
ABWESEND_MIN_TAGE = 2

# Ab wann eine Stunde als vom Mehrverbrauch betroffen gilt: 30 % über ihrem
# eigenen üblichen Wert UND mindestens 0,05 kWh (200 W über die Stunde).
STUNDE_BETROFFEN_MIN_REL = 0.3
STUNDE_BETROFFEN_MIN_KWH = 0.05

# Neue Spitze: mindestens 30 % über allem bisher Gemessenen und absolut
# oberhalb von 2 kW — darunter ist es ein Wasserkocher und keine Nachricht.
SPITZE_MIN_FAKTOR = 1.3
SPITZE_MIN_KW = 2.0

_GRANULARITAET_FEHLER = (
    "Ereignis-Erkennung braucht Q15-Auflösung; interval_minutes={interval_minutes} "
    "(Tageswerte) ist zu grob."
)
_LEERER_LASTGANG_FEHLER = "Leerer Lastgang — keine Ereignisse ableitbar."


# --- Ergebnis -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Ereignis:
    """Ein zusammenhängender auffälliger Zeitraum mit seiner Signatur.

    Die Signatur (``stunden``, ``zusatz_leistung_w``, ``tage``, ``peak_kw``)
    ist der Teil, aus dem eine Hypothese entsteht — eine Last um 3 Uhr bedeutet
    etwas anderes als dieselbe Last um 13 Uhr, und 2 kW über vier Stunden
    etwas anderes als 200 W über 24.
    """

    typ: str
    von: date
    bis: date
    tage: int
    stunden: tuple[int, ...]
    zusatz_kwh: float = 0.0
    zusatz_leistung_w: int = 0
    baseline_leistung_w: int = 0
    kwh_tag: float = 0.0
    baseline_kwh_tag: float = 0.0
    peak_kw: float = 0.0
    baseline_peak_kw: float = 0.0
    staerke: float = 0.0  # Abstand zur Baseline in robusten Sigma


@dataclass(frozen=True, slots=True)
class _Tag:
    """Die Kennzahlen eines Kalendertags, aus denen alle Regeln lesen."""

    tag: date
    kwh: float
    stunden_kwh: tuple[float, ...]  # 24 Werte
    nacht_w: int
    grundlast_kw: float
    peak_kw: float
    peak_stunde: int
    slots: int


def finde_ereignisse(
    consumption: list[tuple[datetime, float]],
    *,
    interval_minutes: int = 15,
    fenster_tage: int = FENSTER_TAGE,
    baseline_tage: int = BASELINE_TAGE,
    heute: date | None = None,
    k_sigma: float = K_SIGMA,
) -> list[Ereignis]:
    """Findet auffällige Zeiträume in den letzten ``fenster_tage`` Tagen.

    Args:
        consumption: (Zeitstempel, kWh)-Paare. Die Zeitstempel sind **Ortszeit**
            — die Ereignisarten hängen an der Uhrzeit, die der Haushalt erlebt
            hat, nicht an UTC.
        interval_minutes: Mess-Intervall (Q15 = 15).
        fenster_tage: Beobachtungsfenster; nur darin liegende Auffälligkeiten
            werden gemeldet.
        baseline_tage: Vergleichszeitraum unmittelbar davor.
        heute: letzter Tag des Beobachtungsfensters (Default: letzter Tag der
            Serie).
        k_sigma: Wie viele robuste Sigma für die statistische Bedingung.

    Returns:
        Ereignisse, aufsteigend nach Startdatum. Leer, wenn nichts auffällig
        ist oder die Historie für eine Schwelle nicht reicht.

    Raises:
        CapabilityError: bei leerer Serie oder zu grober Auflösung.
    """
    if not consumption:
        raise CapabilityError(_LEERER_LASTGANG_FEHLER)
    if interval_minutes >= GRANULARITAET_SCHWELLE_MIN:
        raise CapabilityError(
            _GRANULARITAET_FEHLER.format(interval_minutes=interval_minutes)
        )

    tage = _tageskennzahlen(consumption, interval_minutes)
    if not tage:
        return []

    letzter = heute if heute is not None else tage[-1].tag
    fenster_start = letzter - timedelta(days=fenster_tage - 1)
    baseline_start = fenster_start - timedelta(days=baseline_tage)

    # Nur vollständige Tage vergleichen: ein angebrochener letzter Tag hat eine
    # kleinere Tagessumme, und der wäre sonst als Abwesenheit gemeldet.
    voll = [t for t in tage if t.slots >= _erwartete_slots(interval_minutes)]
    basis = [t for t in voll if baseline_start <= t.tag < fenster_start]
    fenster = [t for t in voll if fenster_start <= t.tag <= letzter]
    if len(basis) < MIN_BASELINE_TAGE or not fenster:
        return []

    # Markiert wird über BASIS UND FENSTER, gemeldet nur, was das Fenster
    # berührt. Der Grund ist der Beginn eines Ereignisses: würde nur über die
    # Fenstertage markiert, wäre ``von`` nicht der wahre Anfang, sondern die
    # Fensterkante — und die wandert mit jedem Lauf einen Tag weiter. Ein
    # dauerhaft laufendes Gerät ergäbe dadurch jeden Tag ein „neues" Ereignis
    # mit neuem Schlüssel und damit eine neue Mail. Nachgestellt: 12 Mails in
    # 12 Tagen, auch nachdem der Haushalt geantwortet hatte.
    alle = basis + fenster
    markierungen = _markiere(alle, basis, k_sigma)
    return _zu_ereignissen(markierungen, alle, basis, fenster_start=fenster_start)


# --- Tages-Kennzahlen ---------------------------------------------------------


def _erwartete_slots(interval_minutes: int) -> int:
    return max(1, int(24 * 60 / interval_minutes))


def _tageskennzahlen(
    consumption: list[tuple[datetime, float]], interval_minutes: int
) -> list[_Tag]:
    per_hour = 60 / interval_minutes
    roh: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
    for ts, v in consumption:
        roh[ts.date()].append((ts, v))

    tage: list[_Tag] = []
    for tag in sorted(roh):
        punkte = roh[tag]
        werte = [v for _, v in punkte]
        stunden_kwh = [0.0] * 24
        nacht: list[float] = []
        for ts, v in punkte:
            stunden_kwh[ts.hour] += v
            if ts.hour in _NIGHT:
                nacht.append(v)
        peak_slot = max(werte)
        peak_stunde = max(punkte, key=lambda p: p[1])[0].hour
        tage.append(
            _Tag(
                tag=tag,
                kwh=round(sum(werte), 4),
                stunden_kwh=tuple(round(x, 4) for x in stunden_kwh),
                nacht_w=int(round(_median(nacht) * per_hour * 1000)) if nacht else 0,
                grundlast_kw=round(_quantil(werte, 0.1) * per_hour, 4),
                peak_kw=round(peak_slot * per_hour, 4),
                peak_stunde=peak_stunde,
                slots=len(punkte),
            )
        )
    return tage


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def _quantil(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def _robuste_grenze(werte: list[float], k: float) -> float:
    """Median + k·MAD·1,4826, mit Standardabweichung als Ersatz bei MAD = 0.

    **Ohne messbare Streuung fällt die Grenze auf den Median** — nicht auf
    unendlich. Das ist kein Detail: die Nacht-Grundlast eines Haushalts ist
    typischerweise über Wochen auf wenige Watt konstant, und eine Grenze von
    unendlich hieße, dass gerade die gleichmäßigsten Haushalte nie einen
    Alarm bekommen können. Die statistische Bedingung wird dann neutral, und
    die Entscheidung tragen die beiden anderen Bedingungen jeder Regel (eine
    absolute und eine relative Mindesthöhe) — die den Fall "eine Streuung von
    null, also ist jede Abweichung signifikant" davor bewahren, jeden
    Messfehler zu melden.
    """
    med = _median(werte)
    mad = _median([abs(w - med) for w in werte])
    if mad > 0:
        streuung = mad * MAD_ZU_SIGMA
    else:
        mittel = sum(werte) / len(werte)
        streuung = (sum((w - mittel) ** 2 for w in werte) / len(werte)) ** 0.5
    if streuung <= 0:
        return med
    return med + k * streuung


def _sigma_abstand(wert: float, werte: list[float]) -> float:
    med = _median(werte)
    mad = _median([abs(w - med) for w in werte])
    streuung = mad * MAD_ZU_SIGMA
    if streuung <= 0:
        mittel = sum(werte) / len(werte)
        streuung = (sum((w - mittel) ** 2 for w in werte) / len(werte)) ** 0.5
    if streuung <= 0:
        return 0.0
    return round(abs(wert - med) / streuung, 2)


# --- Regeln -------------------------------------------------------------------


def _markiere(
    fenster: list[_Tag], basis: list[_Tag], k: float
) -> dict[date, set[str]]:
    """Welcher Tag trägt welche Ereignisart? Drei Bedingungen je Art."""
    basis_kwh = [t.kwh for t in basis]
    basis_nacht = [float(t.nacht_w) for t in basis]
    med_kwh = _median(basis_kwh)
    med_nacht = _median(basis_nacht)
    med_peak = _median([t.peak_kw for t in basis])
    max_peak = max(t.peak_kw for t in basis)

    grenze_kwh = _robuste_grenze(basis_kwh, k)
    grenze_nacht = _robuste_grenze(basis_nacht, k)

    markierungen: dict[date, set[str]] = defaultdict(set)
    for t in fenster:
        hoch = (
            t.kwh > grenze_kwh
            and t.kwh > med_kwh * HOCH_MIN_REL
            and t.kwh - med_kwh > HOCH_MIN_ABS_KWH
        )
        if hoch:
            markierungen[t.tag].add(VERBRAUCH_HOCH)

        abwesend = (
            t.kwh < med_kwh * ABWESEND_MAX_ANTEIL
            and med_peak > 0
            and t.peak_kw < med_peak * ABWESEND_MAX_PEAK_ANTEIL
        )
        if abwesend:
            markierungen[t.tag].add(ABWESENHEIT)

        # Die Nachtlast wird NICHT separat gemeldet, wenn ohnehin der ganze Tag
        # hoch ist: das ist ein Ereignis mit einer 24-Stunden-Signatur, keine
        # zwei. Die betroffenen Stunden zeigen die Nacht dann mit.
        #
        # An einem Abwesenheitstag ebenfalls nicht: dort steigt der
        # Nacht-Median regelmäßig, weil der Tagesbetrieb fehlt, der ihn sonst
        # drückt — das ist eine Folge der Abwesenheit, kein neues Gerät. (An
        # der realen Serie am 23.05.2026 aufgefallen: Abwesenheit und
        # "+60 W neue Dauerlast" für denselben Tag.)
        if (
            not hoch
            and not abwesend
            and t.nacht_w > grenze_nacht
            and t.nacht_w - med_nacht > NACHT_MIN_ABS_W
            and t.nacht_w > med_nacht * (1 + NACHT_MIN_REL)
        ):
            markierungen[t.tag].add(DAUERLAST_NACHT)

        if t.peak_kw > max_peak * SPITZE_MIN_FAKTOR and t.peak_kw > SPITZE_MIN_KW:
            markierungen[t.tag].add(NEUE_SPITZE)

    return markierungen


def _zu_ereignissen(
    markierungen: dict[date, set[str]],
    tage_alle: list[_Tag],
    basis: list[_Tag],
    *,
    fenster_start: date,
) -> list[Ereignis]:
    """Bündelt aufeinanderfolgende Tage gleicher Art zu einem Ereignis.

    Fünf heiße Tage hintereinander sind eine Nachricht, nicht fünf.

    Gebündelt wird über den GESAMTEN Zeitraum (Vergleichstage eingeschlossen),
    gemeldet wird nur, was bis ins Beobachtungsfenster reicht. So trägt jedes
    Ereignis seinen wahren Beginn — und behält ihn über die Läufe hinweg, was
    die Melde-Marke des Aufrufers erst funktionsfähig macht.
    """
    nach_tag = {t.tag: t for t in tage_alle}
    med_kwh = _median([t.kwh for t in basis])
    med_nacht = _median([float(t.nacht_w) for t in basis])
    med_stunden = [
        _median([t.stunden_kwh[h] for t in basis]) for h in range(24)
    ]
    max_peak = max(t.peak_kw for t in basis)
    basis_kwh = [t.kwh for t in basis]
    basis_nacht = [float(t.nacht_w) for t in basis]

    ereignisse: list[Ereignis] = []
    for art in EREIGNISARTEN:
        tage = sorted(d for d, arten in markierungen.items() if art in arten)
        for block in _bloecke(tage):
            # Nur Blöcke, die bis ins Beobachtungsfenster reichen. Was davor
            # endete, ist Vergangenheit und wurde (falls nötig) längst gemeldet.
            if block[-1] < fenster_start:
                continue
            if art == ABWESENHEIT and len(block) < ABWESEND_MIN_TAGE:
                continue
            ereignisse.append(
                _baue(
                    art,
                    block,
                    nach_tag,
                    med_kwh=med_kwh,
                    med_nacht=med_nacht,
                    med_stunden=med_stunden,
                    max_peak=max_peak,
                    basis_kwh=basis_kwh,
                    basis_nacht=basis_nacht,
                )
            )
    return sorted(ereignisse, key=lambda e: (e.von, e.typ))


def _bloecke(tage: list[date]) -> list[list[date]]:
    """Zerlegt eine sortierte Datumsliste in zusammenhängende Blöcke."""
    if not tage:
        return []
    bloecke = [[tage[0]]]
    for d in tage[1:]:
        if d - bloecke[-1][-1] == timedelta(days=1):
            bloecke[-1].append(d)
        else:
            bloecke.append([d])
    return bloecke


def _baue(
    art: str,
    block: list[date],
    nach_tag: dict[date, _Tag],
    *,
    med_kwh: float,
    med_nacht: float,
    med_stunden: list[float],
    max_peak: float,
    basis_kwh: list[float],
    basis_nacht: list[float],
) -> Ereignis:
    tage = [nach_tag[d] for d in block]
    kwh_tag = round(sum(t.kwh for t in tage) / len(tage), 2)

    if art == DAUERLAST_NACHT:
        zusatz_w = int(round(_median([t.nacht_w - med_nacht for t in tage])))
        nacht_stunden = len(_NIGHT)
        return Ereignis(
            typ=art,
            von=block[0],
            bis=block[-1],
            tage=len(block),
            stunden=tuple(sorted(_NIGHT)),
            zusatz_leistung_w=zusatz_w,
            baseline_leistung_w=int(round(med_nacht)),
            zusatz_kwh=round(zusatz_w / 1000 * nacht_stunden * len(block), 2),
            kwh_tag=kwh_tag,
            baseline_kwh_tag=round(med_kwh, 2),
            staerke=_sigma_abstand(
                _median([float(t.nacht_w) for t in tage]), basis_nacht
            ),
        )

    if art == VERBRAUCH_HOCH:
        zusatz = round(sum(t.kwh - med_kwh for t in tage), 2)
        stunden = _auffaellige_stunden(tage, med_stunden)
        # Die mittlere Zusatzleistung über die betroffenen Stunden — die Zahl,
        # an der ein Haushalt ein Gerät wiedererkennt.
        dauer_h = max(1, len(stunden)) * len(block)
        return Ereignis(
            typ=art,
            von=block[0],
            bis=block[-1],
            tage=len(block),
            stunden=stunden,
            zusatz_kwh=zusatz,
            zusatz_leistung_w=int(round(zusatz / dauer_h * 1000)),
            baseline_leistung_w=int(round(med_nacht)),
            kwh_tag=kwh_tag,
            baseline_kwh_tag=round(med_kwh, 2),
            staerke=_sigma_abstand(max(t.kwh for t in tage), basis_kwh),
        )

    if art == ABWESENHEIT:
        # Die Sockel-Leistung kommt aus der GEMESSENEN Tagesenergie, nicht aus
        # dem Median der Nachtwerte. Der Unterschied ist keine Feinheit: ein
        # taktendes Kühlgerät (52 W aus, 176 W an) hat einen Median, der je
        # nach Einschaltdauer auf dem einen oder dem anderen Wert liegt, nie
        # dazwischen. Nachgemessen an vier Einschaltquoten lag die
        # Median-Hochrechnung zwischen 27 % zu niedrig und 36 % zu hoch; der
        # Energieweg trifft auf unter 0,5 %.
        sockel_w = int(round(kwh_tag / 24 * 1000))
        return Ereignis(
            typ=art,
            von=block[0],
            bis=block[-1],
            tage=len(block),
            stunden=(),
            zusatz_kwh=0.0,
            zusatz_leistung_w=sockel_w,
            baseline_leistung_w=int(round(med_nacht)),
            kwh_tag=kwh_tag,
            baseline_kwh_tag=round(med_kwh, 2),
            staerke=_sigma_abstand(min(t.kwh for t in tage), basis_kwh),
        )

    spitzen_tag = max(tage, key=lambda t: t.peak_kw)
    return Ereignis(
        typ=art,
        von=block[0],
        bis=block[-1],
        tage=len(block),
        stunden=(spitzen_tag.peak_stunde,),
        peak_kw=spitzen_tag.peak_kw,
        baseline_peak_kw=round(max_peak, 2),
        kwh_tag=kwh_tag,
        baseline_kwh_tag=round(med_kwh, 2),
        staerke=round(spitzen_tag.peak_kw / max_peak, 2) if max_peak else 0.0,
    )


def _auffaellige_stunden(
    tage: list[_Tag], med_stunden: list[float]
) -> tuple[int, ...]:
    """Stunden, in denen der Mehrverbrauch tatsächlich sitzt.

    Gemessen wird jede Stunde gegen ihren EIGENEN üblichen Wert, nicht gegen
    die stärkste Stunde des Tages. Der Unterschied ist die Deutung: an einem
    Tag, an dem rund um die Uhr 400 W mehr laufen, hat trotzdem eine Stunde
    den höchsten Mehrverbrauch — ein Vergleich gegen dieses Maximum wählte
    daraus vier Einzelstunden aus und ließe die Signatur wie "ein Gerät am
    Abend" aussehen statt wie die Dauerlast, die sie ist (an einem realen
    Hitzetag im Juni 2026 aufgefallen).

    Zwei Bedingungen, wie überall: relativ (30 % über dem Üblichen) und
    absolut (mindestens 0,05 kWh = 200 W über die Stunde) — sonst schlagen
    Nachtstunden mit winziger Baseline schon bei Messrauschen an.
    """
    mehr = [
        sum(t.stunden_kwh[h] for t in tage) / len(tage) - med_stunden[h]
        for h in range(24)
    ]
    return tuple(
        h
        for h in range(24)
        if mehr[h] >= STUNDE_BETROFFEN_MIN_KWH
        and mehr[h] >= med_stunden[h] * STUNDE_BETROFFEN_MIN_REL
    )
