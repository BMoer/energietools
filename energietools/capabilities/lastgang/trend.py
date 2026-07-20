# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Rechen-Kern des Mehrjahres-Trends (L.2, Port von
``gridbert/analysen/09_lastgang/analysis_09.py:73-180`` — ``_per_year``,
``_aligned_window_yoy``, ``FULL_YEAR_DAY_THRESHOLD``).

**Coverage-Guard (F11):** ein echter Kalenderjahres-Vergleich (Kalender-YoY)
ist nur ehrlich, wenn BEIDE Jahre voll abgedeckt sind — sonst vergleicht man
ein Teiljahr gegen ein Volljahr (z.B. ein unterjähriges Q15-Opt-in: viele
Slots, aber wenige Kalendertage). Deshalb zählt „abgedeckt" über
``len(set(dt.date()))`` (verschiedene Kalendertage), NICHT über die
Slot-Anzahl. Ab ``FULL_YEAR_DAY_THRESHOLD`` (360) gilt ein Jahr als voll.

Wenn keine 2 vollen Jahre vorliegen, tritt die **Fenster-YoY** ein: nur
(Monat,Tag,Std,Min)-Slots, die in BEIDEN Jahren existieren, werden verglichen
— ein ehrlicher Vergleich trotz Teiljahr/Schalttag (``_aligned_window_yoy``).

**Mindest-Deckungs-Guard je Fenster (Korrektheits-Fix 2026-07-20):** ein
Fenster kann rein rechnerisch schon ab EINEM gemeinsamen Slot existieren
(z.B. ein einzelner Grenz-Slot am Jahreswechsel) — ``delta_pct`` ist dann
eine Zufallszahl aus zwei fast beliebigen Einzelwerten, keine belastbare
Jahresrate. Deshalb zählt ein Fenster erst ab ``MIN_TREND_FENSTER_TAGE``
gemeinsamen Kalendertagen (``gemeinsame_tage``, s.u.) in den Median; schwache
Fenster bleiben in ``window_yoy`` sichtbar (Transparenz), tragen aber
``in_trend=False`` + einen ``grund`` und fließen NICHT in
``trend_pct_pro_jahr``/``trend_aussage`` ein. Reale Regression: Bens Serie
hatte ein Fenster mit 4 Slots/0,0 Tagen Überlappung (+33,1 %) neben einem
Fenster mit 192,9 Tagen (+9,7 %) — der ungewichtete Median beider Werte ergab
eine falsche "~21 %/Jahr"-Aussage, obwohl nur der zweite Wert belastbar war.

``gemeinsame_tage`` zählt seit diesem Fix die echten, verschiedenen
Kalendertage (Monat/Tag) mit mindestens einem deckungsgleichen Slot —
granularitätsunabhängig (vorher: ``gemeinsame_slots / 96`` unter der
Annahme fixer Q15-Auflösung, was bei gröberer Eingabe — z.B. Tageswerten —
die Deckung um den Faktor 96 unterschätzte und den neuen Filter sonst auch
bei ausreichend abgedeckten Fenstern hätte auslösen lassen).

Aus den Fenster-YoY-Deltas der Fenster mit ``in_trend=True`` (Fallback: der
einzelnen Kalender-YoY) leitet :func:`compute_load_trend` eine
deterministische Trend-Aussage ab (F12) — kein LLM, Median der
``delta_pct``-Werte. Bleibt danach kein Fenster (und keine Kalender-YoY)
übrig, verweigert die Trend-Aussage ehrlich statt eine dünne Datenlage
kleinzureden.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from statistics import median

# Ledger-F11: ab so vielen abgedeckten Kalendertagen gilt ein Jahr als "voll"
# genug für einen echten Kalender-YoY-Vergleich.
FULL_YEAR_DAY_THRESHOLD = 360

# Korrektheits-Fix 2026-07-20: Mindest-Deckung, ab der ein Fenster-YoY in den
# Trend-Median darf. Begründung: darunter ist delta_pct statistisch wertlos
# (siehe Modul-Docstring, realer Fall "4 Slots/0,0 Tage -> +33,1 %"). 30 Tage
# = ein Kalendermonat gemeinsamer Überlappung — knapp genug, um echte
# unterjährige Wechsel (z.B. Einzug im Dezember) noch zuzulassen, aber breit
# genug, um Rand-/Einzel-Slot-Artefakte sicher auszuschließen.
MIN_TREND_FENSTER_TAGE = 30


@dataclass(frozen=True)
class JahresKennzahl:
    """kWh-Summe, Slot-Anzahl und abgedeckte Tage EINES Kalenderjahres (L.2.3)."""

    jahr: int
    kwh: float
    slots: int
    days: int
    full_year: bool
    von: str
    bis: str


@dataclass(frozen=True)
class CalendarYoY:
    """Echter Kalenderjahres-Vergleich — nur zwischen zwei VOLLEN Jahren."""

    von_jahr: int
    bis_jahr: int
    kwh_a: float
    kwh_b: float
    delta_pct: float


@dataclass(frozen=True)
class WindowYoY:
    """Deckungsgleicher Fenster-Vergleich zweier benachbarter Jahre.

    ``in_trend``/``grund`` (Korrektheits-Fix 2026-07-20): ``in_trend`` ist
    ``False``, wenn ``gemeinsame_tage < MIN_TREND_FENSTER_TAGE`` — das Fenster
    bleibt sichtbar (Transparenz), zählt aber nicht in
    ``trend_pct_pro_jahr``/``trend_aussage``. ``grund`` erklärt warum (sonst
    ``None``). Default ``True``/``None``, damit :func:`aligned_window_yoy`
    unverändert bleibt — die Bewertung passiert in :func:`compute_load_trend`,
    wo die Schwelle inhaltlich hingehört.
    """

    von_jahr: int
    bis_jahr: int
    gemeinsame_slots: int
    gemeinsame_tage: float
    kwh_a: float
    kwh_b: float
    delta_pct: float | None
    in_trend: bool = True
    grund: str | None = None


@dataclass(frozen=True)
class LoadTrendCompute:
    """Gebündeltes Ergebnis des Rechen-Kerns — die Capability-Hülle übersetzt
    das 1:1 in ``LoadTrendResult`` (Pydantic) + ergänzt Rechenweg/Caveats/Nenner."""

    per_year: list[JahresKennzahl]
    calendar_yoy: CalendarYoY | None
    calendar_yoy_verweigert_grund: str | None
    window_yoy: list[WindowYoY]
    trend_pct_pro_jahr: float | None
    trend_aussage: str | None


def per_year(consumption: list[tuple[datetime, float]]) -> list[JahresKennzahl]:
    """Je Kalenderjahr ``{kwh, slots, days, full_year, von, bis}`` (Port von
    ``_per_year``, ``analysis_09.py:73-93``).

    ``days`` = Anzahl verschiedener Kalendertage (``len(set(dt.date()))``),
    NICHT die Slot-Anzahl — ein unterjähriges Q15-Opt-in hat viele Slots, aber
    wenige Tage (Ledger-F11, DoD-Kriterium 5).
    """
    kwh: dict[int, float] = defaultdict(float)
    slots: dict[int, int] = defaultdict(int)
    tage: dict[int, set[date]] = defaultdict(set)
    for ts, wert in consumption:
        kwh[ts.year] += wert
        slots[ts.year] += 1
        tage[ts.year].add(ts.date())

    out: list[JahresKennzahl] = []
    for jahr in sorted(kwh):
        tage_jahr = tage[jahr]
        out.append(
            JahresKennzahl(
                jahr=jahr,
                kwh=round(kwh[jahr], 1),
                slots=slots[jahr],
                days=len(tage_jahr),
                full_year=len(tage_jahr) >= FULL_YEAR_DAY_THRESHOLD,
                von=min(tage_jahr).isoformat(),
                bis=max(tage_jahr).isoformat(),
            )
        )
    return out


def aligned_window_yoy(
    consumption: list[tuple[datetime, float]], jahr_a: int, jahr_b: int
) -> WindowYoY | None:
    """Deckungsgleiche YoY: nur (Monat,Tag,Std,Min)-Slots, die in BEIDEN
    Jahren existieren, werden summiert (Port von ``_aligned_window_yoy``,
    ``analysis_09.py:96-119``) — ehrlicher Vergleich trotz Teiljahr/Schalttag.

    Liefert ``None``, wenn die beiden Jahre keinen gemeinsamen Slot haben
    (z.B. disjunkte Zeiträume).

    ``gemeinsame_tage`` zählt die echten, verschiedenen (Monat,Tag)-Kombinationen
    unter den gemeinsamen Slots — NICHT ``gemeinsame_slots / 96``. Die alte
    Q15-Annahme unterschätzte die Deckung bei gröberer Eingabe (Tageswerte:
    1 Slot/Tag statt 96) um den Faktor 96 und wäre als Basis für den
    Mindest-Deckungs-Filter (``MIN_TREND_FENSTER_TAGE``) irreführend gewesen —
    ein voll abgedecktes Tageswert-Fenster hätte fälschlich als "zu dünn"
    gegolten. Die neue Zählung ist granularitätsunabhängig (Q15 wie Tageswert).
    """
    by_key: dict[int, dict[tuple[int, int, int, int], float]] = {jahr_a: {}, jahr_b: {}}
    for ts, wert in consumption:
        if ts.year not in (jahr_a, jahr_b):
            continue
        key = (ts.month, ts.day, ts.hour, ts.minute)
        jahres_dict = by_key[ts.year]
        jahres_dict[key] = jahres_dict.get(key, 0.0) + wert

    gemeinsame_keys = by_key[jahr_a].keys() & by_key[jahr_b].keys()
    if not gemeinsame_keys:
        return None

    summe_a = sum(by_key[jahr_a][k] for k in gemeinsame_keys)
    summe_b = sum(by_key[jahr_b][k] for k in gemeinsame_keys)
    gemeinsame_tage = len({(monat, tag) for monat, tag, _std, _min in gemeinsame_keys})
    return WindowYoY(
        von_jahr=jahr_a,
        bis_jahr=jahr_b,
        gemeinsame_slots=len(gemeinsame_keys),
        gemeinsame_tage=float(gemeinsame_tage),
        kwh_a=round(summe_a, 1),
        kwh_b=round(summe_b, 1),
        delta_pct=round(100 * (summe_b / summe_a - 1), 1) if summe_a else None,
    )


def _calendar_yoy(jahre: list[JahresKennzahl]) -> tuple[CalendarYoY | None, str | None]:
    """Kalender-YoY NUR bei >=2 vollen Jahren; nimmt die letzten zwei vollen
    Jahre (Port von ``analysis_09.py:170-177``). Sonst eine Begründung fürs
    Result (DoD-Kriterium 5: "Kalender-YoY verweigert, nur 1 volles Jahr")."""
    volle_jahre = [j.jahr for j in jahre if j.full_year]
    if len(volle_jahre) < 2:
        grund = (
            f"Kalender-YoY verweigert: nur {len(volle_jahre)} volle(s) Kalenderjahr(e) "
            f"(>= {FULL_YEAR_DAY_THRESHOLD} abgedeckte Tage) — Fenster-YoY (deckungsgleiche "
            "Slots) ist der einzige saubere Mehrjahresvergleich bei Teiljahren."
        )
        return None, grund

    a, b = volle_jahre[-2], volle_jahre[-1]
    kwh_a = next(j.kwh for j in jahre if j.jahr == a)
    kwh_b = next(j.kwh for j in jahre if j.jahr == b)
    delta_pct = round(100 * (kwh_b / kwh_a - 1), 1) if kwh_a else 0.0
    return CalendarYoY(von_jahr=a, bis_jahr=b, kwh_a=kwh_a, kwh_b=kwh_b, delta_pct=delta_pct), None


def _trend_aussage(deltas: list[float]) -> tuple[str | None, float | None]:
    """Deterministische Trend-Formulierung aus dem Median der Delta-Werte
    (F12) — kein LLM. Leer, wenn keine Jahrespaare existieren (nur 1 Jahr
    Daten: kein Trend berechenbar)."""
    if not deltas:
        return None, None
    pct = round(median(deltas), 1)
    gerundet = round(pct)
    if gerundet == 0:
        return f"Verbrauch bleibt ungefähr konstant (~{pct:+.1f} %/Jahr).", pct
    richtung = "steigt" if gerundet > 0 else "sinkt"
    return f"Verbrauch {richtung} ~{abs(gerundet)} %/Jahr.", pct


def _mit_deckungsflag(fenster: WindowYoY) -> WindowYoY:
    """Markiert ein Fenster als ``in_trend=False``, wenn seine Deckung unter
    ``MIN_TREND_FENSTER_TAGE`` liegt (Korrektheits-Fix 2026-07-20). Gibt sonst
    das Fenster unverändert zurück (``in_trend=True`` per Default)."""
    if fenster.gemeinsame_tage >= MIN_TREND_FENSTER_TAGE:
        return fenster
    grund = (
        f"Nur {fenster.gemeinsame_tage:g} gemeinsame Kalendertage zwischen "
        f"{fenster.von_jahr} und {fenster.bis_jahr} (Mindestdeckung: "
        f"{MIN_TREND_FENSTER_TAGE} Tage) — delta_pct wäre eine Zufallszahl aus "
        "zu wenig überlappenden Slots, fließt daher nicht in trend_pct_pro_jahr "
        "bzw. trend_aussage ein."
    )
    return replace(fenster, in_trend=False, grund=grund)


def compute_load_trend(consumption: list[tuple[datetime, float]]) -> LoadTrendCompute:
    """Baut den vollständigen Mehrjahres-Trend: Jahres-Kennzahlen,
    Coverage-geguardete Kalender-YoY, Fenster-YoY über alle Jahrespaare und
    die daraus abgeleitete Trend-Aussage (L.2.3).

    Jedes Fenster durchläuft den Mindest-Deckungs-Guard
    (``MIN_TREND_FENSTER_TAGE``, Korrektheits-Fix 2026-07-20): zu dünne
    Fenster bleiben in ``window_yoy`` sichtbar, tragen aber ``in_trend=False``
    und fließen nicht in den Median. Bleibt danach kein Fenster übrig UND
    keine Kalender-YoY existiert, verweigert die Trend-Aussage ehrlich statt
    einen dünnen Wert vorzutäuschen.
    """
    jahre = per_year(consumption)
    cal_yoy, verweigert_grund = _calendar_yoy(jahre)

    jahre_sortiert = [j.jahr for j in jahre]
    fenster: list[WindowYoY] = []
    for a, b in zip(jahre_sortiert, jahre_sortiert[1:]):
        w = aligned_window_yoy(consumption, a, b)
        if w is not None:
            fenster.append(_mit_deckungsflag(w))

    verbleibende_fenster = [w for w in fenster if w.in_trend]
    deltas = [w.delta_pct for w in verbleibende_fenster if w.delta_pct is not None]
    if not deltas and cal_yoy is not None:
        deltas = [cal_yoy.delta_pct]

    if not deltas and fenster and not verbleibende_fenster:
        # Es gab Fenster-Kandidaten, aber ALLE sind unter der Mindest-Deckung
        # ausgeschieden und keine Kalender-YoY konnte einspringen — ehrlich
        # verweigern statt einen dünnen/verzerrten Wert auszugeben (task-
        # Kriterium: "<1 Fenster übrig" nach dem Guard).
        anzahl = len(fenster)
        trend_aussage = (
            f"Zu wenig Deckung für eine Trend-Aussage: alle {anzahl} "
            f"Jahresfenster liegen unter der Mindestüberlappung von "
            f"{MIN_TREND_FENSTER_TAGE} gemeinsamen Kalendertagen "
            "(s. window_yoy[].grund je Fenster)."
        )
        trend_pct = None
    else:
        trend_aussage, trend_pct = _trend_aussage(deltas)

    return LoadTrendCompute(
        per_year=jahre,
        calendar_yoy=cal_yoy,
        calendar_yoy_verweigert_grund=verweigert_grund,
        window_yoy=fenster,
        trend_pct_pro_jahr=trend_pct,
        trend_aussage=trend_aussage,
    )
