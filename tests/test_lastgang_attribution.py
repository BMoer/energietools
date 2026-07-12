# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Trend-Attribution-Capability (L.3, HARTES DoD-Gate 15).

Reproduziert die validierte Ground-Truth aus ``CASE_09.md:3-9`` mit einer rein
**synthetischen**, PII-freien Serie (kein echter Zählpunkt, keine echten
Rohdaten — die liegen laut Spec L.3.5 nicht im Repo). Der Generator baut zwei
deckungsgleiche Jahres-Fenster mit zwei eingebauten Zuwächsen:

- **Abend-Kochen** (1–4 kW-Band, 18:00–19:59, alle Tage) — Zuwachs jahr_a→jahr_b.
- **Werktag-Tag-Elektronik** (0,1–0,3 kW-Band, 12:00–17:59, nur Werktage) — +≈73 %.

Der Test prüft, dass die Zerlegung genau diese beiden Geräte-KLASSEN als Treiber
identifiziert, den Pflicht-Caveat (15-min-Grenze) setzt und keinen Gerätenamen
ausgibt.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from energietools.capabilities.lastgang.attribution import (
    ABEND,
    BAND_01_03,
    BAND_03_1,
    BAND_1_4,
    BAND_GT4,
    SLOTS_PER_HOUR,
    TREIBER_MIN_DELTA_KWH,
    _geraete_klasse,
    band_of,
    compute_trend_attribution,
    tageszeit_of,
)
from energietools.capabilities.lastgang.attribution_capability import (
    TrendAttributionCapability,
)
from energietools.capabilities.registry import default_registry

# --- Synthetische Ground-Truth-Serie (PII-frei, rein deterministisch) ---------

_BASE_KWH = 0.02  # 0,08 kW < 0,1 kW → Grundrauschen, nicht attribuiert
_COOK = {"a": 0.40, "b": 0.60}  # Abend 18–19h: 1,6 → 2,4 kW (beide im 1–4 kW-Band)
_ELEC = {"a": 0.040, "b": 0.069}  # Werktag-Tag 12–17h: 0,16 → 0,276 kW (0,1–0,3 kW), +72,5 %

# Verbotsliste konkreter Gerätenamen — im geraete_klasse-Feld NIE erlaubt (F21).
_FORBIDDEN_NAMES = [
    "Herd",
    "Induktionsherd",
    "Induktion",
    "Backofen",
    "Backrohr",
    "Wasserkocher",
    "Kühlschrank",
    "Gefrierschrank",
    "Waschmaschine",
    "Geschirrspüler",
    "Trockner",
    "Laptop",
    "MacBook",
    "Fernseher",
    "Boiler",
    "Durchlauferhitzer",
    "Tesla",
    "Aquarium",
]


def build_case_b_series(jahr_a: int = 2025, jahr_b: int = 2026, tage: int = 84) -> list[dict]:
    """Zwei deckungsgleiche 12-Wochen-Fenster (84 Tage = exakt 60 WT / 24 WE je Jahr)."""
    cook = {jahr_a: _COOK["a"], jahr_b: _COOK["b"]}
    elec = {jahr_a: _ELEC["a"], jahr_b: _ELEC["b"]}
    recs: list[dict] = []
    for year in (jahr_a, jahr_b):
        start = date(year, 1, 6)  # gleiche (Monat,Tag)-Sequenz in beiden Jahren
        for off in range(tage):
            d = start + timedelta(days=off)
            ist_werktag = d.weekday() < 5
            for h in range(24):
                for minute in (0, 15, 30, 45):
                    if h in (18, 19):
                        kwh = cook[year]
                    elif 12 <= h < 18 and ist_werktag:
                        kwh = elec[year]
                    else:
                        kwh = _BASE_KWH
                    ts = datetime(d.year, d.month, d.day, h, minute).isoformat()
                    recs.append({"ts": ts, "kwh": round(kwh, 4)})
    return recs


# --- Rechen-Kern-Unit-Tests ---------------------------------------------------


def test_band_of_klassifiziert_leistung() -> None:
    """kW → Band; unter 0,1 kW nicht attribuierbar (None)."""
    assert band_of(0.05) is None  # Grundrauschen
    assert band_of(0.16) == BAND_01_03
    assert band_of(0.5) == "0,3–1 kW"
    assert band_of(2.0) == BAND_1_4
    assert band_of(5.0) == BAND_GT4
    # Band-Grenzen: untere Grenze inklusiv, obere exklusiv.
    assert band_of(0.1) == BAND_01_03
    assert band_of(0.3) == "0,3–1 kW"
    assert band_of(4.0) == BAND_GT4


def test_tageszeit_of_deckt_volle_24h_ab() -> None:
    """Jede Stunde 0–23 fällt in genau ein Fenster (keine Lücke, auch 23h)."""
    fenster = {tageszeit_of(h) for h in range(24)}
    assert fenster == {"nacht", "vormittag", "tag", "abend"}
    assert tageszeit_of(0) == "nacht"
    assert tageszeit_of(4) == "nacht"
    assert tageszeit_of(11) == "vormittag"
    assert tageszeit_of(17) == "tag"
    assert tageszeit_of(18) == "abend"
    assert tageszeit_of(23) == "abend"  # Stunde 23 in Abend gefaltet → volle Abdeckung
    assert SLOTS_PER_HOUR == 4


# --- DoD-Kriterium 15: Ground-Truth-Reproduktion ------------------------------


def test_attribution_reproduziert_ground_truth() -> None:
    """HARTES GATE: Abend-Zuwachs = Kochen (1–4 kW), Werktag-Tag = Elektronik (0,1–0,3 kW)."""
    result = compute_trend_attribution(build_case_b_series()).model_dump(mode="json")

    treiber = result["treiber"]
    assert treiber, "Es müssen Treiber identifiziert werden"

    # Top-Treiber = Abend-Kochen im 1–4 kW-Band (größtes delta_kwh).
    top = treiber[0]
    assert top["tageszeit"] == "abend"
    assert top["band_kw"] == BAND_1_4
    assert "Kochen" in top["geraete_klasse"]
    assert top["delta_kwh"] == pytest.approx(96.0, abs=2.0)
    assert top["delta_pct"] == pytest.approx(50.0, abs=2.0)

    # Zweiter belegter Treiber = Werktag-Tag-Elektronik im 0,1–0,3 kW-Band, +≈73 %.
    elektronik = [
        t
        for t in treiber
        if t["tageszeit"] == "tag" and t["werktag"] and t["band_kw"] == BAND_01_03
    ]
    assert elektronik, "Werktag-Tag-Elektronik-Treiber fehlt"
    et = elektronik[0]
    assert "Elektronik" in et["geraete_klasse"] or "Home-Office" in et["geraete_klasse"]
    assert et["delta_pct"] == pytest.approx(72.5, abs=2.0)  # CASE_09: +73 %

    # Genau drei attribuierte Zellen (Kochen-WT, Kochen-WE, Elektronik-WT).
    assert len(result["zerlegung"]) == 3
    assert result["anzahl_treiber"] == len(treiber)


def test_kein_wallbox_false_positive() -> None:
    """Ohne >4 kW-Nachtlast wird KEINE Wallbox/E-Auto-Klasse behauptet (F6)."""
    result = compute_trend_attribution(build_case_b_series()).model_dump(mode="json")
    for t in result["treiber"]:
        assert "Wallbox" not in t["geraete_klasse"]
        assert t["band_kw"] != BAND_GT4


# --- Finding 1: Kalender-Drift darf keinen Phantom-Treiber erzeugen ------------


def build_identische_serie(jahr_a: int = 2025, jahr_b: int = 2026, tage: int = 6) -> list[dict]:
    """Bit-identische Serie in BEIDEN Jahren (NULL reale Veränderung).

    Nur der Kalender verschiebt sich: dieselben (Monat,Tag)-Slots fallen 2025 und
    2026 auf unterschiedliche Wochentage. Bei einem Fenster, das KEINE ganze
    Wochenzahl ist (hier 6 Tage, Jan 6.–11. = Mo–Sa 2025 / Di–So 2026), ist die
    Werktag/Wochenende-Aufteilung je Jahr verschieden. Eine korrekte Attribution
    darf daraus KEINEN Treiber fabrizieren.
    """
    recs: list[dict] = []
    for year in (jahr_a, jahr_b):
        start = date(year, 1, 6)
        for off in range(tage):
            d = start + timedelta(days=off)
            for h in range(24):
                for minute in (0, 15, 30, 45):
                    kwh = 0.40 if h in (18, 19) else _BASE_KWH  # identisch je Jahr
                    ts = datetime(d.year, d.month, d.day, h, minute).isoformat()
                    recs.append({"ts": ts, "kwh": kwh})
    return recs


def test_kalender_drift_erzeugt_keinen_phantom_treiber() -> None:
    """RED-Beweis: identische Serie in beiden Jahren → KEIN Treiber, alle Δ ≈ 0.

    Der Per-Jahr-Werktag-Split über ein Nicht-ganze-Wochen-Fenster verschiebt die
    Slot-Zahlen der Werktag-/Wochenende-Zellen zwischen den Jahren; bei Rohsummen
    entsteht daraus ein Scheindelta (der Reviewer demonstrierte +2,0 kWh/+10 %).
    Bei NULL realer Veränderung MUSS jedes Zell-Δ ≈ 0 sein und es darf kein
    Treiber (schon gar keine Geräte-KLASSE-Behauptung) entstehen.
    """
    result = compute_trend_attribution(build_identische_serie()).model_dump(mode="json")

    # Kein Treiber, keine Klassen-Behauptung aus reinem Kalender-Drift.
    assert result["treiber"] == [], (
        "Phantom-Treiber aus Kalender-Drift: "
        f"{[(t['tageszeit'], t['band_kw'], t['werktag'], t['delta_kwh']) for t in result['treiber']]}"
    )
    assert result["anzahl_treiber"] == 0
    assert result["top_treiber_klasse"] is None

    # Jede Zelle: Δ kWh und Δ% praktisch 0 (mittlere Slot-Last unverändert).
    for z in result["zerlegung"]:
        assert abs(z["delta_kwh"]) < TREIBER_MIN_DELTA_KWH, z
        if z["delta_pct"] is not None:
            assert abs(z["delta_pct"]) < 1.0, z


# --- Finding 2: Abend-Kleingeräte-Band (0,3–1 kW) ist Kochen-Hypothese ---------


def test_abend_0_3_1_kw_band_ist_kochen_hypothese() -> None:
    """CASE_09/Kriterium 15: Abend-Kochen ist über 0,3–4 kW definiert, nicht nur 1–4 kW.

    Abend-Last im 0,3–1 kW-Band muss als Kochen-KLASSE (bekannte Hypothese, nicht
    'unspezifisch') gelabelt werden — analog zum 1–4 kW-Band.
    """
    klasse_03_1, konf_03_1 = _geraete_klasse(BAND_03_1, ABEND, True, 40.0, False)
    assert "Kochen" in klasse_03_1, klasse_03_1
    assert konf_03_1 != "niedrig", "bekannte Hypothese → mind. mittlere Konfidenz"
    # 1–4 kW-Band bleibt ebenfalls Kochen (Regression-Guard).
    klasse_1_4, _ = _geraete_klasse(BAND_1_4, ABEND, True, 40.0, False)
    assert "Kochen" in klasse_1_4


def build_abend_kleingeraete_serie(
    jahr_a: int = 2025, jahr_b: int = 2026, tage: int = 84
) -> list[dict]:
    """Abend-Zuwachs im 0,3–1 kW-Band (0,4 → 0,6 kW), sonst Grundrauschen."""
    evening = {jahr_a: 0.10, jahr_b: 0.15}  # 0,4 → 0,6 kW, beide im 0,3–1 kW-Band
    recs: list[dict] = []
    for year in (jahr_a, jahr_b):
        start = date(year, 1, 6)
        for off in range(tage):
            d = start + timedelta(days=off)
            for h in range(24):
                for minute in (0, 15, 30, 45):
                    kwh = evening[year] if h in (18, 19) else _BASE_KWH
                    ts = datetime(d.year, d.month, d.day, h, minute).isoformat()
                    recs.append({"ts": ts, "kwh": round(kwh, 4)})
    return recs


def test_abend_zuwachs_im_kleingeraete_band_wird_als_kochen_attribuiert() -> None:
    """Integrationstest: Abend-Zuwachs im 0,3–1 kW-Band → Kochen-Treiber (nicht 'unspezifisch')."""
    result = compute_trend_attribution(build_abend_kleingeraete_serie()).model_dump(mode="json")
    abend = [t for t in result["treiber"] if t["tageszeit"] == "abend"]
    assert abend, "Abend-Zuwachs im 0,3–1 kW-Band wurde nicht als Treiber erkannt"
    for t in abend:
        assert t["band_kw"] == BAND_03_1
        assert "Kochen" in t["geraete_klasse"], t["geraete_klasse"]
        assert "unspezifisch" not in t["geraete_klasse"]


# --- F21: Pflicht-Caveat 15-min-Auflösung -------------------------------------


def test_pflicht_caveat_15min_immer_gesetzt() -> None:
    """Der 15-min-KLASSE-Caveat ist IMMER im Result (F21)."""
    result = compute_trend_attribution(build_case_b_series()).model_dump(mode="json")
    caveats = result["caveats"]
    assert any("15-min" in c and "KLASSE" in c for c in caveats), caveats
    assert result["grenzen"]["aufloesung_min"] == 15
    assert result["grenzen"]["klasse_nicht_name"] is True


def test_kein_geraetename_im_output() -> None:
    """geraete_klasse trägt NIE einen konkreten Gerätenamen (Klasse ja, Name nein)."""
    result = compute_trend_attribution(build_case_b_series()).model_dump(mode="json")
    for t in result["treiber"]:
        klasse = t["geraete_klasse"]
        for name in _FORBIDDEN_NAMES:
            assert name not in klasse, f"Gerätename '{name}' in Klasse '{klasse}'"


# --- L.6: Nenner-Disziplin ----------------------------------------------------


def test_nenner_disziplin_jede_pct_kennzahl_hat_nenner() -> None:
    """Jede *_pct-Kennzahl im Result trägt eine Nenner-Definition (L.6.3)."""
    result = compute_trend_attribution(build_case_b_series()).model_dump(mode="json")
    nenner = result["nenner"]
    assert "delta_pct" in nenner
    # Strukturell: delta_pct kommt in zerlegung + treiber vor → Nenner muss existieren.
    pct_felder = set()
    for zelle in result["zerlegung"]:
        pct_felder |= {k for k in zelle if k.endswith("_pct")}
    for treiber in result["treiber"]:
        pct_felder |= {k for k in treiber if k.endswith("_pct")}
    for feld in pct_felder:
        assert feld in nenner, f"Nenner für {feld} fehlt"


def test_rechenweg_dokumentiert_baender_und_fenster() -> None:
    """Rechenweg trägt Band-Definitionen, Tageszeit-Fenster und Methode."""
    result = compute_trend_attribution(build_case_b_series()).model_dump(mode="json")
    rw = result["rechenweg"]
    assert BAND_1_4 in rw["baender"]
    assert BAND_01_03 in rw["baender"]
    assert set(rw["tageszeit_fenster"]) == {"nacht", "vormittag", "tag", "abend"}
    assert "Leistungsband" in rw["methode"]


# --- Jahres-Auflösung & Guards ------------------------------------------------


def test_jahre_werden_automatisch_aufgeloest() -> None:
    """Ohne jahr_a/jahr_b: die zwei jüngsten Jahre mit deckungsgleichem Fenster."""
    result = compute_trend_attribution(build_case_b_series(2025, 2026)).model_dump(mode="json")
    assert result["fenster"]["von_jahr"] == 2025
    assert result["fenster"]["bis_jahr"] == 2026
    assert result["fenster"]["gemeinsame_slots"] == 84 * 96
    assert result["fenster"]["gemeinsame_tage"] == pytest.approx(84.0, abs=0.1)


def test_drei_jahre_nehmen_die_zwei_juengsten() -> None:
    """Bei drei Jahren werden die zwei jüngsten (2025→2026) verglichen."""
    recs = build_case_b_series(2025, 2026)
    # kleines 2024-Teiljahr anhängen (soll ignoriert werden)
    recs += [
        {"ts": datetime(2024, 3, 1, h, 0).isoformat(), "kwh": 0.1} for h in range(24)
    ]
    result = compute_trend_attribution(recs).model_dump(mode="json")
    assert result["fenster"]["von_jahr"] == 2025
    assert result["fenster"]["bis_jahr"] == 2026


def test_explizite_jahre_werden_verwendet() -> None:
    """jahr_a/jahr_b explizit → genau dieses Paar."""
    result = compute_trend_attribution(
        build_case_b_series(2025, 2026), jahr_a=2025, jahr_b=2026
    ).model_dump(mode="json")
    assert result["fenster"]["von_jahr"] == 2025
    assert result["fenster"]["bis_jahr"] == 2026


# --- Capability-Envelope + Registry ------------------------------------------


def test_capability_envelope_ok() -> None:
    """Capability liefert ok=True + attribuierte Treiber im data-Envelope."""
    cap = TrendAttributionCapability()
    res = cap.run(consumption=build_case_b_series())
    assert res.ok is True
    assert res.error is None
    assert res.data["treiber"][0]["tageszeit"] == "abend"
    # result_field_paths verweist auf reale Skalare.
    pfade = cap.result_field_paths()
    assert "anzahl_treiber" in pfade
    assert pfade["grenzen.klasse_nicht_name"] == "bool"


def test_capability_leere_serie_wird_abgelehnt() -> None:
    """Leere consumption → ok=False mit Begründung (nie stiller Default)."""
    res = TrendAttributionCapability().run(consumption=[])
    assert res.ok is False
    assert res.data is None
    assert res.error


def test_capability_ein_jahr_wird_abgelehnt() -> None:
    """Nur ein Jahr in der Serie → kein YoY-Vergleich möglich → ok=False."""
    recs = [
        {"ts": datetime(2026, 3, 1, h, m).isoformat(), "kwh": 0.1}
        for h in range(24)
        for m in (0, 15, 30, 45)
    ]
    res = TrendAttributionCapability().run(consumption=recs)
    assert res.ok is False
    assert res.error


def test_capability_kein_gemeinsames_fenster_wird_abgelehnt() -> None:
    """Disjunkte Fenster (Jan vs Jul) → kein deckungsgleiches Fenster → ok=False."""
    recs = [
        {"ts": datetime(2025, 1, 10, h, 0).isoformat(), "kwh": 0.2} for h in range(24)
    ] + [{"ts": datetime(2026, 7, 10, h, 0).isoformat(), "kwh": 0.2} for h in range(24)]
    res = TrendAttributionCapability().run(consumption=recs)
    assert res.ok is False
    assert res.error


def test_registry_enthaelt_trend_attribution() -> None:
    """Die Capability ist in der Default-Registry registriert."""
    reg = default_registry()
    assert "trend_attribution" in reg.names
    cap = reg.get("trend_attribution")
    assert cap.name == "trend_attribution"
    assert cap.summary
