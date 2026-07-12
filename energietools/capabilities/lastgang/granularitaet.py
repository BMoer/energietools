# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Gemeinsame Granularitäts-Erkennung für die Intraday-Lastgang-Capabilities
(F29 (a), Plan DURCHSTICH-2-PLAN.md §4 F29 + §2 WP2-P Punkt 5).

``lastgang_signals`` bekommt ``interval_minutes`` als expliziten Parameter
(vom Gateway gesetzt, s. ``signals.compute_signals``) — ``trend_attribution``
und ``spot_backtest`` haben KEIN solches Inputfeld in ihrem ``input_schema``,
deshalb wird der Slot-Abstand hier aus den Zeitstempeln der
``consumption``-Serie selbst abgeleitet (Median der Abstände
aufeinanderfolgender, sortierter Zeitstempel — robust gegen einzelne
Lücken/Duplikate/einen einzelnen Ausreißer-Sprung).

Alle drei Capabilities teilen dieselbe Schwelle
(``GRANULARITAET_SCHWELLE_MIN = 60``, wie der bestehende
``compute_signals``-Guard) — die Fehlertexte selbst bleiben lokal bei der
jeweiligen Capability (Repo-Muster: jedes Modul trägt seine eigenen
Fehlertext-Konstanten, z.B. ``signals._GRANULARITAET_FEHLER``), nur die
Erkennungslogik (Ableitung + Schwellenvergleich) ist hier gebündelt statt
kopiert.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from statistics import median

# Ab so vielen Minuten Slot-Abstand gilt eine Serie als Tageswerte/grobe Serie
# (F29 (a)) — dieselbe Schwelle wie der explizite interval_minutes-Guard in
# lastgang_signals (signals.compute_signals).
GRANULARITAET_SCHWELLE_MIN = 60


def slot_abstand_minuten(zeitstempel: Iterable[datetime]) -> float | None:
    """Median-Abstand aufeinanderfolgender, sortierter Zeitstempel (Minuten).

    ``None`` bei weniger als zwei VERSCHIEDENEN Zeitstempeln — der Abstand ist
    dann nicht bestimmbar; eine so kurze/degenerierte Serie gilt NICHT
    automatisch als grob (andere Guards, z.B. „leerer Lastgang" oder „nur ein
    Jahr", greifen an anderer Stelle mit einer passenderen Begründung).
    """
    eindeutig = sorted(set(zeitstempel))
    if len(eindeutig) < 2:
        return None
    deltas = [(b - a).total_seconds() / 60 for a, b in zip(eindeutig, eindeutig[1:])]
    return median(deltas)


def ist_grobe_serie(zeitstempel: Iterable[datetime]) -> tuple[bool, float | None]:
    """(ist_grob, abgeleiteter_slot_abstand_min).

    ``ist_grob`` ist True ab ``GRANULARITAET_SCHWELLE_MIN`` — der Aufrufer
    entscheidet selbst, mit welchem (capability-eigenen) Fehlertext er einen
    ``CapabilityError`` wirft (F29 (a): Begründung „braucht 15-min-Auflösung"
    + aktive Q15-Opt-in-Empfehlung, s. ``attribution._GRANULARITAET_FEHLER``
    bzw. ``capability._GRANULARITAET_FEHLER_SPOT``).
    """
    abstand = slot_abstand_minuten(zeitstempel)
    return (abstand is not None and abstand >= GRANULARITAET_SCHWELLE_MIN), abstand
