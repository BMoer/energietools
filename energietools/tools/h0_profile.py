# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""H0-Standardlastprofil-Synthesizer.

Für Spot-Tarif-Schätzungen braucht man bei Haushalten OHNE Smart-Meter-Daten ein
repräsentatives Lastprofil, um EPEX-Stundenpreise korrekt zu gewichten (Haushalte
verbrauchen abends mehr — genau dann, wenn Spot teuer ist).

Dies ist eine **Approximation** des österreichischen APCS-H0-Profils:
- charakteristische Tagesform (24 Stundengewichte),
- saisonale Monatsskalierung (Winter höher),
- leichte Wochenend-Dämpfung.

Es ist NICHT das voll-dynamisierte APCS-Profil (4.-Grad-Polynom je Tagtyp),
reicht aber für eine faire, repräsentative Spot-Schätzung. Liegen echte
Verbrauchsdaten vor, werden diese immer bevorzugt.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Relative Stundengewichte eines typischen Haushaltstags (werden normiert).
# Nacht niedrig, Morgenanstieg, Mittagsplateau, klarer Abend-Peak.
_HOURLY_SHAPE = (
    0.55, 0.48, 0.45, 0.44, 0.45, 0.52,  # 00–05
    0.70, 0.95, 1.05, 1.05, 1.02, 1.05,  # 06–11
    1.10, 1.02, 0.95, 0.95, 1.05, 1.20,  # 12–17
    1.45, 1.55, 1.45, 1.20, 0.90, 0.68,  # 18–23
)

# Saisonale Monatsfaktoren (Jan=Index 1). Winter höher (Licht/Heizungshilfen).
_MONTH_FACTOR = (
    0.0,  # Platzhalter Index 0
    1.16, 1.12, 1.05, 0.96, 0.89, 0.85,
    0.85, 0.87, 0.94, 1.03, 1.11, 1.17,
)

_WEEKEND_FACTOR = 1.02  # Wochenende leicht höher (ganztägig zu Hause)


def _raw_weight(ts: datetime) -> float:
    base = _HOURLY_SHAPE[ts.hour] * _MONTH_FACTOR[ts.month]
    if ts.weekday() >= 5:
        base *= _WEEKEND_FACTOR
    return base


def synthesize_h0_consumption(
    annual_kwh: float, start: datetime, end: datetime,
) -> list[dict]:
    """Erzeugt ein stündliches H0-Lastprofil über [start, end).

    Der Gesamtverbrauch über den Zeitraum entspricht exakt ``annual_kwh``
    (skaliert nicht auf die Zeitraumlänge — der Aufrufer übergibt für ein
    Vergleichsjahr genau ein Jahr).

    Returns:
        Liste von {timestamp: ISO-string, kwh: float}, stündlich, aufsteigend.

    Raises:
        ValueError: bei annual_kwh <= 0 oder leerem Zeitraum.
    """
    if annual_kwh <= 0:
        raise ValueError(f"annual_kwh muss > 0 sein, war {annual_kwh}")
    if end <= start:
        raise ValueError("end muss nach start liegen")

    # Stündliche Stützpunkte + Rohgewichte
    points: list[tuple[datetime, float]] = []
    cur = start
    while cur < end:
        points.append((cur, _raw_weight(cur)))
        cur += timedelta(hours=1)

    total_weight = sum(w for _, w in points)
    if total_weight <= 0:
        raise ValueError("Summe der Lastgewichte ist 0")

    return [
        {"timestamp": ts.isoformat(), "kwh": annual_kwh * w / total_weight}
        for ts, w in points
    ]
