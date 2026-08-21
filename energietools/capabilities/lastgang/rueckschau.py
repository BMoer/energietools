# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Geräte-Rückschau — was ist in den letzten zwölf Monaten passiert, seit der
Haushalt geantwortet hat?

Gegenstück zu :mod:`energietools.capabilities.lastgang.ereignisse` (findet im
7-Tage-Fenster gegen eine Baseline) und :mod:`…lastgang.deutung` (fragt, wenn
eine Signatur unbekannt ist): dieses Modul schaut **zurück**. Sobald ein
Haushalt eine Rückfrage aus ``deutung`` beantwortet hat — „das war das
Klimagerät, 142 W, nachts 0–4 Uhr" —, beantwortet ``rueckschau`` sofort die
nächste Frage: *wie oft war das in den letzten zwölf Monaten so, und was hat
es gekostet?*

**Warum es dieses Modul überhaupt gibt.** Ben, 20.08.2026: „aus usersicht ist
mir aktuell noch nicht klar warum ich das beantworten sollte […] es muss nicht
immer um einsparungen gehen, ich find es auch voll fein wenn die leute ihren
verbrauch einfach besser verstehen." Eine Rückfrage ohne Gegenleistung ist ein
Chore. Diese Rückschau ist die Gegenleistung — sie kostet den Haushalt nichts,
weil sie aus derselben Signatur entsteht, die er gerade bestätigt hat.

**Rollierend statt fest.** Ein Ruheniveau über ein ganzes Jahr zu mitteln
ignoriert die Jahreszeit — an Bens Serie liegt die Nacht-Grundlast im Jänner
bei 86 W und im August bei 116 W. Ein fester Jahreswert würde entweder den
ganzen Sommer als „neue Dauerlast" melden oder ein echtes Wintergerät
verschlucken. ``dauerlast_nacht`` vergleicht deshalb jeden Tag gegen das p20
seiner eigenen 30 Vortage, nicht gegen einen Jahreswert.

**Saisonfilter aus derselben Quelle wie die Frage.** Welche Monate zu einem
Kandidaten passen, steht schon in ``deutung.KANDIDATEN`` (Klimagerät →
Sommer, Wärmepumpe → Winter) — dieses Modul liest dieselbe Tabelle, statt eine
zweite Wahrheit zu pflegen. An Bens Serie warf das den 10.02. aus der
Klimagerät-Rückschau: eine echte Nachtlast an dem Tag, aber keine, die im
Februar ein Klimagerät gewesen sein kann.

**Abdeckung ist Tage mit Daten, nie Kalendertage.** Ein Jahr mit Lücken sieht
sonst aus wie ein Jahr mit wenig Verbrauch — der TEC-Fall (L30): fehlende
Messwerte wirken wie Nullverbrauch. Unter 60 Tagen mit Daten gibt es deshalb
gar keine Rückschau, sondern ``None``. Die JAHRES-Hochrechnung
(``kwh_jahr``/``eur_jahr``/``grundlast_anteil``) braucht mehr: an zwei
geprüften Haushaltsjahren (Nachprüfung 20.08.2026, Bens eigene Serie 2025 und
2026) liegt der Fehler bei 60-90 Tagen bei +12 bis +20 %, bei 120 Tagen hält
2025 (+6,3 %), 2026 aber noch nicht (+16,4 %) — erst ab ~165 Tagen liegt er in
BEIDEN Jahren durchgehend unter 7 %. Deshalb ``MIN_ABDECKUNG_TAGE_JAHR = 160``,
nicht 120 — eine an einem einzigen Haushaltsjahr kalibrierte Schwelle hätte
genau den Fehler wiederholt, den sie beheben sollte. Die reine
Vorkommens-Zählung (``tage_gesamt``/``kwh_gesamt``) steht davon unabhängig
schon ab 60 Tagen.

**Fenster rollierend, nie ein Kalenderjahr (Review 20.08.2026).** Ein festes
Kalenderjahr-Fenster (``von`` immer der 1.1.) fiel jedes Jahr am 1.1. auf
null: an Bens Serie lieferte ``rueckschau()`` mit heute=20.01. ``None``, die
erste Rückschau kam erst ab ~1.3., die erste Jahreszahl erst ab ~5.5. — genau
der Zeitraum, in dem die Gegenleistung am nötigsten gewesen wäre. Das Fenster
ist deshalb rollierend: die letzten ``TAGE_PRO_JAHR`` (365) Tage vor
``heute``, unabhängig vom Kalenderdatum. Ein explizites ``von`` überschreibt
den rollierenden Start und zielt auf ein bestimmtes Fenster (z.B. ein
einzelnes Kalenderjahr für einen Vorher-Nachher-Vergleich).

**Abwesenheit rechnet über die Energie, nie über einen Median.** Wie in
``ereignisse._baue``: der Sockel eines leeren Haushalts wird von einem
taktenden Kühlgerät dominiert, dessen Median auf einem der beiden Zustände
liegt, nie dazwischen. Hochgerechnet wird deshalb die gemessene Tagesenergie.

**Der Tagesbetrieb fehlte (NACHTRAG 1, Bens Einwand 20.08.2026 abends):**
„wir haben klima auch untertags betrieben." Wer nur die Signaturstunden zählt
(bei ``dauerlast_nacht`` die Nachtstunden), unterschätzt ein Gerät, das auch
tagsüber läuft, systematisch — an Bens Serie um Faktor 2 (5,4 statt 11,2 kWh).
Deshalb prüft ``dauerlast_nacht`` je Tag zusätzlich einen 24-h-Sockel: das
p20-Quantil ALLER Viertelstundenwerte des Tages, gegen dasselbe rollierende
Verfahren wie das Nachtniveau (p20 der 30 Vortage). Reißt der Sockel-Zusatz
dieselbe Schwelle wie die Nachtsignatur (``DAUERLAST_SIGNATUR_ANTEIL`` der
bestätigten Leistung), lief das Gerät rund um die Uhr; sonst nur in den
Signaturstunden. Ein roher, ungeprüfter Sockel ohne Schwelle wäre Rauschen:
an 12 winterlichen Tagen ohne jede Nachtlast hebt allein ein betriebsamer
Tag (weniger echte Ruheviertelstunden) den Sockel um 20–60 W — die Schwelle
(71 W bei Bens 142-W-Signatur) liegt sauber darüber; über alle 230 Tage 2026
reißt kein einziger Tag ohne Nachtlast die Sockel-Schwelle.

**Was diese Rückschau NICHT erfasst.** Erfasst ist, was sich vom übrigen
Verbrauch abhebt — läuft ein Gerät ständig (Tag UND Nacht, ohne erkennbaren
Zusatz gegenüber dem eigenen Ruheniveau), wird es selbst zum Sockel und
fällt heraus. Dieser Vorbehalt gehört in den Anzeigetext, nicht nur hierher.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.lastgang.deutung import KANDIDATEN, TAGE_PRO_JAHR
from energietools.capabilities.lastgang.ereignisse import (
    ABWESEND_MAX_ANTEIL,
    ABWESEND_MAX_PEAK_ANTEIL,
    ABWESENHEIT,
    DAUERLAST_NACHT,
    EREIGNISARTEN,
    HOCH_MIN_REL,
    K_SIGMA,
    MAD_ZU_SIGMA,
    NEUE_SPITZE,
    VERBRAUCH_HOCH,
    _erwartete_slots,
    _median,
    _quantil,
    _robuste_grenze,
    _Tag,
    _tageskennzahlen,
)
from energietools.capabilities.lastgang.granularitaet import GRANULARITAET_SCHWELLE_MIN

# --- Schwellen (dokumentiert, wie im Bestand — keine Magic Numbers) -----------

# Unter so vielen Tagen MIT Daten im Auswertungsfenster gibt es gar keine
# Rückschau (L30 aus dem TEC-Fall: fehlende Messwerte wirken wie
# Nullverbrauch). Gilt für die EXISTENZ der Rückschau (Vorkommens-Zählung
# tage_gesamt/kwh_gesamt) — für die JAHRES-Hochrechnung s.
# MIN_ABDECKUNG_TAGE_JAHR, deren Schwelle deutlich höher liegt.
MIN_ABDECKUNG_TAGE = 60

# Unter so vielen Tagen MIT Daten im Auswertungsfenster ist die JAHRES-
# Hochrechnung (kwh_jahr/eur_jahr/grundlast_anteil) zu unsicher, auch wenn die
# Rückschau selbst schon existiert (Review 20.08.2026, nachgeschärft in der
# Nachprüfung 20.08.2026). AN ZWEI HAUSHALTSJAHREN GEMESSEN, nicht nur einem:
# 2025 (Wahrheit 939,1 kWh/Jahr) hält 120 Tage mit +6,3 % — 2026 (Wahrheit
# 1000,2 kWh/Jahr) liegt bei exakt 120 Tagen (heute=2026-05-01) bei +16,4 %
# (1164,3 kWh) und erst ab ~165 Tagen durchgehend unter 7 %. Eine an 2025
# allein kalibrierte Schwelle (120) hätte einem Haushalt am 1.5.2026 also
# "rund 1.164,3 kWh im Jahr" statt der wahren ~1.000 kWh gezeigt — der
# Kommentar galt vorher nur für eines der beiden geprüften Jahre.
MIN_ABDECKUNG_TAGE_JAHR = 160

# Rollierendes Ruheniveau für dauerlast_nacht: p20 der 30 Tage davor, mit
# mindestens 10 Werten — sonst ist die Schwelle für diesen Tag geraten und er
# wird übersprungen (nicht auf 0 gesetzt, was ihn fälschlich träfe).
ROLLIEREND_TAGE = 30
ROLLIEREND_MIN_WERTE = 10

# Ein Tag trägt die dauerlast_nacht-Signatur, wenn die Zusatzlast mindestens
# die Hälfte der bestätigten Geräteleistung erreicht — die andere Hälfte ist
# Toleranz für Messrauschen und Alltag um das Gerät herum.
DAUERLAST_SIGNATUR_ANTEIL = 0.5

# Vergleichsfenster für abwesenheit: ±45 Tage um den Tag, derselbe Rhythmus,
# mit dem ein Haushalt normalerweise lebt (nicht ein fixer Vor-Zeitraum wie in
# der Alarm-Erkennung — hier gibt es kein "davor/danach", nur "das ganze Jahr").
ABWESENHEIT_FENSTER_TAGE = 45
# Mindestzahl Vergleichstage im ±45-Fenster, unter der der Median geraten
# wäre — am Rand der Serie (Jahresanfang/-ende) kann das Fenster dünn sein.
ABWESENHEIT_MIN_VERGLEICH_TAGE = 20

# Neue Spitze: die Signatur-Leistung (vom Haushalt bestätigt) ist der
# Referenzwert; 90 % davon zählen noch als "wieder so hoch" — exakt dieselbe
# Spitze wird durch Messrauschen sonst nie zweimal exakt erreicht.
SPITZE_SIGNATUR_ANTEIL = 0.9

_GRANULARITAET_FEHLER = (
    "Rückschau braucht Q15-Auflösung; interval_minutes={interval_minutes} "
    "(Tageswerte) ist zu grob."
)
_LEERER_LASTGANG_FEHLER = "Leerer Lastgang — keine Rückschau ableitbar."
_UNBEKANNTE_ART_FEHLER = "Unbekannte Ereignisart für die Rückschau: {typ!r}"
_DAUERLAST_OHNE_STUNDEN_FEHLER = (
    "dauerlast_nacht braucht mindestens eine Stunde in `stunden`, sonst ist "
    "die kWh-Rechnung (Zusatzlast × Stunden) nicht bestimmt."
)


# --- Ergebnis -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Vorkommen:
    """Ein zusammenhängender Zeitraum, in dem die Signatur getragen wurde.

    ``durchgehend`` (NACHTRAG 1) ist nur bei ``dauerlast_nacht`` bedeutsam:
    ``True``, wenn an ALLEN Tagen dieses Vorkommens auch der 24-h-Sockel die
    Signaturschwelle gerissen hat (Gerät lief rund um die Uhr, ``kwh`` zählt
    24 Stunden je Tag) — ``False``, wenn nur die Signaturstunden zählen. Ein
    Block bricht an der Stelle, wo sich der Wert ändert (s. ``_zu_vorkommen``),
    damit ``kwh`` innerhalb eines Vorkommens konsistent gerechnet ist. Bei
    allen anderen Ereignisarten immer ``False`` (ohne Bedeutung)."""

    von: date
    bis: date
    tage: int
    kwh: float
    leistung_w: int
    durchgehend: bool = False


@dataclass(frozen=True, slots=True)
class Rueckschau:
    """Alle Vorkommen einer bestätigten Signatur im Auswertungsfenster.

    ``von``/``bis`` sind das Auswertungsfenster — ein rollierendes 365-Tage-
    Fenster bis ``bis`` (kein Kalenderjahr mehr, Review 20.08.2026), außer ein
    explizites ``von`` hat es überschrieben. ``tage_mit_daten`` die
    tatsächliche Abdeckung darin — nie
    die Kalendertage (siehe Modul-Docstring, L30), UND abzüglich der Tage, die
    mangels Vortagen für ``dauerlast_nacht`` nicht geprüft werden konnten
    (Review 20.08.2026 — sonst behauptet das Feld volle Abdeckung, obwohl der
    Fensterkopf blind war). ``kwh_jahr``/``eur_jahr``/``grundlast_anteil``
    sind ausschließlich bei ``abwesenheit`` gesetzt, dem einzigen Ereignis,
    das eine Jahres-Hochrechnung trägt — ``grundlast_anteil`` ist NICHT der
    Anteil, den die Abwesenheitstage am Fensterverbrauch haben, sondern der
    Anteil, den die hochgerechnete Grundlast (``kwh_jahr``) am hochgerechneten
    Jahresverbrauch hat (s. ``_abwesenheit_hochrechnung``).

    ``tage_durchgehend``/``tage_nur_signaturstunden`` (NACHTRAG 1) summieren
    ``vorkommen[].tage`` nach ``durchgehend`` — nur bei ``dauerlast_nacht``
    aussagekräftig, bei allen anderen Arten ist ``tage_durchgehend`` immer 0.
    """

    typ: str
    label: str
    text: str
    von: date
    bis: date
    tage_mit_daten: int
    vorkommen: tuple[Vorkommen, ...]
    tage_gesamt: int
    kwh_gesamt: float
    eur_gesamt: float | None
    kwh_jahr: float | None
    eur_jahr: float | None
    grundlast_anteil: float | None
    monate: tuple[tuple[int, float], ...]
    verworfen_saison: int
    rechenweg: tuple[str, ...]
    tage_durchgehend: int = 0
    tage_nur_signaturstunden: int = 0


# --- Öffentliche API --------------------------------------------------------------


def rueckschau(
    consumption: list[tuple[datetime, float]],
    *,
    typ: str,
    leistung_w: int,
    stunden: tuple[int, ...],
    label: str = "",
    text: str = "",
    interval_minutes: int = 15,
    von: date | None = None,
    heute: date | None = None,
    arbeitspreis_ct_kwh: float | None = None,
) -> Rueckschau | None:
    """Sucht alle Vorkommen einer bestätigten Signatur im Auswertungsfenster.

    Args:
        consumption: (Zeitstempel, kWh)-Paare in Ortszeit (siehe
            ``ereignisse.finde_ereignisse``).
        typ: eine der ``EREIGNISARTEN`` aus ``ereignisse``.
        leistung_w: die vom Haushalt bestätigte Geräteleistung — Schwelle für
            ``dauerlast_nacht`` (Zusatzlast) und ``neue_spitze`` (Signatur-
            Peak); bei ``abwesenheit``/``verbrauch_hoch`` ohne Wirkung.
        stunden: die Stunden der Signatur — geht nur in die kWh-Formel von
            ``dauerlast_nacht`` ein (Zusatzlast × Stundenzahl).
        label: Kandidaten-Label aus ``deutung.KANDIDATEN`` für den
            Saisonfilter (z.B. "klimageraet"); leer/unbekannt = kein Filter.
        von: Fensterbeginn (Default: rollierend, ``heute`` minus
            ``TAGE_PRO_JAHR - 1`` Tage — kein Kalenderjahr mehr, Review
            20.08.2026). Explizit gesetzt zielt es auf ein bestimmtes Fenster
            (z.B. ein einzelnes Kalenderjahr für einen Vergleich).
        heute: letzter Tag des Auswertungsfensters (Default: letzter volle
            Tag der Serie).
        arbeitspreis_ct_kwh: ohne diesen Wert entstehen KEINE Euro-Felder.

    Returns:
        ``None`` bei unter ``MIN_ABDECKUNG_TAGE`` Tagen mit Daten im Fenster
        (dann ist jede Jahresaussage geraten) — sonst immer eine
        ``Rueckschau``, auch mit leerem ``vorkommen`` ("geprüft, nichts
        gefunden" ist ein anderes Ergebnis als "konnte nicht geprüft
        werden").

    Raises:
        CapabilityError: bei leerer Serie, zu grober Auflösung, unbekannter
            Ereignisart oder ``dauerlast_nacht`` ohne ``stunden``.
    """
    _validiere_eingabe(consumption, interval_minutes, typ, stunden)

    tage = _tageskennzahlen(consumption, interval_minutes)
    if not tage:
        return None
    voll = [t for t in tage if t.slots >= _erwartete_slots(interval_minutes)]
    if not voll:
        return None

    fenster_von, bis, fenster, tage_im_fenster = _abdeckung(voll, von, heute)

    nach_tag = {t.tag: t for t in voll}
    fenster_tage = {t.tag for t in fenster}
    # Nur für dauerlast_nacht gebraucht (NACHTRAG 1: 24-h-Sockel-Zweig) —
    # anderswo bleibt das Dict leer, das kostet nichts.
    sockel_by_tag = _tages_sockel(consumption, interval_minutes) if typ == DAUERLAST_NACHT else {}
    roh, uebersprungen_blind = _markiere(
        typ,
        voll,
        nach_tag,
        fenster_tage,
        leistung_w=leistung_w,
        stunden=stunden,
        sockel_by_tag=sockel_by_tag,
    )
    # Tage, die mangels Vortagen gar nicht geprüft werden konnten (Fensterkopf
    # bei dauerlast_nacht, s. Modul-Docstring), zählen NICHT als Abdeckung —
    # sonst behauptet tage_mit_daten volle Prüfung, wo in Wahrheit nie
    # hingeschaut wurde (Review 20.08.2026).
    tage_mit_daten = tage_im_fenster - uebersprungen_blind
    if tage_mit_daten < MIN_ABDECKUNG_TAGE:
        return None
    gefiltert, verworfen = _saison_filter(roh, label, typ)

    kwh_by_tag = {d: kwh for d, kwh, _, _ in gefiltert}
    leistung_by_tag = {d: w for d, _, w, _ in gefiltert}
    durchgehend_by_tag = {d: durchgehend for d, _, _, durchgehend in gefiltert}
    # KEIN ``ABWESEND_MIN_TAGE``-Filter hier: der Alarm verwirft einen
    # isolierten Tag, weil er als EINZELNE MAIL keine Nachricht wert ist
    # ("ein Tag außer Haus ist Alltag"). Die Rückschau zählt einen ganzen
    # Jahresverbrauch zusammen — ein einzelner gemessener Abwesenheitstag ist
    # dafür ein gültiger Messpunkt, kein Rauschen. An Bens Serie bestätigt:
    # die rohen Treffer (ohne diesen Filter) treffen exakt 25 Tage/68,5 kWh;
    # mit dem Alarm-Filter wären drei isolierte Tage (u.a. 19.05., 18.06.,
    # 03.07.) verschwunden und 25/68,5 wären 22/60,8 geworden.
    vorkommen = _zu_vorkommen(
        sorted(kwh_by_tag), kwh_by_tag, leistung_by_tag, durchgehend_by_tag, min_tage=1
    )

    tage_gesamt = sum(v.tage for v in vorkommen)
    kwh_gesamt = round(sum(v.kwh for v in vorkommen), 2)
    tage_durchgehend = sum(v.tage for v in vorkommen if v.durchgehend)
    tage_nur_signaturstunden = tage_gesamt - tage_durchgehend
    kept = {d for v in vorkommen for d in _tagesbereich(v.von, v.bis)}
    monate = _monate_verteilung(kept, kwh_by_tag)

    eur_gesamt = _eur(kwh_gesamt, arbeitspreis_ct_kwh, typ)
    kwh_jahr, eur_jahr, grundlast_anteil = _abwesenheit_hochrechnung(
        typ, kwh_gesamt, tage_gesamt, tage_mit_daten, fenster, arbeitspreis_ct_kwh
    )

    rechenweg = _rechenweg(
        typ,
        vorkommen=vorkommen,
        tage_gesamt=tage_gesamt,
        kwh_gesamt=kwh_gesamt,
        tage_durchgehend=tage_durchgehend,
        tage_nur_signaturstunden=tage_nur_signaturstunden,
        verworfen=verworfen,
        eur_gesamt=eur_gesamt,
        kwh_jahr=kwh_jahr,
        eur_jahr=eur_jahr,
        grundlast_anteil=grundlast_anteil,
        arbeitspreis_ct_kwh=arbeitspreis_ct_kwh,
    )

    return Rueckschau(
        typ=typ,
        label=label,
        text=text,
        von=fenster_von,
        bis=bis,
        tage_mit_daten=tage_mit_daten,
        vorkommen=vorkommen,
        tage_gesamt=tage_gesamt,
        kwh_gesamt=kwh_gesamt,
        eur_gesamt=eur_gesamt,
        kwh_jahr=kwh_jahr,
        eur_jahr=eur_jahr,
        grundlast_anteil=grundlast_anteil,
        monate=monate,
        verworfen_saison=verworfen,
        rechenweg=rechenweg,
        tage_durchgehend=tage_durchgehend,
        tage_nur_signaturstunden=tage_nur_signaturstunden,
    )


# --- Eingabe-Validierung -----------------------------------------------------------


def _validiere_eingabe(
    consumption: list[tuple[datetime, float]],
    interval_minutes: int,
    typ: str,
    stunden: tuple[int, ...],
) -> None:
    if not consumption:
        raise CapabilityError(_LEERER_LASTGANG_FEHLER)
    if interval_minutes >= GRANULARITAET_SCHWELLE_MIN:
        raise CapabilityError(
            _GRANULARITAET_FEHLER.format(interval_minutes=interval_minutes)
        )
    if typ not in EREIGNISARTEN:
        raise CapabilityError(_UNBEKANNTE_ART_FEHLER.format(typ=typ))
    if typ == DAUERLAST_NACHT and not stunden:
        raise CapabilityError(_DAUERLAST_OHNE_STUNDEN_FEHLER)


# --- Auswertungsfenster + Abdeckung -------------------------------------------------


def _abdeckung(
    voll: list[_Tag], von: date | None, heute: date | None
) -> tuple[date, date, list[_Tag], int]:
    """(Fensteranfang, Fensterende, volle Tage darin, Anzahl davon).

    Rollierendes Fenster statt Kalenderjahr (Review 20.08.2026, Modul-
    Docstring): das Fensterende ist ``heute`` (Default: letzter volle Tag der
    Serie), der Fensteranfang ``heute`` minus ``TAGE_PRO_JAHR - 1`` Tage —
    außer ein explizites ``von`` zielt auf ein bestimmtes Fenster. Anders als
    ein Kalenderjahr fällt das Fenster nie am 1.1. auf null: solange die
    Serie länger zurückreicht, trägt sie die Vorgeschichte über den
    Jahreswechsel mit.
    """
    bis = heute if heute is not None else voll[-1].tag
    fensteranfang = von if von is not None else bis - timedelta(days=TAGE_PRO_JAHR - 1)
    fenster = [t for t in voll if fensteranfang <= t.tag <= bis]
    return fensteranfang, bis, fenster, len(fenster)


# --- Signatur-Erkennung je Ereignisart ----------------------------------------------


def _markiere(
    typ: str,
    voll: list[_Tag],
    nach_tag: dict[date, _Tag],
    fenster_tage: set[date],
    *,
    leistung_w: int,
    stunden: tuple[int, ...],
    sockel_by_tag: dict[date, float],
) -> tuple[list[tuple[date, float, int, bool]], int]:
    """(Treffer, Anzahl Tage im Fenster, die NICHT geprüft werden konnten).

    Treffer: (Tag, kWh, W, durchgehend) — noch ohne Saisonfilter/Gruppierung.
    ``durchgehend`` ist nur bei ``dauerlast_nacht`` bedeutsam (NACHTRAG 1),
    sonst immer ``False``. Blinde Tage IN DIESEM RÜCKGABEWERT entstehen nur
    bei ``dauerlast_nacht`` (zu wenig Vortage fürs rollierende Ruheniveau, s.
    ``_markiere_dauerlast_nacht``) — für alle anderen Arten liefert diese
    Funktion hier fest 0. Das ist NICHT dasselbe wie „alle anderen Arten
    prüfen jeden Fenstertag": auch ``_markiere_abwesenheit`` überspringt Tage
    mit zu wenig Vergleichstagen (``ABWESENHEIT_MIN_VERGLEICH_TAGE``) still —
    nur meldet sie das nicht zurück, diese Tage bleiben deshalb in
    ``tage_mit_daten`` mitgezählt, obwohl an ihnen nie geprüft wurde
    (Nachprüfung 20.08.2026).
    """
    if typ == DAUERLAST_NACHT:
        return _markiere_dauerlast_nacht(
            nach_tag, fenster_tage, leistung_w, stunden, sockel_by_tag
        )
    if typ == ABWESENHEIT:
        return _markiere_abwesenheit(nach_tag, fenster_tage), 0
    fenster = [t for t in voll if t.tag in fenster_tage]
    if typ == VERBRAUCH_HOCH:
        return _markiere_verbrauch_hoch(fenster), 0
    return _markiere_neue_spitze(fenster, leistung_w), 0


def _tages_sockel(
    consumption: list[tuple[datetime, float]], interval_minutes: int
) -> dict[date, float]:
    """p20 ALLER Viertelstundenwerte (in Watt) je Kalendertag (NACHTRAG 1).

    Grundlage für den 24-h-Sockel: ein Dauerläufer hebt den Sockel rund um
    die Uhr an, eine Waschmaschine oder ein Backofen (kurz, oberer Bereich
    der Verteilung) tun das nicht. Auf ALLEN Tagen der Serie berechnet, nicht
    nur den vollen — die rollierende Baseline (``_pruefe_sockel_zusatz``)
    filtert unvollständige Tage über ``nach_tag`` selbst heraus."""
    per_hour = 60 / interval_minutes
    roh: dict[date, list[float]] = defaultdict(list)
    for ts, v in consumption:
        roh[ts.date()].append(v * per_hour * 1000)
    return {tag: _quantil(werte, 0.2) for tag, werte in roh.items()}


def _markiere_dauerlast_nacht(
    nach_tag: dict[date, _Tag],
    fenster_tage: set[date],
    leistung_w: int,
    stunden: tuple[int, ...],
    sockel_by_tag: dict[date, float],
) -> tuple[list[tuple[date, float, int, bool]], int]:
    """Rollierendes Ruheniveau: p20 der 30 Vortage, nicht ein fester Jahreswert
    (siehe Modul-Docstring — Bens Nacht-Grundlast schwankt 86 W → 116 W).

    Tage am Fensterkopf, die noch keine ``ROLLIEREND_MIN_WERTE`` Vortage
    haben, werden übersprungen (die Schwelle wäre geraten) — die Anzahl geht
    als zweiter Rückgabewert an den Aufrufer, der sie von ``tage_mit_daten``
    abzieht (Review 20.08.2026: sonst behauptet die Rückschau, an diesen
    Tagen geprüft zu haben, obwohl sie blind waren).

    NACHTRAG 1: reißt die Nachtsignatur, wird zusätzlich der 24-h-Sockel
    geprüft (``_pruefe_sockel_zusatz``) — reißt der ebenfalls dieselbe
    Schwelle, lief das Gerät durchgehend und ``kwh`` zählt 24 Stunden statt
    nur ``stunden``."""
    treffer: list[tuple[date, float, int, bool]] = []
    uebersprungen = 0
    for tag, heutiger in nach_tag.items():
        if tag not in fenster_tage:
            continue
        vortage = [
            nach_tag[tag - timedelta(days=i)].nacht_w
            for i in range(1, ROLLIEREND_TAGE + 1)
            if (tag - timedelta(days=i)) in nach_tag
        ]
        if len(vortage) < ROLLIEREND_MIN_WERTE:
            uebersprungen += 1
            continue
        ruhe = _quantil([float(w) for w in vortage], 0.2)
        zusatz_nacht = heutiger.nacht_w - ruhe
        if zusatz_nacht < DAUERLAST_SIGNATUR_ANTEIL * leistung_w:
            continue
        durchgehend, kwh, w = _pruefe_sockel_zusatz(
            tag, nach_tag, sockel_by_tag, leistung_w, zusatz_nacht, stunden
        )
        treffer.append((tag, kwh, w, durchgehend))
    return treffer, uebersprungen


def _pruefe_sockel_zusatz(
    tag: date,
    nach_tag: dict[date, _Tag],
    sockel_by_tag: dict[date, float],
    leistung_w: int,
    zusatz_nacht: float,
    stunden: tuple[int, ...],
) -> tuple[bool, float, int]:
    """(durchgehend, kWh, W) für einen Tag, der die Nachtsignatur schon trägt.

    Rollierende Baseline wie beim Nachtniveau: p20 der ``sockel_by_tag``-Werte
    der 30 Vortage (nur die, die auch in ``nach_tag`` — also vollständig —
    sind). Ohne genug Vortage oder ohne eigenen Sockelwert bleibt der Tag bei
    „nur Signaturstunden" — ein unbestimmbarer Sockel darf nie fälschlich
    „durchgehend" ergeben (fail-soft in dieselbe Richtung wie das Nachtniveau
    selbst)."""
    vortage = [
        sockel_by_tag[t]
        for i in range(1, ROLLIEREND_TAGE + 1)
        if (t := tag - timedelta(days=i)) in nach_tag and t in sockel_by_tag
    ]
    heutiger_sockel = sockel_by_tag.get(tag)
    if heutiger_sockel is not None and len(vortage) >= ROLLIEREND_MIN_WERTE:
        ruhe_sockel = _quantil(vortage, 0.2)
        sockel_zusatz = heutiger_sockel - ruhe_sockel
        if sockel_zusatz >= DAUERLAST_SIGNATUR_ANTEIL * leistung_w:
            kwh = round(sockel_zusatz * 24 / 1000, 4)
            return True, kwh, int(round(sockel_zusatz))
    kwh = round(zusatz_nacht * len(stunden) / 1000, 4)
    return False, kwh, int(round(zusatz_nacht))


def _markiere_abwesenheit(
    nach_tag: dict[date, _Tag], fenster_tage: set[date]
) -> list[tuple[date, float, int, bool]]:
    """Dieselben Kriterien wie die Alarm-Erkennung, aber gegen ein ±45-Tage-
    Vergleichsfenster statt eine feste Vorperiode — über ein Jahr gibt es kein
    "davor", nur den Rhythmus rundherum."""
    treffer: list[tuple[date, float, int, bool]] = []
    for tag, heutiger in nach_tag.items():
        if tag not in fenster_tage:
            continue
        umgebung = [
            nach_tag[tag + timedelta(days=i)]
            for i in range(-ABWESENHEIT_FENSTER_TAGE, ABWESENHEIT_FENSTER_TAGE + 1)
            if i != 0 and (tag + timedelta(days=i)) in nach_tag
        ]
        if len(umgebung) < ABWESENHEIT_MIN_VERGLEICH_TAGE:
            continue
        med_kwh = _median([u.kwh for u in umgebung])
        med_peak = _median([u.peak_kw for u in umgebung])
        if (
            heutiger.kwh < med_kwh * ABWESEND_MAX_ANTEIL
            and med_peak > 0
            and heutiger.peak_kw < med_peak * ABWESEND_MAX_PEAK_ANTEIL
        ):
            # Sockel aus der GEMESSENEN Energie, nicht aus einem Median über
            # taktende Werte (s. Modul-Docstring + ereignisse._baue).
            sockel_w = int(round(heutiger.kwh / 24 * 1000))
            treffer.append((tag, heutiger.kwh, sockel_w, False))
    return treffer


def _markiere_verbrauch_hoch(fenster: list[_Tag]) -> list[tuple[date, float, int, bool]]:
    """Median + 3·MAD·1,4826 UND mindestens das 1,4-fache des Medians."""
    kwh_werte = [t.kwh for t in fenster]
    if not kwh_werte:
        return []
    med = _median(kwh_werte)
    grenze = _robuste_grenze(kwh_werte, K_SIGMA)
    treffer: list[tuple[date, float, int, bool]] = []
    for t in fenster:
        if t.kwh > grenze and t.kwh > med * HOCH_MIN_REL:
            zusatz = round(t.kwh - med, 4)
            treffer.append((t.tag, zusatz, int(round(zusatz / 24 * 1000)), False))
    return treffer


def _markiere_neue_spitze(
    fenster: list[_Tag], leistung_w: int
) -> list[tuple[date, float, int, bool]]:
    """Tage mit mindestens 90 % der bestätigten Signatur-Spitzenleistung."""
    grenze_kw = SPITZE_SIGNATUR_ANTEIL * (leistung_w / 1000)
    treffer: list[tuple[date, float, int, bool]] = []
    for t in fenster:
        if t.peak_kw >= grenze_kw:
            treffer.append(
                (t.tag, t.stunden_kwh[t.peak_stunde], int(round(t.peak_kw * 1000)), False)
            )
    return treffer


# --- Saisonfilter (dieselbe Quelle wie deutung.KANDIDATEN) --------------------------


def _saison_monate(label: str, typ: str) -> tuple[int, ...] | None:
    for kandidat in KANDIDATEN:
        if kandidat.label == label and typ in kandidat.typen:
            return kandidat.monate
    return None


def _saison_filter(
    treffer: list[tuple[date, float, int, bool]], label: str, typ: str
) -> tuple[list[tuple[date, float, int, bool]], int]:
    monate = _saison_monate(label, typ)
    if monate is None:
        return treffer, 0
    behalten = [t for t in treffer if t[0].month in monate]
    return behalten, len(treffer) - len(behalten)


# --- Bündelung zu Vorkommen ---------------------------------------------------------


def _zu_vorkommen(
    tage: list[date],
    kwh_by_tag: dict[date, float],
    leistung_by_tag: dict[date, int],
    durchgehend_by_tag: dict[date, bool],
    *,
    min_tage: int,
) -> tuple[Vorkommen, ...]:
    """Fasst zusammenhängende Tage zu einem Vorkommen (wie ``ereignisse._bloecke``).

    Ein Block bricht zusätzlich, wo sich ``durchgehend`` ändert (NACHTRAG 1) —
    sonst würde ein Tag mit 24-h-Sockel und ein direkt folgender Tag ohne
    Sockel zu EINEM Vorkommen mit einer nicht mehr nachrechenbaren
    kWh-Mischung verschmelzen."""
    ergebnis: list[Vorkommen] = []
    for block in _bloecke_nach_flag(sorted(tage), durchgehend_by_tag):
        if len(block) < min_tage:
            continue
        kwh = round(sum(kwh_by_tag[d] for d in block), 4)
        leistung = int(round(sum(leistung_by_tag[d] for d in block) / len(block)))
        ergebnis.append(
            Vorkommen(
                von=block[0],
                bis=block[-1],
                tage=len(block),
                kwh=kwh,
                leistung_w=leistung,
                durchgehend=durchgehend_by_tag[block[0]],
            )
        )
    return tuple(ergebnis)


def _bloecke_nach_flag(tage: list[date], flag_by_tag: dict[date, bool]) -> list[list[date]]:
    """Wie ``ereignisse._bloecke`` (zusammenhängende Kalendertage), zusätzlich
    getrennt an jeder Stelle, wo sich ``flag_by_tag`` ändert."""
    bloecke: list[list[date]] = []
    for tag in tage:
        if (
            bloecke
            and (tag - bloecke[-1][-1]).days == 1
            and flag_by_tag[tag] == flag_by_tag[bloecke[-1][-1]]
        ):
            bloecke[-1].append(tag)
        else:
            bloecke.append([tag])
    return bloecke


def _tagesbereich(von: date, bis: date) -> list[date]:
    return [von + timedelta(days=i) for i in range((bis - von).days + 1)]


def _monate_verteilung(
    tage: Iterable[date], kwh_by_tag: dict[date, float]
) -> tuple[tuple[int, float], ...]:
    summe: dict[int, float] = defaultdict(float)
    for tag in tage:
        summe[tag.month] += kwh_by_tag[tag]
    return tuple((monat, round(summe[monat], 2)) for monat in sorted(summe))


# --- Preis + Jahres-Hochrechnung (nur abwesenheit) -----------------------------------


def _eur(kwh: float, preis: float | None, typ: str) -> float | None:
    """Keine Euro-Summe für neue_spitze — eine Spitze ist ein Leistungswert,
    kein Verbrauch (siehe Spec) —, sonst nur wenn ein Preis übergeben wurde."""
    if preis is None or typ == NEUE_SPITZE:
        return None
    return round(kwh * preis / 100, 2)


def _abwesenheit_hochrechnung(
    typ: str,
    kwh_gesamt: float,
    tage_gesamt: int,
    tage_mit_daten: int,
    fenster: list[_Tag],
    preis: float | None,
) -> tuple[float | None, float | None, float | None]:
    """kwh_jahr/eur_jahr/grundlast_anteil — ausschließlich bei ``abwesenheit``,
    und erst ab ``MIN_ABDECKUNG_TAGE_JAHR`` Tagen Abdeckung (Review
    20.08.2026 — unter der Schwelle ist die Jahres-Hochrechnung gemessen zu
    ungenau, s. ``MIN_ABDECKUNG_TAGE_JAHR``); die reine Vorkommens-Zählung
    (``tage_gesamt``/``kwh_gesamt``) bleibt davon unberührt.

    Der Weg geht über die Energie (Schnitt/Tag × 365), nicht über eine
    Leistung — s. Modul-Docstring. ``schnitt_tag`` ist die GRUNDLAST des
    Haushalts (was ein leerer Tag verbraucht); ``kwh_jahr`` ist deshalb NICHT
    der hochgerechnete Verbrauch der Abwesenheitstage selbst, sondern die
    Grundlast hochgerechnet aufs ganze Jahr — "wenn der Haushalt das ganze
    Jahr so leer liefe wie an den erkannten Tagen". ``grundlast_anteil`` ist
    ``schnitt_tag`` geteilt durch den mittleren Tagesverbrauch des GESAMTEN
    Auswertungsfensters (nicht nur der Abwesenheitstage) — der Anteil, den
    die hochgerechnete GRUNDLAST am hochgerechneten JAHRESVERBRAUCH hat.
    Das ist NICHT der Anteil, den die Abwesenheitstage am tatsächlich
    GEMESSENEN Fensterverbrauch haben (``kwh_gesamt`` / Fenstersumme) — diese
    zweite Zahl wäre deutlich kleiner und stand vor diesem Review fälschlich
    unter demselben Namen (Review 20.08.2026, an Bens Serie: 48,76 % Grundlast-
    Anteil versus 5,3 % tatsächlicher Anteil am Fensterverbrauch).
    """
    if typ != ABWESENHEIT or tage_gesamt == 0:
        return None, None, None
    if tage_mit_daten < MIN_ABDECKUNG_TAGE_JAHR:
        return None, None, None
    schnitt_tag = kwh_gesamt / tage_gesamt
    kwh_jahr = round(schnitt_tag * TAGE_PRO_JAHR, 1)
    eur_jahr = round(kwh_jahr * preis / 100, 2) if preis is not None else None
    if not fenster:
        return kwh_jahr, eur_jahr, None
    mittel_fenster = sum(t.kwh for t in fenster) / len(fenster)
    grundlast_anteil = round(schnitt_tag / mittel_fenster, 4) if mittel_fenster > 0 else None
    return kwh_jahr, eur_jahr, grundlast_anteil


# --- Rechenweg (No-LLM-Math: jede Zahl entsteht hier, nicht im Anzeigetext) ----------


def _rechenweg(
    typ: str,
    *,
    vorkommen: tuple[Vorkommen, ...],
    tage_gesamt: int,
    kwh_gesamt: float,
    tage_durchgehend: int,
    tage_nur_signaturstunden: int,
    verworfen: int,
    eur_gesamt: float | None,
    kwh_jahr: float | None,
    eur_jahr: float | None,
    grundlast_anteil: float | None,
    arbeitspreis_ct_kwh: float | None,
) -> tuple[str, ...]:
    zeilen = list(
        _rechenweg_kern(
            typ,
            vorkommen=vorkommen,
            tage_gesamt=tage_gesamt,
            kwh_gesamt=kwh_gesamt,
            tage_durchgehend=tage_durchgehend,
            tage_nur_signaturstunden=tage_nur_signaturstunden,
        )
    )
    if typ == ABWESENHEIT and kwh_jahr is not None:
        zeilen.append(
            f"Schnitt/Tag (= Grundlast): {_zahl(kwh_gesamt)} kWh / {tage_gesamt} Tage × "
            f"{TAGE_PRO_JAHR} = {_zahl(kwh_jahr)} kWh/Jahr."
        )
        if grundlast_anteil is not None and grundlast_anteil > 0:
            jahresverbrauch_hoch = round(kwh_jahr / grundlast_anteil, 1)
            zeilen.append(
                f"Grundlast-Anteil am hochgerechneten Jahresverbrauch: "
                f"{_zahl(grundlast_anteil * 100)} % ({_zahl(kwh_jahr)} / "
                f"{_zahl(jahresverbrauch_hoch)} kWh)."
            )
    if verworfen:
        zeilen.append(f"{verworfen} Treffer außerhalb der Saison verworfen.")
    if eur_gesamt is not None and arbeitspreis_ct_kwh is not None:
        zeilen.append(
            f"{_zahl(kwh_gesamt)} kWh × {_zahl(arbeitspreis_ct_kwh)} ct/kWh / 100 = "
            f"{_zahl(eur_gesamt)} €."
        )
    if eur_jahr is not None and arbeitspreis_ct_kwh is not None:
        zeilen.append(
            f"{_zahl(kwh_jahr)} kWh/Jahr × {_zahl(arbeitspreis_ct_kwh)} ct/kWh / 100 = "
            f"{_zahl(eur_jahr)} €/Jahr."
        )
    return tuple(zeilen)


def _rechenweg_dauerlast_nacht(
    vorkommen: tuple[Vorkommen, ...],
    *,
    tage_gesamt: int,
    kwh_gesamt: float,
    tage_durchgehend: int,
    tage_nur_signaturstunden: int,
) -> list[str]:
    """NACHTRAG 1: weist beide Zweige (durchgehend / nur Signaturstunden)
    getrennt aus — no-LLM-Math verlangt, dass jede Zahl hier entsteht, auch
    wenn ein Ereignis beide Zweige gleichzeitig enthält."""
    if tage_durchgehend == 0:
        return [
            f"{tage_gesamt} Nächte × Zusatzlast über dem Ruheniveau "
            f"(p{20} der {ROLLIEREND_TAGE} Vortage) = {_zahl(kwh_gesamt)} kWh "
            "(24-h-Sockel an keinem dieser Tage über der Schwelle — nur "
            "Signaturstunden)."
        ]
    kwh_durchgehend = round(sum(v.kwh for v in vorkommen if v.durchgehend), 4)
    kwh_nur_signatur = round(kwh_gesamt - kwh_durchgehend, 4)
    if tage_nur_signaturstunden == 0:
        return [
            f"{tage_durchgehend} Tage mit 24-h-Sockel über der Schwelle (Gerät lief "
            f"rund um die Uhr): Sockel-Zusatz × 24 h = {_zahl(kwh_durchgehend)} kWh."
        ]
    return [
        f"{tage_durchgehend} Tage mit 24-h-Sockel über der Schwelle (Gerät lief rund "
        f"um die Uhr): Sockel-Zusatz × 24 h = {_zahl(kwh_durchgehend)} kWh.",
        f"{tage_nur_signaturstunden} weitere Nächte nur in den Signaturstunden "
        f"(24-h-Sockel unter der Schwelle) = {_zahl(kwh_nur_signatur)} kWh.",
        f"Zusammen: {tage_gesamt} Tage, {_zahl(kwh_gesamt)} kWh.",
    ]


def _rechenweg_kern(
    typ: str,
    *,
    vorkommen: tuple[Vorkommen, ...],
    tage_gesamt: int,
    kwh_gesamt: float,
    tage_durchgehend: int,
    tage_nur_signaturstunden: int,
) -> list[str]:
    if typ == DAUERLAST_NACHT:
        return _rechenweg_dauerlast_nacht(
            vorkommen,
            tage_gesamt=tage_gesamt,
            kwh_gesamt=kwh_gesamt,
            tage_durchgehend=tage_durchgehend,
            tage_nur_signaturstunden=tage_nur_signaturstunden,
        )
    if typ == ABWESENHEIT:
        return [f"{tage_gesamt} Tage erkannt, Summe der Tagesverbräuche = {_zahl(kwh_gesamt)} kWh."]
    if typ == VERBRAUCH_HOCH:
        return [
            f"{tage_gesamt} Tage über Median + {K_SIGMA:g}·MAD·{MAD_ZU_SIGMA} UND "
            f"≥ {HOCH_MIN_REL:g}×Median, Mehrverbrauch = {_zahl(kwh_gesamt)} kWh."
        ]
    return [
        f"{tage_gesamt} Tage mit Spitze ≥ {int(SPITZE_SIGNATUR_ANTEIL * 100)} % der "
        f"Signatur-Leistung, Energie der Spitzenstunden = {_zahl(kwh_gesamt)} kWh "
        "(keine €-Summe — eine Spitze ist ein Leistungswert, kein Verbrauch)."
    ]


def _zahl(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")
