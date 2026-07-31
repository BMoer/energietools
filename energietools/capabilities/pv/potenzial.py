# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""PV-Potenzial auf einem ECHTEN Lastgang — Eigenverbrauch, Autarkie, Ertrag.

Der Unterschied zu jedem Online-Rechner: die Deckung zwischen Erzeugung und
Verbrauch wird Intervall für Intervall auf den gemessenen Viertelstundenwerten
gerechnet, nicht über ein Standardprofil und nicht über eine Faustformel.

Zwei getrennte Ergebnisse, weil die Datenlage zwei verschiedene Qualitäten hat
(Muster übernommen aus der geprüften Case-12-Rechnung):

A) **gemessen** — nur der Zeitraum mit echten Viertelstundenwerten. Nichts
   modelliert. Sagt aber nichts über ein volles Jahr, wenn das Fenster kürzer ist.
B) **jahr_modelliert** — 365 Tage aus den echten TAGESSUMMEN (die EDA tief
   zurückliefert) plus der Tagesform des ähnlichsten gemessenen Q15-Tages. Das
   ist ein MODELL und wird als solches ausgewiesen: die Winterform eines
   Wärmepumpen-Haushalts unterscheidet sich von seiner Sommerform.

Die Ökonomie ist bewusst nicht Teil der Bilanz: eine vermiedene kWh ist nur die
**arbeitsabhängigen** Preisbestandteile wert (Arbeitspreis + Netznutzung-Arbeit +
Netzverlust + Elektrizitätsabgabe + EAG-Förderbeitrag, × USt). Leistungspreis,
Messentgelt und Pauschalen laufen weiter — wer sie mitrechnet, überschätzt die
Ersparnis.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from energietools.capabilities.pv.profil import PVStundenprofil
from energietools.capabilities.scenarios.dispatch import run_self_consumption
from energietools.components.battery import Battery

#: Relative Toleranz der Energiebilanz-Prüfung (Gleitkomma-Rauschen, nicht mehr).
_BILANZ_TOLERANZ = 1e-6

#: Ab dieser Slot-Länge gilt eine Serie als zu grob für eine PV-Deckungsrechnung.
#: Deckungsgleich mit dem Q15-Guard der Lastgang-Capabilities.
MAX_SLOT_MINUTEN = 60

_TAGE_PRO_JAHR = 365

#: Messwerte liegen in UTC; „ein Tag" meint für Kunde und Netzbetreiber den
#: Wiener Kalendertag. Die Umrechnung ist echt, nicht als Stunden-Offset genähert.
_WIEN = ZoneInfo("Europe/Vienna")


class PVPotenzialFehler(ValueError):
    """Die Rechnung ist mit diesen Daten nicht seriös durchführbar."""


@dataclass(frozen=True)
class Lastreihe:
    """Gemessene Verbrauchsintervalle gleicher Länge (Zeitstempel in UTC)."""

    zeitpunkte: tuple[datetime, ...]
    kwh: tuple[float, ...]
    dt_hours: float

    def __post_init__(self) -> None:
        if len(self.zeitpunkte) != len(self.kwh):
            raise PVPotenzialFehler("Zeitpunkte und Werte müssen gleich lang sein")
        if not self.zeitpunkte:
            raise PVPotenzialFehler("Lastreihe ist leer")
        if self.dt_hours <= 0:
            raise PVPotenzialFehler("dt_hours muss > 0 sein")

    @property
    def summe_kwh(self) -> float:
        return sum(self.kwh)

    @property
    def stunden(self) -> float:
        return len(self.kwh) * self.dt_hours


@dataclass(frozen=True)
class PVBilanz:
    """Physische Bilanz einer PV-Variante über den gerechneten Zeitraum (kWh)."""

    kwp: float
    speicher_kwh: float
    zeitraum_stunden: float
    verbrauch_kwh: float
    ertrag_kwh: float
    eigenverbrauch_kwh: float
    eigenverbrauch_direkt_kwh: float
    eigenverbrauch_speicher_kwh: float
    einspeisung_kwh: float
    netzbezug_kwh: float
    eigenverbrauchsquote: float
    autarkiegrad: float
    speicher_vollzyklen: float
    speicher_restfuellung_kwh: float
    speicher_verlust_kwh: float


def lastreihe_aus_messwerten(
    messwerte: Iterable[Mapping[str, Any]],
    *,
    feld_zeit: str = "timestamp",
    feld_kwh: str = "kwh",
) -> Lastreihe:
    """Messwerte → :class:`Lastreihe`; erzwingt eine ausreichend feine, homogene Serie.

    Wirft, wenn die Serie gröber als :data:`MAX_SLOT_MINUTEN` ist — Tageswerte
    enthalten keine Tagesform, und eine PV-Deckung aus Tageswerten wäre eine
    Erfindung (sie käme systematisch zu hoch heraus).
    """
    paare: list[tuple[datetime, float]] = []
    for m in messwerte:
        roh = m[feld_zeit]
        ts = roh if isinstance(roh, datetime) else datetime.fromisoformat(str(roh))
        paare.append((ts.replace(tzinfo=None), float(m[feld_kwh])))
    paare.sort(key=lambda p: p[0])
    if len(paare) < 2:
        raise PVPotenzialFehler("Lastreihe braucht mindestens zwei Messwerte")

    zeitpunkte = [p[0] for p in paare]
    if len(set(zeitpunkte)) != len(zeitpunkte):
        doppelt = len(zeitpunkte) - len(set(zeitpunkte))
        raise PVPotenzialFehler(
            f"{doppelt} doppelte Zeitstempel in der Serie. Sie würden aufsummiert und "
            "den Verbrauch still erhöhen — die Serie muss vorher entdoppelt werden."
        )

    abstaende = sorted(
        (b[0] - a[0]).total_seconds() / 60.0 for a, b in zip(paare, paare[1:], strict=False)
    )
    median_min = abstaende[len(abstaende) // 2]
    if median_min > MAX_SLOT_MINUTEN:
        raise PVPotenzialFehler(
            f"Serie hat {median_min:.0f}-Minuten-Werte. Für eine PV-Rechnung braucht es "
            "Viertelstundenwerte: aus Tageswerten lässt sich nicht ablesen, wann im "
            "Tagesverlauf verbraucht wurde — und genau davon hängt der Eigenverbrauch ab."
        )
    return Lastreihe(
        zeitpunkte=tuple(p[0] for p in paare),
        kwh=tuple(p[1] for p in paare),
        dt_hours=median_min / 60.0,
    )


def erzeugungsreihe(reihe: Lastreihe, profil: PVStundenprofil, kwp: float) -> tuple[float, ...]:
    """PV-Erzeugung je Lastintervall (kWh) — zeitlich deckungsgleich zur Last."""
    if kwp < 0:
        raise PVPotenzialFehler("kwp darf nicht negativ sein")
    return tuple(profil.ertrag(ts, kwp, reihe.dt_hours) for ts in reihe.zeitpunkte)


def pv_bilanz(
    reihe: Lastreihe,
    profil: PVStundenprofil,
    *,
    kwp: float,
    speicher_kwh: float = 0.0,
    batterie: Battery | None = None,
) -> PVBilanz:
    """Bilanz einer PV-Variante über die Lastreihe (mit optionalem Speicher).

    Nutzt denselben Eigenverbrauchs-Dispatch wie die Szenarien-Capability — es
    gibt genau EINE Speicher-Physik im Paket, nicht zwei.
    """
    erzeugung = erzeugungsreihe(reihe, profil, kwp)
    bat = batterie if batterie is not None else Battery.new(float(speicher_kwh))
    res = run_self_consumption(erzeugung, reihe.kwh, bat, dt_hours=reihe.dt_hours)

    # Energieerhaltung — beide Richtungen. Ein Verstoß ist ein Rechenfehler und
    # darf nicht als plausible Zahl beim Kunden landen.
    erzeugt = res.production_kwh
    links = res.self_consumed_direct_kwh + res.battery_charge_from_bus_kwh + res.grid_feed_in_kwh
    if erzeugt > 0 and abs(links - erzeugt) > _BILANZ_TOLERANZ * max(erzeugt, 1.0):
        raise PVPotenzialFehler(
            f"Erzeugungsbilanz verletzt: {links:.6f} != {erzeugt:.6f} kWh"
        )
    verbraucht = res.consumption_kwh
    rechts = (
        res.self_consumed_direct_kwh + res.battery_discharge_kwh + res.grid_import_kwh
    )
    if verbraucht > 0 and abs(rechts - verbraucht) > _BILANZ_TOLERANZ * max(verbraucht, 1.0):
        raise PVPotenzialFehler(
            f"Verbrauchsbilanz verletzt: {rechts:.6f} != {verbraucht:.6f} kWh"
        )

    verlust = (
        res.battery_charge_from_bus_kwh
        - res.battery_discharge_kwh
        - res.battery_soc_residual_kwh
    )
    return PVBilanz(
        kwp=float(kwp),
        speicher_kwh=bat.capacity_kwh,
        zeitraum_stunden=reihe.stunden,
        verbrauch_kwh=round(res.consumption_kwh, 3),
        ertrag_kwh=round(res.production_kwh, 3),
        eigenverbrauch_kwh=round(res.self_consumed_direct_kwh + res.battery_discharge_kwh, 3),
        eigenverbrauch_direkt_kwh=round(res.self_consumed_direct_kwh, 3),
        eigenverbrauch_speicher_kwh=round(res.battery_discharge_kwh, 3),
        einspeisung_kwh=round(res.grid_feed_in_kwh, 3),
        netzbezug_kwh=round(res.grid_import_kwh, 3),
        eigenverbrauchsquote=res.self_consumption_rate,
        autarkiegrad=res.self_sufficiency_rate,
        speicher_vollzyklen=res.cycles,
        speicher_restfuellung_kwh=round(res.battery_soc_residual_kwh, 3),
        speicher_verlust_kwh=round(max(verlust, 0.0), 3),
    )


# ---------------------------------------------------------------------------
# Jahres-Modell aus echten Tagessummen + gemessener Tagesform
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Jahresmodell:
    """Modellierte Jahres-Lastreihe + die Angaben, die sie als Modell kenntlich machen."""

    reihe: Lastreihe
    von: date
    bis: date
    tage_mit_tagessumme: int
    muster_tage: int
    #: Monate, aus denen die gemessenen Tagesformen stammen. Fehlen die
    #: ertragsstarken Monate, wird die Deckung systematisch zu hoch geschätzt
    #: (an einem echten Jahreslastgang gemessen: bis +15 % ohne Speicher, wenn
    #: nur Winter-Q15 vorlag; mit Speicher unter 1 %).
    muster_monate: tuple[int, ...] = ()
    ist_modell: bool = True

    @property
    def deckt_sonnenhalbjahr(self) -> bool:
        """Ist mindestens ein Mustertag aus April–September dabei?"""
        return any(4 <= m <= 9 for m in self.muster_monate)


def jahresmodell(
    q15: Lastreihe,
    tagessummen: Mapping[date, float],
    *,
    bis_tag: date | None = None,
) -> Jahresmodell:
    """365 Tage Stundenreihe aus echten Tagessummen und gemessenen Tagesformen.

    Für jeden Tag wird die normierte Tagesform des ähnlichsten gemessenen Q15-Tages
    übernommen (kleinster Abstand der Tagessumme, gleicher Werktag/Wochenende-Typ)
    und auf die echte Tagessumme skaliert. Die Tagessumme ist gemessen, die
    **Verteilung über den Tag** ist modelliert.
    """
    if not tagessummen:
        raise PVPotenzialFehler("keine Tagessummen übergeben")

    # Muster: nur vollständige gemessene Tage (mind. 90 % der Slots).
    slots_pro_tag = round(24.0 / q15.dt_hours)
    nach_tag: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
    for ts, kwh in zip(q15.zeitpunkte, q15.kwh, strict=True):
        nach_tag[ts.date()].append((ts, kwh))

    muster: list[tuple[float, bool, dict[int, float]]] = []
    muster_monate: set[int] = set()
    for tag, slots in nach_tag.items():
        summe = sum(k for _, k in slots)
        if summe <= 0 or len(slots) < 0.9 * slots_pro_tag:
            continue
        form: dict[int, float] = defaultdict(float)
        for ts, kwh in slots:
            form[ts.hour] += kwh / summe
        muster.append((summe, tag.weekday() >= 5, dict(form)))
        muster_monate.add(tag.month)
    if not muster:
        raise PVPotenzialFehler(
            "kein vollständiger gemessener Tag als Muster vorhanden — ohne mindestens "
            "einen kompletten Q15-Tag lässt sich keine Tagesform übertragen"
        )

    letzter = bis_tag or max(tagessummen)
    erster = letzter - timedelta(days=_TAGE_PRO_JAHR - 1)

    zeitpunkte: list[datetime] = []
    werte: list[float] = []
    getroffen = 0
    tag = erster
    while tag <= letzter:
        summe = tagessummen.get(tag)
        if summe is not None:
            getroffen += 1
            ist_we = tag.weekday() >= 5
            passend = [m for m in muster if m[1] == ist_we] or muster
            _, _, form = min(passend, key=lambda m: abs(m[0] - summe))
            for stunde in range(24):
                zeitpunkte.append(datetime(tag.year, tag.month, tag.day, stunde))
                werte.append(summe * form.get(stunde, 0.0))
        tag += timedelta(days=1)

    if not zeitpunkte:
        raise PVPotenzialFehler("keine Tagessumme im Jahresfenster gefunden")

    return Jahresmodell(
        reihe=Lastreihe(tuple(zeitpunkte), tuple(werte), dt_hours=1.0),
        von=erster,
        bis=letzter,
        tage_mit_tagessumme=getroffen,
        muster_tage=len(muster),
        muster_monate=tuple(sorted(muster_monate)),
    )


def tagessummen_aus_messwerten(
    messwerte: Iterable[Mapping[str, Any]],
    *,
    feld_zeit: str = "timestamp",
    feld_kwh: str = "kwh",
) -> dict[date, float]:
    """Alle Messwerte (Q15 UND Tageswerte) → Tagessumme je Kalendertag.

    Der Kalendertag ist der **Wiener** Tag: ein Tageswert für den 1. Mai trägt als
    Intervallbeginn ``2025-04-30T22:00Z`` (= 1. Mai 00:00 MESZ), ein Tageswert für
    den 1. Jänner ``2024-12-31T23:00Z`` (MEZ). Ein fester Stunden-Offset trifft
    deshalb nur eine der beiden Jahreshälften — hier wird echt umgerechnet.
    """
    summen: dict[date, float] = defaultdict(float)
    for m in messwerte:
        roh = m[feld_zeit]
        ts = roh if isinstance(roh, datetime) else datetime.fromisoformat(str(roh))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        summen[ts.astimezone(_WIEN).date()] += float(m[feld_kwh])
    return dict(summen)


# ---------------------------------------------------------------------------
# Ökonomie
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bezugspreis:
    """Was eine vermiedene kWh Netzbezug wert ist (brutto EUR/kWh), mit Rechenweg."""

    arbeitspreis_netto_ct_kwh: float
    netz_arbeitsabhaengig_netto_ct_kwh: float
    ust_satz: float
    brutto_eur_kwh: float
    rechenweg: tuple[str, ...]


def bezugspreis(
    *,
    arbeitspreis_netto_ct_kwh: float,
    netz_arbeitsabhaengig_netto_ct_kwh: float,
    ust_satz: float = 0.20,
) -> Bezugspreis:
    """Arbeitsabhängiger Bezugspreis brutto — die einzige Größe, die PV einspart.

    ``netz_arbeitsabhaengig_netto_ct_kwh`` kommt aus der ``netzkosten``-Capability
    (Netznutzung-Arbeitspreis + Netzverlust + EAG-Förderbeiträge +
    Elektrizitätsabgabe) und wird hier NICHT nachgebaut.
    """
    if arbeitspreis_netto_ct_kwh < 0 or netz_arbeitsabhaengig_netto_ct_kwh < 0:
        raise PVPotenzialFehler("Preisbestandteile dürfen nicht negativ sein")
    netto = arbeitspreis_netto_ct_kwh + netz_arbeitsabhaengig_netto_ct_kwh
    brutto = netto * (1.0 + ust_satz) / 100.0
    return Bezugspreis(
        arbeitspreis_netto_ct_kwh=round(arbeitspreis_netto_ct_kwh, 4),
        netz_arbeitsabhaengig_netto_ct_kwh=round(netz_arbeitsabhaengig_netto_ct_kwh, 4),
        ust_satz=ust_satz,
        brutto_eur_kwh=round(brutto, 6),
        rechenweg=(
            f"Arbeitspreis netto {arbeitspreis_netto_ct_kwh:.4f} ct/kWh",
            f"+ Netz arbeitsabhängig netto {netz_arbeitsabhaengig_netto_ct_kwh:.4f} ct/kWh",
            f"= netto {netto:.4f} ct/kWh",
            f"× {1 + ust_satz:.2f} USt = brutto {netto * (1 + ust_satz):.4f} ct/kWh"
            f" = {brutto:.6f} EUR/kWh",
        ),
    )


@dataclass(frozen=True)
class Nutzen:
    """Jährlicher Geldnutzen einer PV-Variante, aufgeschlüsselt."""

    vermiedener_bezug_eur: float
    einspeiseerloes_eur: float
    gesamt_eur: float
    einspeise_netto_ct_kwh: float
    rechenweg: tuple[str, ...]


def nutzen(
    bilanz: PVBilanz,
    preis: Bezugspreis,
    *,
    einspeise_netto_ct_kwh: float,
    ust_satz: float = 0.20,
    jahresfaktor: float = 1.0,
) -> Nutzen:
    """Vermiedener Bezug + Einspeiseerlös (beides brutto EUR), auf ein Jahr skaliert.

    ``jahresfaktor`` ist 1.0, wenn die Bilanz bereits ein Jahr abdeckt. Für ein
    kürzeres Messfenster gibt der Aufrufer den Faktor NUR dann an, wenn er die
    saisonale Verzerrung ausdrücklich in Kauf nimmt und ausweist.
    """
    vermieden = bilanz.eigenverbrauch_kwh * preis.brutto_eur_kwh * jahresfaktor
    erloes = (
        bilanz.einspeisung_kwh * einspeise_netto_ct_kwh / 100.0 * (1.0 + ust_satz) * jahresfaktor
    )
    return Nutzen(
        vermiedener_bezug_eur=round(vermieden, 2),
        einspeiseerloes_eur=round(erloes, 2),
        gesamt_eur=round(vermieden + erloes, 2),
        einspeise_netto_ct_kwh=einspeise_netto_ct_kwh,
        rechenweg=(
            f"Eigenverbrauch {bilanz.eigenverbrauch_kwh:.0f} kWh"
            f" × {preis.brutto_eur_kwh:.6f} EUR/kWh"
            + (f" × {jahresfaktor:.4f}" if jahresfaktor != 1.0 else "")
            + f" = {vermieden:.2f} EUR vermiedener Bezug",
            f"Einspeisung {bilanz.einspeisung_kwh:.0f} kWh"
            f" × {einspeise_netto_ct_kwh:.2f} ct/kWh × {1 + ust_satz:.2f}"
            + (f" × {jahresfaktor:.4f}" if jahresfaktor != 1.0 else "")
            + f" = {erloes:.2f} EUR Einspeiseerlös",
            f"Summe {vermieden + erloes:.2f} EUR/Jahr",
        ),
    )


def grenznutzen(reihen: Sequence[tuple[float, float]]) -> list[dict[str, float]]:
    """Zusatznutzen je zusätzlicher kWh Speicher — ``[(groesse_kwh, nutzen_eur), …]``.

    Beantwortet die eigentliche Dimensionierungsfrage: nicht „bringt ein Speicher
    was", sondern „ab welcher Größe bringt die nächste kWh fast nichts mehr".
    """
    sortiert = sorted(reihen, key=lambda r: r[0])
    out: list[dict[str, float]] = []
    for (g0, n0), (g1, n1) in zip(sortiert, sortiert[1:], strict=False):
        delta_g = g1 - g0
        if delta_g <= 0:
            continue
        out.append(
            {
                "von_kwh": g0,
                "bis_kwh": g1,
                "zusatznutzen_eur_jahr": round(n1 - n0, 2),
                "zusatznutzen_eur_je_kwh_jahr": round((n1 - n0) / delta_g, 2),
            }
        )
    return out


__all__ = [
    "MAX_SLOT_MINUTEN",
    "Bezugspreis",
    "Jahresmodell",
    "Lastreihe",
    "Nutzen",
    "PVBilanz",
    "PVPotenzialFehler",
    "bezugspreis",
    "erzeugungsreihe",
    "grenznutzen",
    "jahresmodell",
    "lastreihe_aus_messwerten",
    "nutzen",
    "pv_bilanz",
    "tagessummen_aus_messwerten",
]
