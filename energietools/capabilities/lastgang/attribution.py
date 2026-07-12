# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Trend-Attribution (L.3) — Rechen-Kern (offline, deterministisch).

Zerlegt das YoY-Delta einer 15-min-Verbrauchsserie nach **Leistungsband ×
Tageszeit × Werktag/Wochenende** und leitet je Treiber-Zelle eine Geräte-KLASSE
als Hypothese ab (NIE einen Gerätenamen — 15-min-Auflösungsgrenze, F21).

Methode neu implementiert nach der validierten Beschreibung in
``gridbert/analysen/09_lastgang/CASE_09.md:3-9`` (kein Copy-Port; MIT). Kein
LLM, keine DB, keine Netz-Abhängigkeit — die Zahlen kommen ausschließlich aus
dieser Datei (L.6: keine Zahl „im Kopf").
"""

from __future__ import annotations

import datetime as _dt
from collections import defaultdict

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.lastgang.attribution_models import (
    AttributionFenster,
    Treiber,
    TrendAttributionResult,
    ZerlegungsZelle,
)

# --- Konversion & Bänder (keine Magic Numbers) --------------------------------

SLOTS_PER_HOUR = 4  # 15-min-Slot → Momentanleistung: kW = kWh_slot × 4 (F7)
UNTERGRENZE_KW = 0.1  # darunter Grundrauschen, nicht attribuierbar

BAND_01_03 = "0,1–0,3 kW"
BAND_03_1 = "0,3–1 kW"
BAND_1_4 = "1–4 kW"
BAND_GT4 = ">4 kW"

# (Label, untere Grenze inklusiv, obere Grenze exklusiv) — aus der Ground-Truth abgeleitet.
_BAENDER: tuple[tuple[str, float, float], ...] = (
    (BAND_01_03, 0.1, 0.3),  # Elektronik/Standby→aktiv
    (BAND_03_1, 0.3, 1.0),  # Kleingeräte
    (BAND_1_4, 1.0, 4.0),  # Kochen/Küche — sustained
    (BAND_GT4, 4.0, float("inf")),  # Großlast/Spitze
)

_BAND_BESCHREIBUNG: dict[str, str] = {
    BAND_01_03: "Elektronik/Standby-aktiv",
    BAND_03_1: "Kleingeräte",
    BAND_1_4: "Kochen/Küche (sustained)",
    BAND_GT4: "Großlast/Spitze",
}

# --- Tageszeit-Fenster (volle 24h-Abdeckung; Stunde 23 in Abend gefaltet) ------

NACHT = "nacht"
VORMITTAG = "vormittag"
TAG = "tag"
ABEND = "abend"

_NACHT_HOURS = range(0, 5)  # 00:00–04:59 (= Dauerläufer-/Wallbox-Fenster, F9)
_VORMITTAG_HOURS = range(5, 12)  # 05:00–11:59
_TAG_HOURS = range(12, 18)  # 12:00–17:59 (Werktag-Tag = Home-Office-Muster)
_ABEND_HOURS = range(18, 24)  # 18:00–23:59

_TAGESZEIT_FENSTER: dict[str, str] = {
    NACHT: "00:00–04:59",
    VORMITTAG: "05:00–11:59",
    TAG: "12:00–17:59",
    ABEND: "18:00–23:59",
}

# --- Treiber-/Konfidenz-Schwellen ---------------------------------------------

TREIBER_MIN_DELTA_KWH = 1.0  # Zellen unter diesem Zuwachs sind kein Treiber (Rauschen)
TREIBER_TOP_N = 5  # maximale Anzahl ausgewiesener Treiber
KONFIDENZ_PCT_SCHWELLE = 30.0  # ab diesem Δ% gilt eine bekannte Klasse als „hoch"
NAECHTE_HAEUFUNG_MIN = 5  # Mindest-Nächte mit >4 kW für die Wallbox-Klasse (F6)

# Pflicht-Caveat (F21) — IMMER gesetzt.
_CAVEAT_15MIN = (
    "15-min-Auflösung: sustained Lasten (Backrohr, AC, WP) sind isolierbar, "
    "schnell taktende Einzelgeräte (Induktion) nicht — die Aussage ist eine "
    "Geräte-KLASSE, nicht ein Gerätename."
)


# --- Reine Klassifikatoren ----------------------------------------------------


def band_of(kw: float) -> str | None:
    """Leistung (kW) → Band-Label. Unter ``UNTERGRENZE_KW`` → None (nicht attribuierbar)."""
    if kw < UNTERGRENZE_KW:
        return None
    for label, low, high in _BAENDER:
        if low <= kw < high:
            return label
    return None


def tageszeit_of(hour: int) -> str:
    """Stunde (0–23) → Tageszeit-Fenster (volle Abdeckung, keine Lücke)."""
    if hour in _NACHT_HOURS:
        return NACHT
    if hour in _VORMITTAG_HOURS:
        return VORMITTAG
    if hour in _TAG_HOURS:
        return TAG
    return ABEND  # 18–23h


# --- Eingabe-Parsing (Validierung an der Systemgrenze) ------------------------


def _parse_records(consumption: object) -> list[tuple[_dt.datetime, float]]:
    """Serie [{ts, kwh}] → [(datetime, kwh)]. Wirft CapabilityError bei Fehlern."""
    if not consumption or not isinstance(consumption, (list, tuple)):
        raise CapabilityError("consumption ist erforderlich (Serie [{ts, kwh}])")
    out: list[tuple[_dt.datetime, float]] = []
    for i, rec in enumerate(consumption):
        if not isinstance(rec, dict):
            raise CapabilityError(f"consumption[{i}] ist kein Objekt {{ts, kwh}}")
        ts = rec.get("ts", rec.get("timestamp"))
        if ts is None:
            raise CapabilityError(f"consumption[{i}] hat kein Feld 'ts'")
        try:
            dt = ts if isinstance(ts, _dt.datetime) else _dt.datetime.fromisoformat(str(ts))
        except ValueError as exc:
            raise CapabilityError(f"consumption[{i}]: ungültiger Zeitstempel '{ts}'") from exc
        kwh_raw = rec.get("kwh")
        if kwh_raw is None:
            raise CapabilityError(f"consumption[{i}] hat kein Feld 'kwh'")
        try:
            kwh = float(kwh_raw)
        except (TypeError, ValueError) as exc:
            raise CapabilityError(f"consumption[{i}]: kwh '{kwh_raw}' nicht numerisch") from exc
        out.append((dt, kwh))
    return out


def _resolve_years(
    cons: list[tuple[_dt.datetime, float]], jahr_a: int | None, jahr_b: int | None
) -> tuple[int, int]:
    """Vergleichsjahre bestimmen: explizit oder die zwei jüngsten Jahre der Serie."""
    jahre = sorted({dt.year for dt, _ in cons})
    if jahr_a is not None and jahr_b is not None:
        if jahr_a not in jahre:
            raise CapabilityError(f"jahr_a={jahr_a} ist nicht in der Serie enthalten")
        if jahr_b not in jahre:
            raise CapabilityError(f"jahr_b={jahr_b} ist nicht in der Serie enthalten")
        if jahr_a >= jahr_b:
            raise CapabilityError("jahr_a muss vor jahr_b liegen")
        return jahr_a, jahr_b
    if len(jahre) < 2:
        raise CapabilityError(
            "Attribution braucht mindestens zwei Kalenderjahre in der Serie"
        )
    return jahre[-2], jahre[-1]


def _common_keys(
    cons: list[tuple[_dt.datetime, float]], ya: int, yb: int
) -> set[tuple[int, int, int, int]]:
    """(Monat,Tag,Std,Min)-Slots, die in BEIDEN Jahren existieren (wie load_trend)."""
    keys_a: set[tuple[int, int, int, int]] = set()
    keys_b: set[tuple[int, int, int, int]] = set()
    for dt, _ in cons:
        if dt.year == ya:
            keys_a.add((dt.month, dt.day, dt.hour, dt.minute))
        elif dt.year == yb:
            keys_b.add((dt.month, dt.day, dt.hour, dt.minute))
    return keys_a & keys_b


# --- Geräte-KLASSE-Hypothese (deterministisch, nie ein Gerätename) ------------


def _geraete_klasse(
    band: str, tageszeit: str, werktag: bool, delta_pct: float | None, naechte_haeufung: bool
) -> tuple[str, str]:
    """(Band × Tageszeit) → (Geräte-KLASSE, Konfidenz). Klasse ja, Name nein."""
    bekannt = False
    if tageszeit == ABEND and band == BAND_1_4:
        klasse, bekannt = "Kochen/Küche (sustained)", True
    elif tageszeit == TAG and werktag and band == BAND_01_03:
        klasse, bekannt = "Elektronik/Home-Office (Standby→aktiv)", True
    elif tageszeit == NACHT and band == BAND_GT4:
        if naechte_haeufung:
            klasse, bekannt = "Wallbox/E-Auto (Nachtladung)", True
        else:
            # Magnitude ohne Frequenz — keine Wallbox-Behauptung (F6).
            return "Großlast nachts (unspezifisch, keine Nächte-Häufung)", "niedrig"
    else:
        return f"unspezifische Last im Band {band} ({tageszeit})", "niedrig"

    if bekannt and delta_pct is not None and delta_pct >= KONFIDENZ_PCT_SCHWELLE:
        return klasse, "hoch"
    return klasse, "mittel"


def _beleg(band: str, tageszeit: str, werktag: bool, a: float, b: float, pct: float | None) -> str:
    tag_label = "Werktag" if werktag else "Wochenende"
    pct_txt = f"{pct:+.1f} %" if pct is not None else "n/a (kwh_a=0)"
    return (
        f"Δ {b - a:+.1f} kWh im Band {band} ({tageszeit}, {tag_label}); "
        f"{a:.1f} → {b:.1f} kWh ({pct_txt})"
    )


def _delta_pct(a: float, b: float) -> float | None:
    return round(100.0 * (b / a - 1.0), 1) if a > 0 else None


# --- Hauptfunktion ------------------------------------------------------------


def compute_trend_attribution(
    consumption: object, jahr_a: int | None = None, jahr_b: int | None = None
) -> TrendAttributionResult:
    """Zerlegt das YoY-Delta nach Leistungsband × Tageszeit und benennt Treiber-KLASSEN.

    Args:
        consumption: 15-min-Serie ``[{ts: ISO, kwh: float}, …]`` (Mehrjahres-Serie).
        jahr_a: Basisjahr; wenn None → zweitjüngstes Jahr der Serie.
        jahr_b: Vergleichsjahr; wenn None → jüngstes Jahr der Serie.

    Returns:
        :class:`TrendAttributionResult` mit Zerlegung, Treiber-KLASSEN, Rechenweg,
        Caveats (F21 IMMER) und Nenner-Definitionen (L.6).
    """
    cons = _parse_records(consumption)
    ya, yb = _resolve_years(cons, jahr_a, jahr_b)
    common = _common_keys(cons, ya, yb)
    if not common:
        raise CapabilityError(
            f"Kein deckungsgleiches Fenster zwischen {ya} und {yb} "
            "(keine gemeinsamen Monat,Tag,Std,Min-Slots)"
        )

    # Zerlegung: kWh je (Band × Tageszeit × WT/WE)-Zelle, je Jahr.
    cell_a: dict[tuple[str, str, bool], float] = defaultdict(float)
    cell_b: dict[tuple[str, str, bool], float] = defaultdict(float)
    naechte_gt4: dict[tuple[str, str, bool], set[_dt.date]] = defaultdict(set)
    for dt, kwh in cons:
        if dt.year not in (ya, yb):
            continue
        if (dt.month, dt.day, dt.hour, dt.minute) not in common:
            continue
        band = band_of(kwh * SLOTS_PER_HOUR)
        if band is None:  # Grundrauschen — nicht attribuierbar
            continue
        tageszeit = tageszeit_of(dt.hour)
        werktag = dt.weekday() < 5
        cell = (band, tageszeit, werktag)
        if dt.year == ya:
            cell_a[cell] += kwh
        else:
            cell_b[cell] += kwh
            if band == BAND_GT4 and tageszeit == NACHT:
                naechte_gt4[cell].add(dt.date())

    alle_zellen = set(cell_a) | set(cell_b)
    zerlegung: list[ZerlegungsZelle] = []
    for band, tageszeit, werktag in alle_zellen:
        a = round(cell_a.get((band, tageszeit, werktag), 0.0), 1)
        b = round(cell_b.get((band, tageszeit, werktag), 0.0), 1)
        raw_a = cell_a.get((band, tageszeit, werktag), 0.0)
        raw_b = cell_b.get((band, tageszeit, werktag), 0.0)
        zerlegung.append(
            ZerlegungsZelle(
                band_kw=band,
                tageszeit=tageszeit,
                werktag=werktag,
                kwh_a=a,
                kwh_b=b,
                delta_kwh=round(raw_b - raw_a, 1),
                delta_pct=_delta_pct(raw_a, raw_b),
            )
        )
    zerlegung.sort(key=lambda z: z.delta_kwh, reverse=True)

    # Treiber: Zellen mit dem größten positiven Zuwachs (→ Geräte-KLASSE-Hypothese).
    treiber: list[Treiber] = []
    for zelle in zerlegung:
        if zelle.delta_kwh < TREIBER_MIN_DELTA_KWH:
            continue
        cell = (zelle.band_kw, zelle.tageszeit, zelle.werktag)
        haeufung = len(naechte_gt4.get(cell, set())) >= NAECHTE_HAEUFUNG_MIN
        klasse, konfidenz = _geraete_klasse(
            zelle.band_kw, zelle.tageszeit, zelle.werktag, zelle.delta_pct, haeufung
        )
        treiber.append(
            Treiber(
                geraete_klasse=klasse,
                band_kw=zelle.band_kw,
                tageszeit=zelle.tageszeit,
                werktag=zelle.werktag,
                delta_kwh=zelle.delta_kwh,
                delta_pct=zelle.delta_pct,
                konfidenz=konfidenz,
                beleg=_beleg(
                    zelle.band_kw,
                    zelle.tageszeit,
                    zelle.werktag,
                    zelle.kwh_a,
                    zelle.kwh_b,
                    zelle.delta_pct,
                ),
            )
        )
        if len(treiber) >= TREIBER_TOP_N:
            break

    fenster = AttributionFenster(
        von_jahr=ya,
        bis_jahr=yb,
        gemeinsame_slots=len(common),
        gemeinsame_tage=round(len(common) / (24 * SLOTS_PER_HOUR), 1),
    )

    return TrendAttributionResult(
        fenster=fenster,
        zerlegung=zerlegung,
        treiber=treiber,
        anzahl_zellen=len(zerlegung),
        anzahl_treiber=len(treiber),
        top_treiber_klasse=treiber[0].geraete_klasse if treiber else None,
        top_treiber_delta_kwh=treiber[0].delta_kwh if treiber else None,
        rechenweg={
            "baender": dict(_BAND_BESCHREIBUNG),
            "untergrenze": f"<{UNTERGRENZE_KW} kW = Grundrauschen, nicht attribuiert",
            "tageszeit_fenster": dict(_TAGESZEIT_FENSTER),
            "methode": (
                "YoY-Delta je Leistungsband × Tageszeit "
                "(deckungsgleiches Fenster wie load_trend)"
            ),
            "slot_zu_kw": f"kW = kWh_slot × {SLOTS_PER_HOUR} (15-min-Slot → Momentanleistung)",
            "werktag_wochenende": "Mo–Fr = Werktag, Sa/So = Wochenende (je Jahr eigener Kalender)",
        },
        caveats=[
            _CAVEAT_15MIN,
            "Klasse ja, Name nein: die Zuordnung Leistungsband×Tageszeit → Geräteklasse "
            "ist eine Hypothese, kein Nachweis eines konkreten Geräts.",
            "Vergleich nur über das deckungsgleiche (Monat,Tag,Std,Min)-Fenster beider "
            "Jahre — Teiljahre werden nicht gegen Volljahre gerechnet.",
            f"kW je Slot = kWh × {SLOTS_PER_HOUR} (15-min-Auflösung); die Bänder gelten "
            "für 15-min-Serien.",
        ],
        nenner={
            "delta_pct": "kWh_a der jeweiligen Zelle (Band×Tageszeit×Werktag/Wochenende)",
            "gemeinsame_tage": "gemeinsame_slots ÷ 96 (Slots/Tag)",
        },
        grenzen={"aufloesung_min": 15, "klasse_nicht_name": True},
    )
