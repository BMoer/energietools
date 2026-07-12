# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Rechen-Kern der Lastgang-Signale (L.1, Port von
``gridbert/gridbert/insights/lastgang_signals.py``).

Leitet aus einem Verbrauchs-/Netzbezugs-Lastgang Ursachen-Hypothesen (Signale)
ab: elektrische Heizung (Winter/Sommer-Verhältnis), PV-Eigenverbrauch
(Mittags-Delle) und Dauerläufer (Nacht-Grundlast). Bewusst getrennt von
``tools.load_profile`` (Metriken/Anomalien) — hier nur die Ursachen-Hypothesen,
die :func:`select_rueckfragen` in gezielte Rückfragen übersetzt.

**Nacht-Fenster-Entscheidung (Ledger-F9, Spec L.1.5):** EIN „Nacht-Grundlast/
Dauerläufer"-Fenster = 00:00–04:59 (Stunden 0–4), NICHT das ältere
``range(1, 5)`` (01:00–04:59) der gridbert-Quelle. Grund: das committete
Referenz-Artefakt (Wallbox-Nächte-Zählung) nutzt bereits 0–5h; beide Zwecke
(Nacht-Grundlast-Signal + Wallbox-Nächte) sollen dasselbe Fenster teilen. Das
separate 22:00–04:00-Fenster von ``models/load_profile.py`` (``nacht_mean_kw``)
ist ein ANDERES Konzept (Nacht-Durchschnitt inkl. Abendtail) und bleibt
unangetastet (F7: Fenster nicht konflatieren).

Keine erfundenen Quoten — wo Daten fehlen (z.B. keine Winter- oder Sommertage
in der Serie), bleibt das Signal ``UNKNOWN``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from energietools.capabilities.base import CapabilityError

_WINTER_MONATE = (12, 1, 2)
_SOMMER_MONATE = (6, 7, 8)

# F9-Entscheidung (L.1.5): 00:00–04:59, vereinheitlicht mit der Wallbox-Nächte-
# Zählung (analysis_08.py:72 nutzt bereits ``hours=range(0, 5)``).
_NIGHT = range(0, 5)
NIGHT_FENSTER_LABEL = "00:00–04:59"

_MIDDAY = range(10, 16)
MIDDAY_FENSTER_LABEL = "10:00–15:59"

# Schwellen (heuristisch, dokumentiert — L.1.3, keine Magic Numbers im Code).
ELECTRIC_HEAT_RATIO = 2.5  # Winter/Sommer ab hier: elektrische Heizung wahrscheinlich
PV_DIP_RATIO = 0.85  # Mittag/Nacht darunter: PV-Eigenverbrauch wahrscheinlich
HIGH_BASE_W = 300  # Nacht-Grundlast darüber: Dauerläufer prüfen

_GRANULARITAET_FEHLER = (
    "Intraday-Signale brauchen Q15-Auflösung; interval_minutes={interval_minutes} "
    "(Tageswerte) ist zu grob für lastgang_signals."
)
_LEERER_LASTGANG_FEHLER = "Leerer Lastgang — keine Signale ableitbar."


class Signal(str, Enum):
    """Dreiwertige Hypothese: bestätigt / verneint / unbekannt."""

    LIKELY = "likely"
    UNLIKELY = "unlikely"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LastgangSignals:
    """Aus dem Lastgang abgeleitete Ursachen-Hypothesen (Roh, ungeguardet)."""

    winter_summer_ratio: float | None
    night_base_w: int
    midday_dip_ratio: float | None  # Ø Mittag / Ø Nacht
    evening_peak_hour: int
    weekday_weekend_ratio: float | None

    electric_heating: Signal
    pv_self_consumption: Signal
    high_continuous_load: Signal
    pv_feedin_kwh: float | None


@dataclass(frozen=True)
class Rueckfrage:
    """Eine durch ein Signal motivierte Rückfrage an den Haushalt."""

    feld: str  # Datenmodell-Feld, das die Antwort befüllt
    frage: str
    motiviert_durch: str  # welches Signal die Frage auslöst


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[len(s) // 2]


def compute_signals(
    consumption: list[tuple[datetime, float]],
    *,
    interval_minutes: int = 15,
    pv_feedin_kwh: float | None = None,
) -> LastgangSignals:
    """Leitet Interpretations-Signale aus dem summierten Verbrauch ab.

    Args:
        consumption: (Zeitstempel, kWh)-Liste des Netzbezugs/Verbrauchs.
        interval_minutes: Mess-Intervall (Standard Q15 = 15).
        pv_feedin_kwh: eingespeiste Überschuss-Energie, falls gemessen.

    Raises:
        CapabilityError: bei leerem Lastgang oder Tages-/Stundenauflösung
            (``interval_minutes >= 60`` — Granularitäts-Guard, Ledger-F29).
    """
    if not consumption:
        raise CapabilityError(_LEERER_LASTGANG_FEHLER)
    if interval_minutes >= 60:
        raise CapabilityError(_GRANULARITAET_FEHLER.format(interval_minutes=interval_minutes))

    per_hour = 60 / interval_minutes
    daily: dict[date, float] = defaultdict(float)
    hour_sum: dict[int, float] = defaultdict(float)
    hour_n: dict[int, int] = defaultdict(int)
    night_vals: list[float] = []
    midday_vals: list[float] = []
    weekday_total = 0.0
    weekend_total = 0.0
    weekday_days: set[date] = set()
    weekend_days: set[date] = set()

    for ts, v in consumption:
        d = ts.date()
        daily[d] += v
        hour_sum[ts.hour] += v
        hour_n[ts.hour] += 1
        if ts.hour in _NIGHT:
            night_vals.append(v)
        if ts.hour in _MIDDAY:
            midday_vals.append(v)
        if ts.weekday() >= 5:
            weekend_total += v
            weekend_days.add(d)
        else:
            weekday_total += v
            weekday_days.add(d)

    night_med = _median(night_vals)
    midday_med = _median(midday_vals)
    night_base_w = int(round(night_med * per_hour * 1000))
    midday_dip = (midday_med / night_med) if night_med > 0 else None

    ws_ratio = _winter_summer(daily)
    evening_peak = max(range(24), key=lambda h: (hour_sum[h] / hour_n[h]) if hour_n[h] else 0.0)
    ww_ratio = (
        (weekday_total / len(weekday_days)) / (weekend_total / len(weekend_days))
        if weekday_days and weekend_days and weekend_total
        else None
    )

    return LastgangSignals(
        winter_summer_ratio=round(ws_ratio, 2) if ws_ratio else None,
        night_base_w=night_base_w,
        midday_dip_ratio=round(midday_dip, 2) if midday_dip is not None else None,
        evening_peak_hour=evening_peak,
        weekday_weekend_ratio=round(ww_ratio, 2) if ww_ratio else None,
        electric_heating=_heat_signal(ws_ratio),
        pv_self_consumption=_pv_signal(midday_dip, pv_feedin_kwh),
        high_continuous_load=(Signal.LIKELY if night_base_w >= HIGH_BASE_W else Signal.UNLIKELY),
        pv_feedin_kwh=round(pv_feedin_kwh, 1) if pv_feedin_kwh is not None else None,
    )


def _winter_summer(daily: dict[date, float]) -> float | None:
    w = [v for d, v in daily.items() if d.month in _WINTER_MONATE]
    s = [v for d, v in daily.items() if d.month in _SOMMER_MONATE]
    if not w or not s:
        return None
    avg_s = sum(s) / len(s)
    return (sum(w) / len(w)) / avg_s if avg_s else None


def _heat_signal(ws_ratio: float | None) -> Signal:
    if ws_ratio is None:
        return Signal.UNKNOWN
    return Signal.LIKELY if ws_ratio >= ELECTRIC_HEAT_RATIO else Signal.UNLIKELY


def _pv_signal(midday_dip: float | None, feedin: float | None) -> Signal:
    if feedin is not None and feedin > 0:
        return Signal.LIKELY
    if midday_dip is None:
        return Signal.UNKNOWN
    return Signal.LIKELY if midday_dip < PV_DIP_RATIO else Signal.UNLIKELY


def select_rueckfragen(signals: LastgangSignals) -> list[Rueckfrage]:
    """Wählt die durch die Signale motivierten Rückfragen aus.

    Genau die Mehrdeutigkeiten, die der Lastgang offen lässt, werden zu
    Fragen (Port von ``lastgang_signals.py:180-226``). PV-bedingte Guards
    (L.1.4) werden NICHT hier, sondern von
    :func:`energietools.capabilities.lastgang.guards.guard_rueckfragen`
    nachgelagert angewendet — dieser Kern bleibt der reine, ungeguardete Port.
    """
    fragen: list[Rueckfrage] = []

    if signals.electric_heating is Signal.LIKELY:
        fragen.append(
            Rueckfrage(
                feld="asset.heating.type",
                frage=(
                    "Dein Winterverbrauch ist deutlich höher — heizt du mit Strom "
                    "(Wärmepumpe/Direktheizung) oder nur mehr Beleuchtung/Geräte?"
                ),
                motiviert_durch=f"winter_summer_ratio={signals.winter_summer_ratio}",
            )
        )
    elif signals.electric_heating is Signal.UNLIKELY:
        fragen.append(
            Rueckfrage(
                feld="asset.heating.type",
                frage=(
                    "Dein Stromverbrauch ist über das Jahr flach — heizt du mit "
                    "Gas/Fernwärme/Pellets (also nicht elektrisch)?"
                ),
                motiviert_durch=f"winter_summer_ratio={signals.winter_summer_ratio}",
            )
        )

    if signals.pv_self_consumption is Signal.LIKELY:
        fragen.append(
            Rueckfrage(
                feld="asset.pv.kwp",
                frage=(
                    "Tagsüber sinkt dein Netzbezug auffällig — hast du eine "
                    "PV-Anlage? Wie viel kWp, und gibt es einen Speicher? → dafür "
                    "bräuchten wir einen zweiten Consent für den Einspeise-Zählpunkt."
                ),
                motiviert_durch=(
                    f"midday_dip_ratio={signals.midday_dip_ratio}, "
                    f"feedin={signals.pv_feedin_kwh}"
                ),
            )
        )

    if signals.high_continuous_load is Signal.LIKELY:
        fragen.append(
            Rueckfrage(
                feld="asset.continuous_loads",
                frage=(
                    f"Nachts laufen konstant ~{signals.night_base_w} W durch — "
                    "gibt es Dauerverbraucher (Pool, Aquarium, Server, alter "
                    "Kühlschrank, Boiler)?"
                ),
                motiviert_durch=f"night_base_w={signals.night_base_w}",
            )
        )

    fragen.append(
        Rueckfrage(
            feld="behavior.appliance_timing",
            frage=(
                f"Dein Tages-Peak liegt um ~{signals.evening_peak_hour}:00 Uhr — "
                "kannst du Wasch-/Spül-/Trockner-Läufe zeitlich verschieben?"
            ),
            motiviert_durch=f"evening_peak_hour={signals.evening_peak_hour}",
        )
    )
    return fragen
