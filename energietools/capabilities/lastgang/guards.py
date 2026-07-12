# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""PV-bedingte Guards für die Lastgang-Signale (L.1.4 — NEU ggü. der gridbert-
Quelle, Ledger F3/F14/F24).

Ein Netzbezug-Lastgang bei einem PV-Prosumer erzeugt False Positives, die ein
reiner Verbrauchskanal nicht hat: der Mittags-Bezug ist PV-gedeckt, also sieht
jede Kennzahl auf Netzbezug-Basis nach weniger Verbrauch aus als real
stattfindet. Belegfall (Ledger-F24, anonymisiert): ein PV-Prosumer-Fall mit
Winter/Sommer-Verhältnis 3,16 auf Netzbezug → ``electric_heating=likely`` —
real eine Pelletsheizung, keine E-Heizung. Die Guards greifen
**ausschließlich bei ``is_pv=True``** (Ledger-F14: bei einem reinen
Verbrauchskanal — Fall B — gelten sie NICHT, sonst würde ein echtes Signal
grundlos entschärft).

Drei Guard-Effekte + eine Konsistenz-Prüfung (kein Hard-Fail):
(a) NETZBEZUG-Label statt „Verbrauch".
(b) ``electric_heating=LIKELY`` wird zur Rückfrage herabgestuft (Behauptung →
    Frage), der Rohwert bleibt in ``roh_ws_ratio`` erhalten.
(c) eine übergebene ``grundlast_kw`` (aus ``load_profile``) wird als
    PV-Artefakt markiert (P15 nahe 0 durch Mittags-Eigenverbrauch).
(d) Plausibilitäts-Check: Mittag > Nacht (``midday_dip_ratio > 1``) ist
    untypisch für PV-Bezug → Warnfeld, ob das PV-Flag überhaupt stimmt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from energietools.capabilities.lastgang.signals import LastgangSignals, Rueckfrage, Signal

_HEATING_FELD = "asset.heating.type"

CAVEAT_NETZBEZUG = (
    "Metriken beschreiben den NETZBEZUG, nicht den Verbrauch — bei PV ist der "
    "Mittags-Bezug PV-gedeckt."
)
CAVEAT_HEATING_GUARD = (
    "WS-Ratio auf Netzbezug ist bei PV ein False Positive (Ledger-F24: ein "
    "WS-Ratio von 3,16 erwies sich real als Pelletsheizung, nicht E-Heizung) — "
    "electric_heating wurde auf 'unknown' herabgestuft, die Rückfrage bleibt "
    "offen statt zu behaupten."
)
CAVEAT_GRUNDLAST_ARTEFAKT = (
    "Grundlast(P15) bei PV verzerrt — Mittags-Slots nahe 0 durch "
    "Eigenverbrauch, kein echter Sockel."
)
CAVEAT_PV_WIDERSPRUCH = (
    "PV-Flag ggf. falsch gesetzt: Mittags-Bezug > Nacht-Bezug ist bei PV "
    "untypisch (Konsistenz prüfen, kein Hard-Fail)."
)

_GUARDED_HEATING_FRAGE = (
    "Dein Netzbezug ist im Winter deutlich höher als im Sommer (Winter/Sommer-"
    "Verhältnis {ws} auf Netzbezug) — bei einer PV-Anlage ist das aber KEIN "
    "verlässliches Zeichen für eine E-Heizung, weil der Netzbezug nicht dem "
    "Gesamtverbrauch entspricht (PV deckt einen Teil ab, F24). Heizt du mit "
    "Strom (Wärmepumpe/Direktheizung) oder mit Gas/Fernwärme/Pellets?"
)


@dataclass(frozen=True)
class PvGuardResult:
    """Effekt der PV-Guards auf ein rohes :class:`LastgangSignals`-Ergebnis."""

    basis_label: str  # "Netzbezug" | "Verbrauch"
    electric_heating: Signal  # ggf. auf UNKNOWN herabgestuft
    electric_heating_guarded: bool
    roh_ws_ratio: float | None  # nur gesetzt, wenn geguardet
    grundlast_p15_pv_artefakt: bool
    pv_flag_widerspruch: bool
    caveats: list[str] = field(default_factory=list)


def apply_pv_guards(
    signals: LastgangSignals,
    *,
    is_pv: bool,
    grundlast_kw: float | None,
) -> PvGuardResult:
    """Wendet die PV-Guards (L.1.4) auf ein Roh-Signal-Ergebnis an.

    Bei ``is_pv=False`` (Fall B, reiner Verbrauchskanal) unverändert
    durchgereicht — die Guards sind PV-bedingt, nicht pauschal (Ledger-F14).
    """
    if not is_pv:
        return PvGuardResult(
            basis_label="Verbrauch",
            electric_heating=signals.electric_heating,
            electric_heating_guarded=False,
            roh_ws_ratio=None,
            grundlast_p15_pv_artefakt=False,
            pv_flag_widerspruch=False,
            caveats=[],
        )

    caveats = [CAVEAT_NETZBEZUG]

    guarded = signals.electric_heating is Signal.LIKELY
    electric_heating = Signal.UNKNOWN if guarded else signals.electric_heating
    roh_ws_ratio = signals.winter_summer_ratio if guarded else None
    if guarded:
        caveats.append(CAVEAT_HEATING_GUARD)

    grundlast_artefakt = grundlast_kw is not None
    if grundlast_artefakt:
        caveats.append(CAVEAT_GRUNDLAST_ARTEFAKT)

    widerspruch = signals.midday_dip_ratio is not None and signals.midday_dip_ratio > 1
    if widerspruch:
        caveats.append(CAVEAT_PV_WIDERSPRUCH)

    return PvGuardResult(
        basis_label="Netzbezug",
        electric_heating=electric_heating,
        electric_heating_guarded=guarded,
        roh_ws_ratio=roh_ws_ratio,
        grundlast_p15_pv_artefakt=grundlast_artefakt,
        pv_flag_widerspruch=widerspruch,
        caveats=caveats,
    )


def guard_rueckfragen(
    rueckfragen: list[Rueckfrage],
    *,
    guard: PvGuardResult,
) -> list[Rueckfrage]:
    """Ersetzt die Heizungs-Rückfrage durch die PV-neutrale Frage-Variante.

    L.1.6: „PV-Guard-Override: bei ``is_pv=True`` + geguardetem
    ``electric_heating`` IMMER die Frage-Variante (nie Behauptung)." Die
    Standard-Rückfrage nimmt bei einem hohen Winter/Sommer-Verhältnis bereits
    an, dass E-Heizung wahrscheinlich ist — bei PV ist genau diese Annahme der
    F24-False-Positive. Die geguardete Frage bleibt offen, statt vorwegzunehmen.
    """
    if not guard.electric_heating_guarded:
        return rueckfragen
    ersetzt: list[Rueckfrage] = []
    for frage in rueckfragen:
        if frage.feld == _HEATING_FELD:
            ersetzt.append(
                Rueckfrage(
                    feld=frage.feld,
                    frage=_GUARDED_HEATING_FRAGE.format(ws=guard.roh_ws_ratio),
                    motiviert_durch=(
                        f"{frage.motiviert_durch}; PV-Guard aktiv "
                        "(Netzbezug != Verbrauch, F24)"
                    ),
                )
            )
        else:
            ersetzt.append(frage)
    return ersetzt
