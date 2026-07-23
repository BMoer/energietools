# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Fakt-Präzedenz-Reconciler (Fakt vor Heuristik, Stufe 2 des Lastgang-Signal-
Pipelines: ``compute_signals -> apply_pv_guards (Stufe 1, Evidenz-Guard) ->
reconcile_signals (Stufe 2, Fakt-Präzedenz)``).

Ein gespeicherter Profil-Fakt (z.B. ``asset.heating.type=gas``) schlägt IMMER
die Lastgang-Heuristik — die Heuristik bleibt als Gegenprobe im Result
sichtbar (``heuristik_schaetzung``), gewinnt aber nie gegen einen Fakt. Die
Präzedenz-Tabelle (:data:`PRAEZEDENZ`) ist SSOT als Code; der optionale
``signale``-Block in ``prozesse/lastganganalyse.yaml`` ist eine gelintete
SICHT darauf (Drift-Guard im Prozess-Linter, s. ``prozesse/linter.py``).

Nur 3 der 7 Profil-Felder haben ein Signal-Gegenstück (``electric_heating``,
``pv_self_consumption``, ``high_continuous_load``) — die übrigen vier
(``asset.battery.kwh``, ``contract.heiztarif_typ``, ``behavior.
appliance_timing``, ``meter.q15_optin``) haben KEINE Lastgang-Heuristik, mit
der man sie gegenprüfen könnte; sie wirken ausschließlich über
:func:`reconcile_rueckfragen` (ein gespeicherter Fakt unterdrückt die
zugehörige Rückfrage, ohne Präzedenz-Zeile in dieser Tabelle).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from energietools.capabilities.lastgang.guards import PvGuardResult
from energietools.capabilities.lastgang.signals import (
    ELECTRIC_HEAT_RATIO,
    HIGH_BASE_W,
    NIGHT_FENSTER_LABEL,
    PV_DIP_RATIO,
    LastgangSignals,
    Rueckfrage,
    Signal,
)
from energietools.capabilities.profile import FaktWert, ProfileSource

ABGLEICH_KONSISTENT = "konsistent"
ABGLEICH_WIDERSPRUCH = "widerspruch"
ABGLEICH_NICHT_PRUEFBAR = "nicht_pruefbar"
ABGLEICH_KEIN_FAKT = "kein_fakt"

_HEIZUNG_ELEKTRISCH_WERTE = frozenset({"elektrisch", "waermepumpe"})
_HEIZUNG_UNKATEGORISIERT_WERTE = frozenset({"sonstiges"})

_WIDERSPRUCH_WAS = {
    "heizung": "der Heizung",
    "pv": "der PV-Anlage",
    "dauerlast": "den Dauerverbrauchern",
}


def _fmt(wert: float | int | None) -> str:
    return "n/a" if wert is None else str(wert)


def _heizung_signal_aus_fakt(fakt: FaktWert) -> Signal:
    """``sonstiges`` ist unkategorisiert (E1) — weder ein Beleg für noch gegen
    eine E-Heizung (z.B. Infrarot, Nachtspeicher), anders als ``keine`` (klar
    UNLIKELY). Ein Fakt-Wert von ``sonstiges`` impliziert daher UNKNOWN statt
    fälschlich UNLIKELY zu behaupten (Overclaim-Fix)."""
    if fakt.wert in _HEIZUNG_ELEKTRISCH_WERTE:
        return Signal.LIKELY
    if fakt.wert in _HEIZUNG_UNKATEGORISIERT_WERTE:
        return Signal.UNKNOWN
    return Signal.UNLIKELY


def _immer_likely(_fakt: FaktWert) -> Signal:
    # asset.pv.kwp/asset.continuous_loads sind bereits gateway-/ontologie-
    # validiert (kwp>0 bzw. nicht-leerer Text) — ein VORHANDENER Fakt ist
    # selbst schon die Bestätigung, es gibt keinen "Fakt sagt NEIN"-Zustand.
    return Signal.LIKELY


def _heizung_heuristik(signal: Signal) -> str | None:
    return {
        Signal.LIKELY: "vermutlich_elektrisch",
        Signal.UNLIKELY: "vermutlich_nicht_elektrisch",
    }.get(signal)


def _pv_heuristik(signal: Signal) -> str | None:
    return {
        Signal.LIKELY: "vermutlich_pv",
        Signal.UNLIKELY: "vermutlich_keine_pv",
    }.get(signal)


def _dauerlast_heuristik(signal: Signal) -> str | None:
    return {
        Signal.LIKELY: "vermutlich_dauerlaeufer",
        Signal.UNLIKELY: "vermutlich_keine_dauerlaeufer",
    }.get(signal)


def _heizung_kennzahl(signals: LastgangSignals) -> str:
    ratio = _fmt(signals.winter_summer_ratio)
    return f"winter_summer_ratio={ratio} (Schwelle {ELECTRIC_HEAT_RATIO})"


def _pv_kennzahl(signals: LastgangSignals) -> str:
    return f"midday_dip_ratio={_fmt(signals.midday_dip_ratio)} (Schwelle {PV_DIP_RATIO})"


def _dauerlast_kennzahl(signals: LastgangSignals) -> str:
    return (
        f"night_base_w={signals.night_base_w} W ({NIGHT_FENSTER_LABEL}, "
        f"Schwelle {HIGH_BASE_W} W)"
    )


@dataclass(frozen=True)
class SignalFaktPraezedenz:
    """Ein Eintrag der Präzedenz-Tabelle: welcher Fakt welches Signal übersteuert."""

    signal: str  # Result-Feld der Lastgang-Signale, z.B. "electric_heating"
    fakt_feld: str  # Profil-Feld, z.B. "asset.heating.type"
    antwort: str  # Block-Key im Result: "heizung" | "pv" | "dauerlast"
    fakt_impliziert_signal: Callable[[FaktWert], Signal]
    heuristik_schaetzung: Callable[[Signal], str | None]
    kennzahl: Callable[[LastgangSignals], str]


PRAEZEDENZ: tuple[SignalFaktPraezedenz, ...] = (
    SignalFaktPraezedenz(
        signal="electric_heating",
        fakt_feld="asset.heating.type",
        antwort="heizung",
        fakt_impliziert_signal=_heizung_signal_aus_fakt,
        heuristik_schaetzung=_heizung_heuristik,
        kennzahl=_heizung_kennzahl,
    ),
    SignalFaktPraezedenz(
        signal="pv_self_consumption",
        fakt_feld="asset.pv.kwp",
        antwort="pv",
        fakt_impliziert_signal=_immer_likely,
        heuristik_schaetzung=_pv_heuristik,
        kennzahl=_pv_kennzahl,
    ),
    SignalFaktPraezedenz(
        signal="high_continuous_load",
        fakt_feld="asset.continuous_loads",
        antwort="dauerlast",
        fakt_impliziert_signal=_immer_likely,
        heuristik_schaetzung=_dauerlast_heuristik,
        kennzahl=_dauerlast_kennzahl,
    ),
)

# Linter-Export (prozesse/linter.py::_lint_signal_praezedenz Drift-Check gegen
# den optionalen ``signale``-Block in prozesse/lastganganalyse.yaml).
SIGNAL_FELD_MAPPING: dict[str, str] = {p.signal: p.fakt_feld for p in PRAEZEDENZ}


@dataclass(frozen=True)
class SignalAbgleich:
    """Ergebnis EINES Präzedenz-Eintrags — Fakt vs. Heuristik, mit Gegenprobe."""

    antwort: str
    signal: str
    fakt_feld: str
    wert: str | float | bool | None  # Fakt-Wert (None ohne Fakt)
    quelle: str  # profil|rechnung|messung|prognose|heuristik
    stand: str | None
    heuristik_schaetzung: str | None
    status: str  # konsistent|widerspruch|nicht_pruefbar|kein_fakt
    signal_roh: str  # Heuristik NACH PV-Guard (ein Weg!)
    signal_effektiv: str  # fakt-konsistent gesetzt (== roh ohne Fakt)
    kennzahl: str
    caveat: str | None  # gesetzt bei widerspruch (deterministischer Text)


@dataclass(frozen=True)
class ProfilAbgleich:
    """Gesamtergebnis des Reconcilers über alle Präzedenz-Einträge."""

    verfuegbar: bool  # False = kein profil_fakten übergeben (fakten.get_all() leer)
    abgleiche: tuple[SignalAbgleich, ...]
    unterdrueckte_rueckfragen: tuple[str, ...] = field(default_factory=tuple)
    anzahl_widersprueche: int = 0


def _widerspruch_caveat(antwort: str, kennzahl: str) -> str:
    was = _WIDERSPRUCH_WAS.get(antwort, antwort)
    return (
        f"Ein gespeicherter Profil-Fakt widerspricht dem Lastgang-Muster bei "
        f"{antwort} ({kennzahl}) — die Antwort folgt dem gespeicherten Fakt; "
        f"prüfe, ob sich an {was} etwas geändert hat."
    )


def _signal_roh_werte(signals: LastgangSignals, guard: PvGuardResult) -> dict[str, Signal]:
    """Der jeweils AKTUELLE (Stufe-1-geguardete) Rohwert je Signal.

    ``electric_heating`` kommt bewusst aus dem PV-Guard-Ergebnis (kann auf
    ``unknown`` herabgestuft sein, Ledger-F24) — ``pv_self_consumption``/
    ``high_continuous_load`` hat der PV-Guard nicht angefasst, die kommen
    unverändert aus ``signals``.
    """
    return {
        "electric_heating": guard.electric_heating,
        "pv_self_consumption": signals.pv_self_consumption,
        "high_continuous_load": signals.high_continuous_load,
    }


def reconcile_signals(
    signals: LastgangSignals,
    guard: PvGuardResult,
    fakten: ProfileSource,
) -> ProfilAbgleich:
    """Stufe 2 der Lastgang-Signal-Pipeline: Fakt schlägt Heuristik.

    Pure Funktion — liest ausschließlich ``signals``/``guard``/``fakten``,
    keine Seiteneffekte. ``unterdrueckte_rueckfragen`` bleibt hier leer (die
    Rückfragen-Liste ist zu diesem Zeitpunkt der Pipeline noch nicht gebaut,
    s. :func:`reconcile_rueckfragen`) — der Aufrufer (Capability) trägt sie
    per ``dataclasses.replace`` nach, statt dieses Ergebnis zu mutieren.
    """
    roh_werte = _signal_roh_werte(signals, guard)
    abgleiche: list[SignalAbgleich] = []

    for eintrag in PRAEZEDENZ:
        signal_roh = roh_werte[eintrag.signal]
        kennzahl = eintrag.kennzahl(signals)
        heuristik_schaetzung = eintrag.heuristik_schaetzung(signal_roh)
        fakt = fakten.get_fakt(eintrag.fakt_feld)

        if fakt is None:
            abgleiche.append(
                SignalAbgleich(
                    antwort=eintrag.antwort,
                    signal=eintrag.signal,
                    fakt_feld=eintrag.fakt_feld,
                    wert=None,
                    quelle="heuristik",
                    stand=None,
                    heuristik_schaetzung=heuristik_schaetzung,
                    status=ABGLEICH_KEIN_FAKT,
                    signal_roh=signal_roh.value,
                    signal_effektiv=signal_roh.value,
                    kennzahl=kennzahl,
                    caveat=None,
                )
            )
            continue

        signal_effektiv = eintrag.fakt_impliziert_signal(fakt)
        if signal_effektiv is Signal.UNKNOWN:
            # Der Fakt selbst ist unkategorisiert (E1, z.B. asset.heating.type=
            # "sonstiges") — kein Beleg für ODER gegen das Signal. Die
            # Heuristik bleibt die Antwort (quelle="heuristik", wie im
            # kein_fakt-Fall), der Fakt-Wert bleibt zur Transparenz im
            # Abgleich sichtbar (``wert`` unten bleibt ``fakt.wert``).
            quelle = "heuristik"
            signal_effektiv = signal_roh
            status = ABGLEICH_NICHT_PRUEFBAR
            caveat = None
        elif signal_roh is Signal.UNKNOWN:
            quelle = fakt.quelle
            status = ABGLEICH_NICHT_PRUEFBAR
            caveat = None
        elif signal_roh == signal_effektiv:
            quelle = fakt.quelle
            status = ABGLEICH_KONSISTENT
            caveat = None
        else:
            quelle = fakt.quelle
            status = ABGLEICH_WIDERSPRUCH
            caveat = _widerspruch_caveat(eintrag.antwort, kennzahl)

        abgleiche.append(
            SignalAbgleich(
                antwort=eintrag.antwort,
                signal=eintrag.signal,
                fakt_feld=eintrag.fakt_feld,
                wert=fakt.wert,
                quelle=quelle,
                stand=fakt.stand.isoformat() if fakt.stand else None,
                heuristik_schaetzung=heuristik_schaetzung,
                status=status,
                signal_roh=signal_roh.value,
                signal_effektiv=signal_effektiv.value,
                kennzahl=kennzahl,
                caveat=caveat,
            )
        )

    anzahl_widersprueche = sum(1 for a in abgleiche if a.status == ABGLEICH_WIDERSPRUCH)

    return ProfilAbgleich(
        verfuegbar=bool(fakten.get_all()),
        abgleiche=tuple(abgleiche),
        unterdrueckte_rueckfragen=(),
        anzahl_widersprueche=anzahl_widersprueche,
    )


def reconcile_rueckfragen(
    rueckfragen: list[Rueckfrage],
    fakten: ProfileSource,
) -> tuple[list[Rueckfrage], list[str]]:
    """Entfernt jede Rückfrage, deren ``feld`` bereits einen gespeicherten Fakt
    hat (über ALLE 7 Profil-Felder, nicht nur die 3 mit Signal-Gegenstück).

    Gibt ``(verbleibende_rueckfragen, unterdrueckte_felder)`` zurück — pure,
    baut neue Listen statt die Eingabe zu mutieren. Kein Fakt vorhanden ⇒
    identische Rückfragen-Liste, leere Unterdrückungs-Liste.
    """
    verbleibend: list[Rueckfrage] = []
    unterdrueckt: list[str] = []
    for frage in rueckfragen:
        if fakten.get_fakt(frage.feld) is not None:
            unterdrueckt.append(frage.feld)
        else:
            verbleibend.append(frage)
    return verbleibend, unterdrueckt
