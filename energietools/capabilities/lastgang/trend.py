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

Aus den Fenster-YoY-Deltas (Fallback: der einzelnen Kalender-YoY) leitet
:func:`compute_load_trend` eine deterministische Trend-Aussage ab (F12) —
kein LLM, Median der ``delta_pct``-Werte.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from statistics import median

# Ledger-F11: ab so vielen abgedeckten Kalendertagen gilt ein Jahr als "voll"
# genug für einen echten Kalender-YoY-Vergleich.
FULL_YEAR_DAY_THRESHOLD = 360

# Q15-Annahme für die "gemeinsame_tage"-Diagnosezahl (Slots/96). Die Capability
# erwartet 15-min-Auflösung (Spec L.2.2); bei gröberer Eingabe ist dieses Feld
# nur eine Näherung — delta_pct selbst ist granularitätsunabhängig (Formel
# arbeitet auf Summen, nicht auf Slot-Zahlen).
_SLOTS_PRO_TAG_Q15 = 96


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
    """Deckungsgleicher Fenster-Vergleich zweier benachbarter Jahre."""

    von_jahr: int
    bis_jahr: int
    gemeinsame_slots: int
    gemeinsame_tage: float
    kwh_a: float
    kwh_b: float
    delta_pct: float | None


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
    return WindowYoY(
        von_jahr=jahr_a,
        bis_jahr=jahr_b,
        gemeinsame_slots=len(gemeinsame_keys),
        gemeinsame_tage=round(len(gemeinsame_keys) / _SLOTS_PRO_TAG_Q15, 1),
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


def compute_load_trend(consumption: list[tuple[datetime, float]]) -> LoadTrendCompute:
    """Baut den vollständigen Mehrjahres-Trend: Jahres-Kennzahlen,
    Coverage-geguardete Kalender-YoY, Fenster-YoY über alle Jahrespaare und
    die daraus abgeleitete Trend-Aussage (L.2.3).
    """
    jahre = per_year(consumption)
    cal_yoy, verweigert_grund = _calendar_yoy(jahre)

    jahre_sortiert = [j.jahr for j in jahre]
    fenster: list[WindowYoY] = []
    for a, b in zip(jahre_sortiert, jahre_sortiert[1:]):
        w = aligned_window_yoy(consumption, a, b)
        if w is not None:
            fenster.append(w)

    deltas = [w.delta_pct for w in fenster if w.delta_pct is not None]
    if not deltas and cal_yoy is not None:
        deltas = [cal_yoy.delta_pct]

    trend_aussage, trend_pct = _trend_aussage(deltas)

    return LoadTrendCompute(
        per_year=jahre,
        calendar_yoy=cal_yoy,
        calendar_yoy_verweigert_grund=verweigert_grund,
        window_yoy=fenster,
        trend_pct_pro_jahr=trend_pct,
        trend_aussage=trend_aussage,
    )
