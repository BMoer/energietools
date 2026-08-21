# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Deutung eines Lastgang-Ereignisses — was könnte das gewesen sein?

Gegenstück zu :mod:`energietools.capabilities.lastgang.ereignisse`: dort wird
gemessen, was passiert ist, hier wird daraus eine Hypothese und — wenn nötig —
eine Rückfrage.

**Die Reihenfolge ist die ganze Idee.** Gefragt wird nur, was nicht schon
bekannt ist:

1. **Profil-Fakt** — was der Haushalt über sich gesagt hat (``ProfileSource``,
   Fakt vor Heuristik wie in :mod:`…lastgang.reconcile`).
2. **Gedächtnis** — was der Haushalt bei einem *gleichartigen* Ereignis schon
   einmal geantwortet hat. Gleichartig heißt: dieselbe Ereignisart, dieselbe
   Größenordnung der Leistung, dasselbe Zeitfenster. Ein Klimagerät mit 190 W
   erklärt keine 2.300 W — sonst lernte das System Unsinn und behauptete ihn
   danach mit voller Überzeugung.
3. **Kandidaten** — passt keines von beidem, werden aus der Signatur (Leistung,
   Stunden, Dauer, Jahreszeit) die plausiblen Verbraucher ausgewählt und dem
   Haushalt zur Auswahl gestellt. Behauptet wird dabei nichts.

**Warum überhaupt gefragt wird.** Die Forschung zur Disaggregation bei 15- bis
60-Minuten-Werten kommt ohne Zusatzwissen über die Geräte des Haushalts nicht
aus: Zhao et al. (Applied Energy 2020) brauchen die Wattage-Angaben aus einer
Geräte-Befragung, und die Verfahren, die ohne auskommen, brauchen tausende
gelabelte Haushalte als Trainingsdaten (Petralia et al., ACM e-Energy 2023:
2.611 bzw. >5.000 Lastkurven). Die Rückfrage ist deshalb kein Notbehelf,
sondern der Teil des Verfahrens, der die fehlende Auflösung ersetzt — und ein
gespeichertes Nutzer-Label wirkt danach wie ein Fakt und nicht wie eine
Schätzung.

**Keine erfundene Sicherheit.** Ohne Arbeitspreis gibt es keine Euro-Zahl.
Ohne passenden Kandidaten gibt es die Option „weiß ich nicht", und die steht
immer zur Verfügung — eine Mail, die eine Antwort erzwingt, die der Haushalt
nicht hat, bekommt eine falsche.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from energietools.capabilities.lastgang.ereignisse import (
    ABWESENHEIT,
    DAUERLAST_NACHT,
    NEUE_SPITZE,
    VERBRAUCH_HOCH,
    Ereignis,
)
from energietools.capabilities.profile import ProfileSource

STUNDEN_PRO_JAHR = 8760
TAGE_PRO_JAHR = 365

# Ab so vielen betroffenen Stunden gilt ein Verbrauchssprung als durchgehend
# (und nicht als "ein Gerät lief ein paar Stunden").
DURCHGEHEND_AB_STUNDEN = 14

# Toleranz, innerhalb derer eine frühere Antwort auf ein neues Ereignis
# übertragen wird: die Leistung darf um 40 % abweichen, die betroffenen
# Stunden müssen sich zur Hälfte überlappen.
GEDAECHTNIS_LEISTUNG_TOLERANZ = 0.4
GEDAECHTNIS_STUNDEN_UEBERLAPPUNG = 0.5

SOMMER_MONATE = (5, 6, 7, 8, 9)
WINTER_MONATE = (10, 11, 12, 1, 2, 3, 4)


@dataclass(frozen=True, slots=True)
class Antwortoption:
    """Eine anklickbare Antwort auf die Rückfrage.

    ``profil_feld``/``profil_wert`` sagen, was gespeichert wird, wenn der
    Haushalt diese Option wählt — leer bei Optionen, die keinen dauerhaften
    Fakt begründen (z.B. „war Besuch").
    """

    label: str
    text: str
    profil_feld: str = ""
    profil_wert: str = ""


@dataclass(frozen=True, slots=True)
class FruehereAntwort:
    """Was der Haushalt bei einem früheren Ereignis geantwortet hat."""

    typ: str
    label: str
    text: str
    leistung_w: int
    stunden: tuple[int, ...]
    beantwortet_am: date


@dataclass(frozen=True, slots=True)
class Deutung:
    """Ergebnis: entweder eine belegte Erklärung oder eine gezielte Frage."""

    ereignis: Ereignis
    erklaerung: str | None = None
    quelle: str | None = None  # "profil" | "gedaechtnis"
    frage: str | None = None
    optionen: tuple[Antwortoption, ...] = ()
    kontext: tuple[str, ...] = ()
    kosten_eur: float | None = None
    hochrechnung_kwh_jahr: float | None = None
    hochrechnung_eur_jahr: float | None = None


@dataclass(frozen=True, slots=True)
class _Kandidat:
    """Ein möglicher Verursacher samt der Signatur, zu der er passt."""

    label: str
    text: str
    typen: tuple[str, ...]
    watt_von: int
    watt_bis: int
    monate: tuple[int, ...] | None = None
    stunden: tuple[int, ...] | None = None
    profil_feld: str = ""
    profil_wert: str = ""
    stichworte: tuple[str, ...] = ()
    # Mindestdauer in betroffenen Stunden. Eine Ladung dauert; eine einzelne
    # Stunde mit 5 kW ist ein Herd, kein Auto.
    min_stunden: int = 0
    # Nur an Feiertagen/Wochenenden anbieten — und dann mit Vorrang. Am
    # 24. Dezember nach einem defekten Kühlgerät zu fragen, während der
    # Kalender die Antwort danebenlegt, ist die Sorte Alarm, die man abbestellt.
    nur_an_freien_tagen: bool = False


_DAUER = (DAUERLAST_NACHT, VERBRAUCH_HOCH)

# Der Katalog. Die Leistungsbänder sind Typenschild-Größenordnungen, keine
# Messwerte — sie entscheiden nur, WELCHE Frage gestellt wird.
KANDIDATEN: tuple[_Kandidat, ...] = (
    _Kandidat(
        label="kuehlgeraet",
        text="Ein Kühl- oder Gefriergerät (zusätzliches, oder eines, das nicht mehr richtig schließt)",
        typen=_DAUER,
        watt_von=60,
        watt_bis=400,
        profil_feld="asset.continuous_loads",
        profil_wert="Kühl-/Gefriergerät",
        stichworte=("kühl", "kuehl", "gefrier", "truhe", "fridge"),
    ),
    _Kandidat(
        label="klimageraet",
        text="Ein Klimagerät oder ein Ventilator",
        typen=_DAUER,
        watt_von=80,
        watt_bis=1500,
        monate=SOMMER_MONATE,
        profil_feld="asset.continuous_loads",
        profil_wert="Klimagerät",
        stichworte=("klima", "klimaanlage", "ventilator", "lüfter", "luefter"),
    ),
    _Kandidat(
        label="heizgeraet",
        text="Ein Heizlüfter, ein Ölradiator oder ein Handtuchtrockner",
        typen=_DAUER,
        watt_von=100,
        watt_bis=3000,
        monate=WINTER_MONATE,
        profil_feld="asset.continuous_loads",
        profil_wert="Elektrisches Heizgerät",
        stichworte=("heizlüfter", "heizluefter", "radiator", "handtuch", "infrarot"),
    ),
    _Kandidat(
        label="pumpe",
        text="Eine Pumpe, Aquarium, Pool, Zirkulation oder Umwälzung",
        typen=_DAUER,
        watt_von=60,
        watt_bis=1000,
        profil_feld="asset.continuous_loads",
        profil_wert="Pumpe",
        stichworte=("aquarium", "pool", "pumpe", "teich", "zirkulation"),
    ),
    _Kandidat(
        label="technik",
        text="Technik im Dauerbetrieb, Server, NAS, PC oder Netzwerkgeräte",
        typen=_DAUER,
        watt_von=50,
        watt_bis=500,
        profil_feld="asset.continuous_loads",
        profil_wert="IT im Dauerbetrieb",
        stichworte=("server", "nas", "pc", "rechner", "router", "mining"),
    ),
    _Kandidat(
        label="entfeuchter",
        text="Ein Luftentfeuchter oder ein Bautrockner",
        typen=_DAUER,
        watt_von=150,
        watt_bis=1000,
        profil_feld="asset.continuous_loads",
        profil_wert="Luftentfeuchter",
        stichworte=("entfeucht", "bautrockner", "trocknungsgerät"),
    ),
    _Kandidat(
        label="boiler",
        text="Ein Boiler oder ein Warmwasserspeicher",
        typen=_DAUER,
        watt_von=800,
        watt_bis=3500,
        profil_feld="asset.continuous_loads",
        profil_wert="Elektroboiler",
        stichworte=("boiler", "warmwasser", "speicher"),
    ),
    _Kandidat(
        label="eauto",
        text="Ein Elektroauto, das geladen hat",
        typen=_DAUER,
        watt_von=1800,
        watt_bis=22000,
        min_stunden=3,
        profil_feld="asset.continuous_loads",
        profil_wert="E-Auto-Ladung",
        stichworte=("e-auto", "eauto", "elektroauto", "wallbox", "laden"),
    ),
    _Kandidat(
        label="waermepumpe",
        text="Eine Wärmepumpe",
        typen=_DAUER,
        watt_von=400,
        watt_bis=6000,
        monate=WINTER_MONATE,
        profil_feld="asset.heating.type",
        profil_wert="waermepumpe",
        stichworte=("wärmepumpe", "waermepumpe", "wp"),
    ),
    _Kandidat(
        label="feiertag",
        text="Der Feiertag selbst, Besuch, Kochen, alle den Tag über zu Hause",
        typen=(VERBRAUCH_HOCH,),
        watt_von=80,
        watt_bis=6000,
        nur_an_freien_tagen=True,
    ),
    _Kandidat(
        label="besuch",
        text="Besuch, mehr Menschen im Haushalt als sonst",
        typen=(VERBRAUCH_HOCH,),
        watt_von=100,
        watt_bis=4000,
    ),
    _Kandidat(
        label="kochen",
        text="Kochen oder Backen (Backofen und Herdplatten zusammen 5–7 kW)",
        typen=(VERBRAUCH_HOCH,),
        watt_von=800,
        watt_bis=7000,
        stunden=(10, 11, 12, 13, 17, 18, 19, 20),
    ),
    _Kandidat(
        label="waschen",
        text="Waschmaschine, Trockner oder Geschirrspüler",
        typen=(VERBRAUCH_HOCH,),
        watt_von=400,
        watt_bis=3500,
        stunden=tuple(range(7, 23)),
    ),
    _Kandidat(
        label="zuhause",
        text="Jemand war den ganzen Tag zu Hause (Homeoffice, Urlaub, krank)",
        typen=(VERBRAUCH_HOCH,),
        watt_von=80,
        watt_bis=2000,
    ),
    _Kandidat(
        label="herd",
        text="Herd oder Backofen auf voller Leistung",
        typen=(NEUE_SPITZE,),
        watt_von=2000,
        watt_bis=8000,
    ),
    _Kandidat(
        label="durchlauferhitzer",
        text="Ein Durchlauferhitzer",
        typen=(NEUE_SPITZE,),
        watt_von=3500,
        watt_bis=21000,
        profil_feld="asset.continuous_loads",
        profil_wert="Durchlauferhitzer",
        stichworte=("durchlauferhitzer",),
    ),
    _Kandidat(
        label="wallbox",
        text="Eine Wallbox oder ein Ladeziegel fürs E-Auto",
        typen=(NEUE_SPITZE,),
        watt_von=3500,
        watt_bis=22000,
        profil_feld="asset.continuous_loads",
        profil_wert="Wallbox",
        stichworte=("wallbox", "e-auto", "eauto", "elektroauto"),
    ),
    _Kandidat(
        label="sauna",
        text="Eine Sauna oder ein Infrarotkabine",
        typen=(NEUE_SPITZE,),
        watt_von=3000,
        watt_bis=12000,
        profil_feld="asset.continuous_loads",
        profil_wert="Sauna",
        stichworte=("sauna", "infrarotkabine"),
    ),
    _Kandidat(
        label="werkzeug",
        text="Ein Elektrowerkzeug, ein Hochdruckreiniger oder ein Staubsauger",
        typen=(NEUE_SPITZE,),
        watt_von=1500,
        watt_bis=4000,
    ),
    _Kandidat(
        label="heizluefter_spitze",
        text="Ein Heizlüfter",
        typen=(NEUE_SPITZE,),
        watt_von=1500,
        watt_bis=3000,
        monate=WINTER_MONATE,
    ),
)

UNBEKANNT = Antwortoption(label="unbekannt", text="Weiß ich nicht")

MAX_OPTIONEN = 4

_FRAGEN = {
    DAUERLAST_NACHT: (
        "{Zeitraum} sind nachts durchgehend rund {watt} W mehr gelaufen als "
        "sonst. Üblich sind bei dir etwa {basis} W. Was war das?"
    ),
    VERBRAUCH_HOCH: (
        "{Zeitraum} lag dein Verbrauch bei {kwh_tag} kWh am Tag statt der "
        "üblichen {basis_kwh} kWh, {stunden_text}. Was war da los?"
    ),
    NEUE_SPITZE: (
        "{Zeitraum} gab es um {stunde} Uhr eine Spitze von {peak} kW, mehr "
        "als je zuvor gemessen (bisher höchstens {basis_peak} kW). Was war das?"
    ),
    ABWESENHEIT: (
        "{Zeitraum} sah dein Zähler so aus, als wäre niemand zu Hause gewesen. "
        "Stimmt das?"
    ),
}

_ABWESENHEIT_OPTIONEN = (
    Antwortoption(label="verreist", text="Ja, ich war verreist"),
    Antwortoption(label="tagsueber_weg", text="Ja, tagsüber niemand da"),
    Antwortoption(label="war_da", text="Nein, ich war da"),
    UNBEKANNT,
)


def deute(
    ereignis: Ereignis,
    *,
    profil: ProfileSource | None = None,
    gedaechtnis: Sequence[FruehereAntwort] = (),
    arbeitspreis_ct_kwh: float | None = None,
) -> Deutung:
    """Deutet ein Ereignis: erklären, wenn wir es wissen — sonst fragen."""
    kontext = _kalender_kontext(ereignis)
    kosten = (
        round(ereignis.zusatz_kwh * arbeitspreis_ct_kwh / 100, 2)
        if arbeitspreis_ct_kwh is not None and ereignis.zusatz_kwh
        else None
    )

    if ereignis.typ == ABWESENHEIT:
        return _deute_abwesenheit(ereignis, kontext, arbeitspreis_ct_kwh)

    aus_gedaechtnis = _passende_frueher(ereignis, gedaechtnis)
    if aus_gedaechtnis is not None:
        return Deutung(
            ereignis=ereignis,
            erklaerung=(
                f"Das sieht aus wie beim letzten Mal: {aus_gedaechtnis.text}. "
                f"Du hast das am {_de_datum(aus_gedaechtnis.beantwortet_am)} "
                "so eingeordnet."
            ),
            quelle="gedaechtnis",
            kontext=kontext,
            kosten_eur=kosten,
        )

    kandidaten = _passende_kandidaten(
        ereignis, freier_tag=bool(kontext), profil=profil
    )

    aus_profil = _passender_profil_fakt(kandidaten, profil)
    if aus_profil is not None:
        kandidat, beleg = aus_profil
        return Deutung(
            ereignis=ereignis,
            erklaerung=(
                f"Das passt zu dem, was du uns schon gesagt hast: {beleg}. "
                f"{kandidat.text} erklärt eine Last dieser Größe."
            ),
            quelle="profil",
            kontext=kontext,
            kosten_eur=kosten,
        )

    optionen = tuple(
        Antwortoption(
            label=k.label,
            text=k.text,
            profil_feld=k.profil_feld,
            profil_wert=k.profil_wert,
        )
        for k in kandidaten[:MAX_OPTIONEN]
    ) + (UNBEKANNT,)

    return Deutung(
        ereignis=ereignis,
        frage=_frage(ereignis),
        optionen=optionen,
        kontext=kontext,
        kosten_eur=kosten,
    )


# --- Abwesenheit --------------------------------------------------------------


def _deute_abwesenheit(
    ereignis: Ereignis, kontext: tuple[str, ...], preis: float | None
) -> Deutung:
    """Bei Abwesenheit ist nicht das Gerät interessant, sondern der Sockel.

    Was in dieser Zeit gelaufen ist, läuft das ganze Jahr — das ist die
    einzige Gelegenheit, an der man den Grundverbrauch eines Haushalts sauber
    messen kann, ohne ihn vom Alltag getrennt zu bekommen.

    **Die Hochrechnung geht über die Energie, nicht über eine Leistung.** Eine
    Leistung aufs Jahr zu multiplizieren setzt voraus, dass sie konstant ist.
    Der Kühlschrank, der den Sockel eines leeren Haushalts dominiert, taktet
    aber — und ein Median über taktende Werte liegt immer auf einem der beiden
    Zustände, nie dazwischen. An vier Einschaltquoten nachgemessen lag die
    frühere Leistungs-Hochrechnung zwischen 27 % zu niedrig und 36 % zu hoch.
    """
    # Hochgerechnet wird die GEMESSENE Tagesenergie, nicht eine Leistung.
    # Der Weg über eine Leistung setzt voraus, dass sie konstant ist — bei
    # jedem taktenden Gerät ist sie das nicht, und der Fehler geht in beide
    # Richtungen (gemessen: −27 % bis +36 %).
    kwh_jahr = round(ereignis.kwh_tag * TAGE_PRO_JAHR, 1)
    eur_jahr = round(kwh_jahr * preis / 100, 2) if preis is not None else None
    return Deutung(
        ereignis=ereignis,
        frage=_frage(ereignis),
        optionen=_ABWESENHEIT_OPTIONEN,
        kontext=kontext,
        hochrechnung_kwh_jahr=kwh_jahr,
        hochrechnung_eur_jahr=eur_jahr,
    )


# --- Gedächtnis ---------------------------------------------------------------


def _passende_frueher(
    ereignis: Ereignis, gedaechtnis: Sequence[FruehereAntwort]
) -> FruehereAntwort | None:
    """Die jüngste frühere Antwort auf ein gleichartiges Ereignis."""
    treffer = [
        f
        for f in gedaechtnis
        if f.typ == ereignis.typ
        and _leistung_aehnlich(ereignis.zusatz_leistung_w, f.leistung_w)
        and _stunden_aehnlich(ereignis.stunden, f.stunden)
    ]
    if not treffer:
        return None
    return max(treffer, key=lambda f: f.beantwortet_am)


def _leistung_aehnlich(a: int, b: int) -> bool:
    if a <= 0 or b <= 0:
        return False
    return abs(a - b) / max(a, b) <= GEDAECHTNIS_LEISTUNG_TOLERANZ


def _stunden_aehnlich(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    if not a or not b:
        return not a and not b
    schnitt = len(set(a) & set(b))
    return schnitt / max(len(a), len(b)) >= GEDAECHTNIS_STUNDEN_UEBERLAPPUNG


# --- Kandidaten ---------------------------------------------------------------


def _passende_kandidaten(
    ereignis: Ereignis,
    *,
    freier_tag: bool = False,
    profil: ProfileSource | None = None,
) -> list[_Kandidat]:
    """Kandidaten, deren Signatur zum Ereignis passt — die spezifischsten zuerst.

    Zwei Kriterien, in dieser Reihenfolge:

    1. **Wie viele Zusatzbedingungen ein Kandidat erfüllt.** Wer außer der
       Leistung auch die Jahreszeit oder das Stundenfenster trifft, sagt mehr:
       eine neue Nachtlast im Juli ist eher ein Klimagerät als ein Aquarium,
       obwohl beide zur Leistung passen. Ohne diesen Vorrang verdrängen die
       ganzjährigen Allerweltskandidaten genau die Erklärung, die zur
       Jahreszeit passt (an 180 W im Juli aufgefallen).
    2. **Wie eng das Leistungsband ist.** „Kühlgerät (60–400 W)" ist bei 180 W
       eine präzisere Aussage als „E-Auto (1,8–22 kW)" bei 2.300 W.
    """
    watt = _leistung(ereignis)
    monat = ereignis.von.month
    ausgeschlossen = _vom_profil_ausgeschlossen(profil)
    treffer: list[tuple[int, float, _Kandidat]] = []
    for k in KANDIDATEN:
        if ereignis.typ not in k.typen:
            continue
        if k.label in ausgeschlossen:
            continue
        if k.nur_an_freien_tagen and not freier_tag:
            continue
        if not (k.watt_von <= watt <= k.watt_bis):
            continue
        spezifitaet = 0
        if k.monate is not None:
            if monat not in k.monate:
                continue
            spezifitaet += 1
        if k.stunden is not None and ereignis.stunden:
            if not set(k.stunden) & set(ereignis.stunden):
                continue
            spezifitaet += 1
        if k.min_stunden and len(ereignis.stunden) < k.min_stunden:
            continue
        if k.nur_an_freien_tagen:
            spezifitaet += 2  # der Kalender ist die stärkste verfügbare Evidenz
        treffer.append((-spezifitaet, k.watt_bis - k.watt_von, k))
    treffer.sort(key=lambda p: (p[0], p[1], p[2].label))
    return [k for _, _, k in treffer]


_NICHT_ELEKTRISCH = frozenset({"gas", "fernwaerme", "pellets", "keine"})


def _vom_profil_ausgeschlossen(profil: ProfileSource | None) -> frozenset[str]:
    """Kandidaten, die ein gespeicherter Fakt ausschließt.

    Nur dort, wo ein Feld die Frage direkt beantwortet: ``asset.heating.type``
    mit einem nicht-elektrischen Wert schließt die Wärmepumpe aus. Ein
    Heizlüfter bleibt möglich (den hat auch, wer mit Fernwärme heizt), und ein
    E-Auto kann seit der letzten Antwort dazugekommen sein — solche Kandidaten
    werden NICHT ausgeschlossen. Ein Ausschluss, den man später bereut, ist
    schlimmer als eine Option zu viel.
    """
    if profil is None:
        return frozenset()
    heizung = profil.get_fakt("asset.heating.type")
    if heizung is not None and str(heizung.wert) in _NICHT_ELEKTRISCH:
        return frozenset({"waermepumpe"})
    return frozenset()


def _leistung(ereignis: Ereignis) -> float:
    if ereignis.typ == NEUE_SPITZE:
        return ereignis.peak_kw * 1000
    return float(ereignis.zusatz_leistung_w)


def _passender_profil_fakt(
    kandidaten: list[_Kandidat], profil: ProfileSource | None
) -> tuple[_Kandidat, str] | None:
    """Erster Kandidat, für den ein gespeicherter Fakt spricht."""
    if profil is None:
        return None
    for k in kandidaten:
        if not k.profil_feld:
            continue
        fakt = profil.get_fakt(k.profil_feld)
        if fakt is None:
            continue
        wert = str(fakt.wert).strip()
        if not wert:
            continue
        gesucht = wert.casefold()
        if any(s in gesucht for s in k.stichworte) or k.profil_wert.casefold() in gesucht:
            return k, wert
    return None


# --- Frage-Texte --------------------------------------------------------------


def _frage(ereignis: Ereignis) -> str:
    vorlage = _FRAGEN[ereignis.typ]
    return vorlage.format(
        Zeitraum=_zeitraum_text(ereignis).capitalize(),
        watt=ereignis.zusatz_leistung_w,
        basis=ereignis.baseline_leistung_w,
        kwh_tag=_zahl(ereignis.kwh_tag),
        basis_kwh=_zahl(ereignis.baseline_kwh_tag),
        stunden_text=_stunden_text(ereignis.stunden),
        stunde=ereignis.stunden[0] if ereignis.stunden else 0,
        peak=_zahl(ereignis.peak_kw),
        basis_peak=_zahl(ereignis.baseline_peak_kw),
    )


def _stunden_text(stunden: tuple[int, ...]) -> str:
    if not stunden:
        return "über den Tag verteilt"
    if len(stunden) >= DURCHGEHEND_AB_STUNDEN:
        return "durchgehend, rund um die Uhr"
    if len(stunden) == 1:
        return f"vor allem um {stunden[0]} Uhr"
    bloecke = _stunden_bloecke(stunden)
    teile = [f"{a} bis {b + 1} Uhr" if a != b else f"{a} Uhr" for a, b in bloecke]
    if len(teile) == 1:
        return f"vor allem zwischen {teile[0]}"
    return "vor allem um " + ", ".join(teile[:-1]) + f" und um {teile[-1]}"


def _stunden_bloecke(stunden: tuple[int, ...]) -> list[tuple[int, int]]:
    s = sorted(stunden)
    bloecke = [(s[0], s[0])]
    for h in s[1:]:
        if h == bloecke[-1][1] + 1:
            bloecke[-1] = (bloecke[-1][0], h)
        else:
            bloecke.append((h, h))
    return bloecke


def _zeitraum_text(ereignis: Ereignis) -> str:
    if ereignis.von == ereignis.bis:
        return f"am {_de_datum(ereignis.von)}"
    return f"von {_de_datum(ereignis.von)} bis {_de_datum(ereignis.bis)}"


def _de_datum(d: date) -> str:
    return f"{d.day}.{d.month}."


def _zahl(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


# --- Kalender -----------------------------------------------------------------

_FESTE_FEIERTAGE = {
    (1, 1): "Neujahr",
    (1, 6): "Heilige Drei Könige",
    (5, 1): "Staatsfeiertag",
    (8, 15): "Mariä Himmelfahrt",
    (10, 26): "Nationalfeiertag",
    (11, 1): "Allerheiligen",
    (12, 8): "Mariä Empfängnis",
    (12, 24): "Heiliger Abend (Weihnachten)",
    (12, 25): "Weihnachten",
    (12, 26): "Stefanitag (Weihnachten)",
    (12, 31): "Silvester",
}


def _ostersonntag(jahr: int) -> date:
    """Gaußsche Osterformel — Basis der beweglichen Feiertage."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f, g = (b + 8) // 25, (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    monat = (h + m - 7 * n + 114) // 31
    tag = ((h + m - 7 * n + 114) % 31) + 1
    return date(jahr, monat, tag)


def _bewegliche_feiertage(jahr: int) -> dict[date, str]:
    o = _ostersonntag(jahr)
    return {
        o - timedelta(days=2): "Karfreitag",
        o: "Ostersonntag",
        o + timedelta(days=1): "Ostermontag",
        o + timedelta(days=39): "Christi Himmelfahrt",
        o + timedelta(days=50): "Pfingstmontag",
        o + timedelta(days=60): "Fronleichnam",
    }


def feiertag(tag: date) -> str | None:
    """Name des österreichischen Feiertags, sonst ``None``."""
    fest = _FESTE_FEIERTAGE.get((tag.month, tag.day))
    if fest:
        return fest
    return _bewegliche_feiertage(tag.year).get(tag)


def _kalender_kontext(ereignis: Ereignis) -> tuple[str, ...]:
    """Was der Kalender über den Zeitraum sagt — Feiertage und Wochenende.

    Kein Filter, sondern Kontext: dass der 24. Dezember mehr verbraucht als
    ein normaler Mittwoch, weiß der Haushalt selbst. Es ungefragt zu melden,
    ohne es zu benennen, wäre die Sorte Alarm, die man abbestellt.
    """
    kontext: list[str] = []
    tage = [
        ereignis.von + timedelta(days=i)
        for i in range((ereignis.bis - ereignis.von).days + 1)
    ]
    namen = [n for n in (feiertag(t) for t in tage) if n]
    if namen:
        kontext.append("Feiertag: " + ", ".join(dict.fromkeys(namen)))
    if any(t.weekday() >= 5 for t in tage):
        kontext.append("Wochenende")
    return tuple(kontext)
