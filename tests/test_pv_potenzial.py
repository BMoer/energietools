# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""PV-Potenzial + Speicher-Dimensionierung — adversariale Prüfung.

Die Tests sind bewusst NICHT als „läuft durch"-Rauchtests gebaut. Jeder prüft
eine Aussage, die falsch sein KÖNNTE, und die meisten leiten das Ergebnis
unabhängig ein zweites Mal her (andere Implementierung, dieselbe Zahl).

Das PVGIS-Profil ist ein eingefrorenes echtes Profil (Sulz im Wienerwald,
35 Grad Süd) — kein Netzzugriff im Test.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from energietools.capabilities.pv.capability import (
    PVPotenzialCapability,
    SpeicherDimensionierungCapability,
)
from energietools.capabilities.pv.potenzial import (
    Lastreihe,
    PVPotenzialFehler,
    bezugspreis,
    erzeugungsreihe,
    jahresmodell,
    lastreihe_aus_messwerten,
    nutzen,
    pv_bilanz,
    tagessummen_aus_messwerten,
)
from energietools.capabilities.pv.profil import (
    PVStundenprofil,
    azimut_aus_ausrichtung,
    profil_aus_stundenliste,
)
from energietools.capabilities.registry import default_registry
from energietools.capabilities.scenarios.dispatch import (
    MarketTerms,
    run_self_consumption,
    simulate_battery,
)
from energietools.capabilities.scenarios.peak_shaving import run_peak_shaving
from energietools.components.battery import Battery

FIXTURE = Path(__file__).parent / "fixtures" / "pvgis_sulz_35_sued.json"


@pytest.fixture(scope="module")
def profil() -> PVStundenprofil:
    roh = json.loads(FIXTURE.read_text())
    return profil_aus_stundenliste(
        [
            {"monat": m, "tag": t, "stunde": s, "kwh_pro_kwp": v}
            for m, t, s, v in roh["stunden"]
        ],
        lat=roh["lat"],
        lon=roh["lon"],
        neigung_grad=roh["neigung_grad"],
        azimut_grad=roh["azimut_grad"],
        quelle="pvgis-fixture",
        datensatz=roh["datensatz"],
    )


def _q15_reihe(tage: int = 120, start: date = date(2025, 3, 1)) -> Lastreihe:
    """Deterministischer Haushalt: Grundlast + Morgen-/Abendspitze, 15-min-Raster."""
    zeitpunkte: list[datetime] = []
    werte: list[float] = []
    beginn = datetime(start.year, start.month, start.day)
    for tag in range(tage):
        for slot in range(96):
            ts = beginn + timedelta(days=tag, minutes=15 * slot)
            stunde = slot / 4.0
            kw = 0.25
            if 6.5 <= stunde < 8.0:
                kw += 1.2
            if 18.0 <= stunde < 21.5:
                kw += 1.8
            # leichte Wochenend-Anhebung, damit die Muster-Auswahl etwas zu tun hat
            if ts.weekday() >= 5:
                kw *= 1.15
            zeitpunkte.append(ts)
            werte.append(kw * 0.25)
    return Lastreihe(tuple(zeitpunkte), tuple(werte), dt_hours=0.25)


@pytest.fixture(scope="module")
def reihe() -> Lastreihe:
    return _q15_reihe()


# ---------------------------------------------------------------------------
# Profil
# ---------------------------------------------------------------------------


def test_profil_jahresertrag_liegt_im_oesterreichischen_band(profil: PVStundenprofil) -> None:
    # AT-Aufdach Süd 35 Grad: ~950-1300 kWh/kWp. Ausserhalb waere das Profil kaputt.
    assert 900 < profil.jahresertrag_kwh_pro_kwp < 1400


def test_profil_verweigert_teilreihe() -> None:
    with pytest.raises(ValueError, match="mindestens"):
        profil_aus_stundenliste(
            [{"monat": 1, "tag": 1, "stunde": h, "kwh_pro_kwp": 0.0} for h in range(24)]
        )


def test_profil_verweigert_negative_ertraege(profil: PVStundenprofil) -> None:
    werte = dict(profil.werte)
    werte[(6, 15, 12)] = -1.0
    with pytest.raises(ValueError, match="negativ"):
        PVStundenprofil(werte, 0.0, 0.0, 35, 0, "test")


def test_schalttag_faellt_auf_28_februar_zurueck() -> None:
    werte = {
        (m, t, h): 0.5
        for m in range(1, 13)
        for t in range(1, 32)
        for h in range(24)
    }
    del werte[(2, 29, 12)]
    p = PVStundenprofil(werte, 0.0, 0.0, 35, 0, "test")
    assert p.ertrag(datetime(2024, 2, 29, 12), kwp=1.0, dt_hours=1.0) == 0.5


def test_ausrichtung_ohne_stillen_default() -> None:
    assert azimut_aus_ausrichtung("Südwest") == 45
    assert azimut_aus_ausrichtung("sued") == 0
    with pytest.raises(ValueError, match="Unbekannte Ausrichtung"):
        azimut_aus_ausrichtung("schräg nach oben")


# ---------------------------------------------------------------------------
# Physik: Erhaltungssätze und Grenzen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kwp", [1.0, 5.0, 10.0, 30.0])
@pytest.mark.parametrize("speicher", [0.0, 5.0, 20.0])
def test_energiebilanz_schliesst(
    reihe: Lastreihe, profil: PVStundenprofil, kwp: float, speicher: float
) -> None:
    b = pv_bilanz(reihe, profil, kwp=kwp, speicher_kwh=speicher)
    # Erzeugung = Eigenverbrauch(direkt) + Speicherladung(bus) + Einspeisung
    # Verbrauch  = Eigenverbrauch(direkt) + Entladung + Netzbezug
    assert b.eigenverbrauch_direkt_kwh + b.eigenverbrauch_speicher_kwh + b.netzbezug_kwh == (
        pytest.approx(b.verbrauch_kwh, rel=1e-6)
    )
    assert b.eigenverbrauch_kwh + b.einspeisung_kwh <= b.ertrag_kwh + 1e-6


@pytest.mark.parametrize("kwp", [1.0, 10.0, 50.0])
def test_kennzahlen_bleiben_in_ihren_grenzen(
    reihe: Lastreihe, profil: PVStundenprofil, kwp: float
) -> None:
    b = pv_bilanz(reihe, profil, kwp=kwp, speicher_kwh=10.0)
    assert 0.0 <= b.eigenverbrauchsquote <= 1.0
    assert 0.0 <= b.autarkiegrad <= 1.0
    assert b.eigenverbrauch_kwh <= b.verbrauch_kwh + 1e-6
    assert b.eigenverbrauch_kwh <= b.ertrag_kwh + 1e-6


def test_speicher_erzeugt_keine_energie(reihe: Lastreihe, profil: PVStundenprofil) -> None:
    b = pv_bilanz(reihe, profil, kwp=10.0, speicher_kwh=15.0)
    # Entladen kann nie mehr sein als geladen (Wirkungsgrad < 1).
    geladen_bus = (
        b.eigenverbrauch_speicher_kwh
        + b.speicher_verlust_kwh
        + b.speicher_restfuellung_kwh
    )
    assert b.eigenverbrauch_speicher_kwh <= geladen_bus + 1e-9
    assert b.speicher_verlust_kwh >= 0.0


def test_ertrag_skaliert_streng_linear_mit_kwp(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    e1 = sum(erzeugungsreihe(reihe, profil, 1.0))
    e7 = sum(erzeugungsreihe(reihe, profil, 7.0))
    assert e7 == pytest.approx(7.0 * e1, rel=1e-12)


# ---------------------------------------------------------------------------
# Monotonie — die Aussagen, auf die eine Empfehlung sich stützt
# ---------------------------------------------------------------------------


def test_groessere_anlage_senkt_quote_und_hebt_autarkie(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    vorher = None
    for kwp in (1.0, 3.0, 5.0, 10.0, 20.0, 40.0):
        b = pv_bilanz(reihe, profil, kwp=kwp, speicher_kwh=0.0)
        if vorher is not None:
            assert b.ertrag_kwh > vorher.ertrag_kwh
            assert b.eigenverbrauchsquote <= vorher.eigenverbrauchsquote + 1e-9
            assert b.autarkiegrad >= vorher.autarkiegrad - 1e-9
            assert b.netzbezug_kwh <= vorher.netzbezug_kwh + 1e-9
        vorher = b


def test_groesserer_speicher_ist_nie_schlechter(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    vorher = None
    for kwh in (0.0, 2.0, 5.0, 10.0, 20.0, 50.0):
        b = pv_bilanz(reihe, profil, kwp=10.0, speicher_kwh=kwh)
        if vorher is not None:
            assert b.autarkiegrad >= vorher.autarkiegrad - 1e-9
            assert b.netzbezug_kwh <= vorher.netzbezug_kwh + 1e-9
            assert b.einspeisung_kwh <= vorher.einspeisung_kwh + 1e-9
        vorher = b


def test_grenznutzen_des_speichers_faellt(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    """Die tragende Aussage der Dimensionierung: die nächste kWh bringt weniger."""
    autarkie = [
        pv_bilanz(reihe, profil, kwp=10.0, speicher_kwh=k).autarkiegrad
        for k in (0.0, 5.0, 10.0, 15.0, 20.0)
    ]
    zuwaechse = [b - a for a, b in zip(autarkie, autarkie[1:], strict=False)]
    assert all(z >= -1e-9 for z in zuwaechse)
    # konkav: jeder Zuwachs höchstens so groß wie der vorherige
    assert all(
        spaeter <= frueher + 1e-9
        for frueher, spaeter in zip(zuwaechse, zuwaechse[1:], strict=False)
    )


# ---------------------------------------------------------------------------
# Unabhängige Zweitherleitung
# ---------------------------------------------------------------------------


def test_bilanz_ohne_speicher_gegen_naive_zweitrechnung(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    """Zweite, absichtlich dumme Implementierung — muss aufs Bit dasselbe liefern."""
    kwp = 8.0
    eigen = einspeisung = bezug = 0.0
    for ts, last in zip(reihe.zeitpunkte, reihe.kwh, strict=True):
        erzeugt = profil.werte.get((ts.month, ts.day, ts.hour), 0.0) * kwp * reihe.dt_hours
        direkt = min(last, erzeugt)
        eigen += direkt
        einspeisung += erzeugt - direkt
        bezug += last - direkt

    # Toleranz = die Anzeige-Rundung der Bilanz (3 Nachkommastellen), sonst nichts.
    b = pv_bilanz(reihe, profil, kwp=kwp, speicher_kwh=0.0)
    assert b.eigenverbrauch_kwh == pytest.approx(eigen, abs=5e-4)
    assert b.einspeisung_kwh == pytest.approx(einspeisung, abs=5e-4)
    assert b.netzbezug_kwh == pytest.approx(bezug, abs=5e-4)


def test_speicherbilanz_gegen_handgerechneten_sonderfall(profil: PVStundenprofil) -> None:
    """Ein Tag, ein Slot Sonne, ein Slot Last — Ergebnis von Hand nachvollziehbar."""
    werte = {(m, t, h): 0.0 for m in range(1, 13) for t in range(1, 32) for h in range(24)}
    werte[(6, 15, 12)] = 4.0  # 4 kWh je kWp in einer Stunde
    p = PVStundenprofil(werte, 0.0, 0.0, 35, 0, "test")
    zeitpunkte = tuple(datetime(2025, 6, 15, h) for h in range(24))
    last = tuple(0.0 if h != 20 else 3.0 for h in range(24))
    r = Lastreihe(zeitpunkte, last, dt_hours=1.0)

    b = pv_bilanz(r, p, kwp=1.0, speicher_kwh=10.0)
    # Erzeugung 4 kWh um 12 Uhr, Last 0 -> alles in den Speicher (95 % Ladewirkungsgrad),
    # aber C-Rate 0,5 begrenzt auf 10 * 0,5 * 1 h = 5 kWh Bus-seitig -> nicht bindend.
    # SOC nach Laden: min_soc 0,5 + 4 * 0,95 = 4,3; max_soc 9,5 -> nicht bindend.
    # Um 20 Uhr: Bedarf 3 kWh, entladbar (4,3 - 0,5) = 3,8 SOC-seitig,
    # Bedarf SOC-seitig 3 / 0,95 = 3,1579; C-Rate-Grenze 5 -> liefert 3 kWh.
    assert b.ertrag_kwh == pytest.approx(4.0)
    assert b.eigenverbrauch_direkt_kwh == pytest.approx(0.0)
    assert b.eigenverbrauch_speicher_kwh == pytest.approx(3.0, rel=1e-9)
    assert b.netzbezug_kwh == pytest.approx(0.0, abs=1e-9)
    assert b.einspeisung_kwh == pytest.approx(0.0, abs=1e-9)
    assert b.autarkiegrad == pytest.approx(1.0)
    # 4 kWh geladen (Bus), 3,1579 SOC entnommen, 0,2 Ladeverlust -> Rest bleibt drin
    assert b.speicher_restfuellung_kwh > 0.0


def test_nachtverbrauch_ohne_speicher_hat_null_eigenverbrauch(
    profil: PVStundenprofil,
) -> None:
    zeitpunkte = tuple(
        datetime(2025, 6, 15) + timedelta(hours=h) for h in range(24 * 7)
    )
    # Last ausschließlich zwischen 23 und 03 Uhr UTC — dort ist der PV-Ertrag 0.
    last = tuple(1.0 if (ts.hour >= 23 or ts.hour < 3) else 0.0 for ts in zeitpunkte)
    r = Lastreihe(zeitpunkte, last, dt_hours=1.0)
    ohne = pv_bilanz(r, profil, kwp=10.0, speicher_kwh=0.0)
    mit = pv_bilanz(r, profil, kwp=10.0, speicher_kwh=20.0)
    assert ohne.eigenverbrauch_kwh == pytest.approx(0.0, abs=1e-9)
    assert ohne.autarkiegrad == pytest.approx(0.0, abs=1e-9)
    assert mit.eigenverbrauch_kwh > 0.0


# ---------------------------------------------------------------------------
# Auflösung: was kostet das Glätten der PV-Stunde?
# ---------------------------------------------------------------------------


def test_stundenglaettung_ueberschaetzt_nicht(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    """Q15-Last gegen stündlich aggregierte Last — die Richtung des Fehlers messen.

    Wer die Last auf Stunden aggregiert (wie es ein reiner Stundenabgleich täte),
    glättet die Lastspitzen weg und bekommt eine HÖHERE Deckung. Die hier
    gewählte Variante (Last in voller Q15-Auflösung, PV-Stunde geviertelt) darf
    deshalb nicht über dem Stundenwert liegen.
    """
    fein = pv_bilanz(reihe, profil, kwp=10.0, speicher_kwh=0.0)

    stunden: dict[datetime, float] = {}
    for ts, kwh in zip(reihe.zeitpunkte, reihe.kwh, strict=True):
        stunden[ts.replace(minute=0)] = stunden.get(ts.replace(minute=0), 0.0) + kwh
    grob_reihe = Lastreihe(
        tuple(sorted(stunden)), tuple(stunden[t] for t in sorted(stunden)), dt_hours=1.0
    )
    grob = pv_bilanz(grob_reihe, profil, kwp=10.0, speicher_kwh=0.0)

    assert grob.verbrauch_kwh == pytest.approx(fein.verbrauch_kwh, rel=1e-9)
    assert grob.ertrag_kwh == pytest.approx(fein.ertrag_kwh, rel=1e-9)
    assert fein.eigenverbrauch_kwh <= grob.eigenverbrauch_kwh + 1e-9


# ---------------------------------------------------------------------------
# Eingangs-Guards
# ---------------------------------------------------------------------------


def test_tageswerte_werden_abgelehnt() -> None:
    messwerte = [
        {"timestamp": datetime(2025, 1, 1) + timedelta(days=d), "kwh": 12.0}
        for d in range(40)
    ]
    with pytest.raises(PVPotenzialFehler, match="Viertelstundenwerte"):
        lastreihe_aus_messwerten(messwerte)


def test_leere_und_zu_kurze_reihe_werden_abgelehnt() -> None:
    with pytest.raises(PVPotenzialFehler):
        lastreihe_aus_messwerten([])
    with pytest.raises(PVPotenzialFehler):
        lastreihe_aus_messwerten([{"timestamp": datetime(2025, 1, 1), "kwh": 1.0}])


def test_negative_kwp_wird_abgelehnt(reihe: Lastreihe, profil: PVStundenprofil) -> None:
    with pytest.raises(PVPotenzialFehler, match="negativ"):
        erzeugungsreihe(reihe, profil, -1.0)


def test_doppelte_zeitstempel_werden_abgelehnt() -> None:
    """Duplikate würden aufaddiert und den Verbrauch still erhöhen."""
    basis = [
        {"timestamp": datetime(2025, 6, 1) + timedelta(minutes=15 * i), "kwh": 0.2}
        for i in range(200)
    ]
    with pytest.raises(PVPotenzialFehler, match="doppelte Zeitstempel"):
        lastreihe_aus_messwerten(basis + basis[:3])


# ---------------------------------------------------------------------------
# Jahresmodell
# ---------------------------------------------------------------------------


def test_jahresmodell_erhaelt_die_gemessenen_tagessummen() -> None:
    q15 = _q15_reihe(tage=30, start=date(2025, 6, 1))
    tagessummen = {
        date(2025, 1, 1) + timedelta(days=d): 8.0 + (d % 7) for d in range(365)
    }
    jm = jahresmodell(q15, tagessummen, bis_tag=date(2025, 12, 31))
    assert jm.tage_mit_gemessener_tagessumme if False else jm.tage_mit_tagessumme == 365
    # Die Tagessumme ist gemessen und darf durch das Modell nicht verändert werden.
    erwartet = sum(tagessummen[date(2025, 1, 1) + timedelta(days=d)] for d in range(365))
    assert jm.reihe.summe_kwh == pytest.approx(erwartet, rel=1e-9)
    assert len(jm.reihe.zeitpunkte) == 365 * 24


def test_jahresmodell_ohne_vollstaendigen_mustertag_verweigert() -> None:
    # Nur ein halber Tag Q15 -> kein vollständiger Mustertag.
    zeitpunkte = tuple(datetime(2025, 6, 1) + timedelta(minutes=15 * i) for i in range(40))
    q15 = Lastreihe(zeitpunkte, tuple(0.2 for _ in zeitpunkte), dt_hours=0.25)
    with pytest.raises(PVPotenzialFehler, match="Muster"):
        jahresmodell(q15, {date(2025, 6, 1): 5.0})


def test_tagessummen_trennen_q15_und_tageswerte() -> None:
    messwerte = [
        {"timestamp": datetime(2025, 5, 1, 10, 0), "kwh": 1.0, "interval_minutes": 15},
        {"timestamp": datetime(2025, 5, 1, 10, 15), "kwh": 2.0, "interval_minutes": 15},
        {"timestamp": datetime(2025, 4, 30, 22, 0), "kwh": 9.0, "interval_minutes": 1440},
    ]
    summen = tagessummen_aus_messwerten(messwerte)
    assert summen[date(2025, 5, 1)] == pytest.approx(3.0 + 9.0)


# ---------------------------------------------------------------------------
# Ökonomie
# ---------------------------------------------------------------------------


def test_bezugspreis_rechenweg_ist_nachrechenbar() -> None:
    p = bezugspreis(
        arbeitspreis_netto_ct_kwh=12.9, netz_arbeitsabhaengig_netto_ct_kwh=10.396
    )
    # (12,9 + 10,396) ct netto x 1,20 = 27,9552 ct = 0,279552 EUR
    assert p.brutto_eur_kwh == pytest.approx(0.279552, abs=1e-9)
    assert any("× 1.20 USt" in z for z in p.rechenweg)


def test_bezugspreis_lehnt_negative_bestandteile_ab() -> None:
    with pytest.raises(PVPotenzialFehler):
        bezugspreis(arbeitspreis_netto_ct_kwh=-1.0, netz_arbeitsabhaengig_netto_ct_kwh=10.0)


def test_nutzen_trennt_vermiedenen_bezug_von_einspeiseerloes(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    b = pv_bilanz(reihe, profil, kwp=10.0, speicher_kwh=0.0)
    p = bezugspreis(arbeitspreis_netto_ct_kwh=12.9, netz_arbeitsabhaengig_netto_ct_kwh=10.396)
    n = nutzen(b, p, einspeise_netto_ct_kwh=5.0)
    assert n.vermiedener_bezug_eur == pytest.approx(
        b.eigenverbrauch_kwh * p.brutto_eur_kwh, abs=0.01
    )
    assert n.einspeiseerloes_eur == pytest.approx(
        b.einspeisung_kwh * 0.05 * 1.2, abs=0.01
    )
    assert n.gesamt_eur == pytest.approx(
        n.vermiedener_bezug_eur + n.einspeiseerloes_eur, abs=0.01
    )
    # Eine vermiedene kWh ist mehr wert als eine eingespeiste — sonst stimmt die
    # ganze Eigenverbrauchs-Logik nicht.
    assert p.brutto_eur_kwh > 0.05 * 1.2


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


def _messwerte_aus_reihe(r: Lastreihe) -> list[dict]:
    return [
        {"timestamp": ts.isoformat(), "kwh": k, "interval_minutes": round(r.dt_hours * 60)}
        for ts, k in zip(r.zeitpunkte, r.kwh, strict=True)
    ]


def _profil_liste(p: PVStundenprofil) -> list[dict]:
    return [
        {"monat": m, "tag": t, "stunde": h, "kwh_pro_kwp": v}
        for (m, t, h), v in sorted(p.werte.items())
    ]


def test_beide_capabilities_sind_registriert() -> None:
    namen = set(default_registry().names)
    assert {"pv_potenzial", "speicher_dimensionierung"} <= namen


def test_pv_potenzial_rechnet_kein_geld_auf_ein_teiljahr(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    res = PVPotenzialCapability().run(
        consumption_data=_messwerte_aus_reihe(reihe),
        pv_profil=_profil_liste(profil),
        kwp_varianten=[5.0, 10.0],
        arbeitspreis_netto_ct_kwh=12.9,
        netz_arbeitsabhaengig_netto_ct_kwh=10.396,
        einspeise_szenarien_ct_kwh=[3.0, 5.0, 8.0],
        jahresmodell=False,
    )
    assert res.ok, res.error
    for variante in res.data["gemessen"]["varianten"]:
        assert variante["wirtschaftlichkeit"]["gerechnet"] is False
        assert "saisonal" in variante["wirtschaftlichkeit"]["grund"]


def test_pv_potenzial_liefert_jahresmodell_mit_warnung(profil: PVStundenprofil) -> None:
    q15 = _q15_reihe(tage=60, start=date(2025, 5, 1))
    messwerte = _messwerte_aus_reihe(q15)
    # Tagessummen für ein volles Jahr davor (wie sie EDA als Backfill liefert).
    letzter = date(2025, 6, 29)
    messwerte += [
        {
            "timestamp": (
                datetime(letzter.year, letzter.month, letzter.day) - timedelta(days=d + 1)
            ).isoformat(),
            "kwh": 9.0,
            "interval_minutes": 1440,
        }
        for d in range(365)
    ]
    res = PVPotenzialCapability().run(
        consumption_data=messwerte,
        pv_profil=_profil_liste(profil),
        kwp_varianten=[10.0],
        arbeitspreis_netto_ct_kwh=12.9,
        netz_arbeitsabhaengig_netto_ct_kwh=10.396,
        einspeise_szenarien_ct_kwh=[5.0],
        investition_eur_pro_kwp={"10": 1400},
        nutzungsdauer_jahre=20,
        diskontrate=0.04,
    )
    assert res.ok, res.error
    jahr = res.data["jahr_modelliert"]
    assert jahr["ist_modell"] is True
    assert "MODELL" in jahr["hinweis"]
    wirt = jahr["varianten"][0]["wirtschaftlichkeit"]
    assert wirt["gerechnet"] is True
    assert wirt["szenarien"][0]["amortisation_jahre"] > 0
    assert res.data["annahmen"]["einspeisung_ist_annahme"] is True


def test_jahresmodell_warnt_wenn_nur_winter_gemessen_wurde(
    profil: PVStundenprofil,
) -> None:
    """Der gemessene Modellfehler (bis +15 %) muss beim Ergebnis stehen, nicht im Test."""
    q15 = _q15_reihe(tage=45, start=date(2025, 12, 1))
    messwerte = _messwerte_aus_reihe(q15)
    messwerte += [
        {
            "timestamp": (datetime(2026, 1, 14) - timedelta(days=d + 1)).isoformat(),
            "kwh": 9.0,
            "interval_minutes": 1440,
        }
        for d in range(365)
    ]
    res = PVPotenzialCapability().run(
        consumption_data=messwerte,
        pv_profil=_profil_liste(profil),
        kwp_varianten=[10.0],
        arbeitspreis_netto_ct_kwh=12.9,
        netz_arbeitsabhaengig_netto_ct_kwh=10.396,
        einspeise_szenarien_ct_kwh=[5.0],
    )
    assert res.ok, res.error
    hinweis = res.data["jahr_modelliert"]["hinweis"]
    assert "ACHTUNG" in hinweis
    assert "15 %" in hinweis


def test_pv_potenzial_ohne_q15_wird_abgelehnt(profil: PVStundenprofil) -> None:
    messwerte = [
        {
            "timestamp": (datetime(2025, 1, 1) + timedelta(days=d)).isoformat(),
            "kwh": 9.0,
            "interval_minutes": 1440,
        }
        for d in range(400)
    ]
    res = PVPotenzialCapability().run(
        consumption_data=messwerte,
        pv_profil=_profil_liste(profil),
        kwp_varianten=[10.0],
        arbeitspreis_netto_ct_kwh=12.9,
        netz_arbeitsabhaengig_netto_ct_kwh=10.396,
        einspeise_szenarien_ct_kwh=[5.0],
    )
    assert not res.ok
    assert "Viertelstundenwerte" in (res.error or "")


def test_pv_potenzial_erfindet_keine_preise(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    res = PVPotenzialCapability().run(
        consumption_data=_messwerte_aus_reihe(reihe),
        pv_profil=_profil_liste(profil),
        kwp_varianten=[10.0],
        einspeise_szenarien_ct_kwh=[5.0],
    )
    assert not res.ok
    assert "erforderlich" in (res.error or "")


def test_speicher_dimensionierung_meldet_fallenden_grenznutzen(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    res = SpeicherDimensionierungCapability().run(
        consumption_data=_messwerte_aus_reihe(reihe),
        pv_profil=_profil_liste(profil),
        kwp=10.0,
        groessen_kwh=[5.0, 10.0, 15.0, 20.0],
        arbeitspreis_netto_ct_kwh=12.9,
        netz_arbeitsabhaengig_netto_ct_kwh=10.396,
        einspeise_netto_ct_kwh=5.0,
        speicher_kosten_eur_pro_kwh=600.0,
        nutzungsdauer_jahre=15,
        diskontrate=0.04,
        jahresmodell=False,
    )
    assert res.ok, res.error
    stufen = res.data["grenznutzen"]
    werte = [s["zusatznutzen_eur_je_kwh_jahr"] for s in stufen]
    assert werte == sorted(werte, reverse=True), werte
    assert res.data["annahmen"]["alterung_beruecksichtigt"] is False
    assert "Alterung" in res.data["hinweis"]


def test_speicher_dimensionierung_sagt_auch_nein(
    reihe: Lastreihe, profil: PVStundenprofil
) -> None:
    """Ein absurd teurer Speicher muss ein ehrliches Nein bekommen, keine Zahl."""
    res = SpeicherDimensionierungCapability().run(
        consumption_data=_messwerte_aus_reihe(reihe),
        pv_profil=_profil_liste(profil),
        kwp=10.0,
        groessen_kwh=[10.0],
        arbeitspreis_netto_ct_kwh=12.9,
        netz_arbeitsabhaengig_netto_ct_kwh=10.396,
        einspeise_netto_ct_kwh=5.0,
        speicher_kosten_eur_pro_kwh=50_000.0,
        nutzungsdauer_jahre=15,
        diskontrate=0.04,
        jahresmodell=False,
    )
    assert res.ok, res.error
    assert res.data["lohnt_sich"] is False
    assert "verdient seine Anschaffung" in res.data["befund"]


# ---------------------------------------------------------------------------
# Regressionen der reparierten Bestandsrechnungen
# ---------------------------------------------------------------------------


def test_eigenverbrauchsquote_zaehlt_restspeicher_nicht_mit() -> None:
    """Vorher meldete diese Konstellation 100 % Eigenverbrauch (Rest-SOC mitgezählt)."""
    prod = [4.0, 0.0]
    cons = [0.0, 1.0]
    res = run_self_consumption(prod, cons, Battery.new(50.0), dt_hours=1.0)
    assert res.grid_feed_in_kwh == pytest.approx(0.0)
    assert res.self_consumption_rate < 0.5
    assert res.self_consumption_rate == pytest.approx(
        (res.self_consumed_direct_kwh + res.battery_discharge_kwh) / res.production_kwh
    )
    assert res.battery_soc_residual_kwh > 0.0


def test_vollzyklen_bedeuten_in_beiden_dispatchern_dasselbe() -> None:
    prod = [4.0, 0.0, 4.0, 0.0]
    cons = [0.0, 2.0, 0.0, 2.0]
    a = run_self_consumption(prod, cons, Battery.new(10.0), dt_hours=1.0)
    b = simulate_battery(
        [p - c for p, c in zip(prod, cons, strict=True)],
        Battery.new(10.0),
        MarketTerms(),
        strategy="self_consumption",
        dt_hours=1.0,
    )
    # Gleiche Größe, gleiche Zahl — die Anzeige rundet unterschiedlich fein
    # (2 vs. 1 Nachkommastelle), deshalb die Toleranz auf der Zyklenzahl.
    assert a.battery_charge_kwh == pytest.approx(b.battery_charge_kwh, rel=1e-9)
    assert a.cycles == pytest.approx(b.cycles, abs=0.05)
    assert a.battery_charge_kwh / a.capacity_kwh == pytest.approx(
        b.battery_charge_kwh / b.capacity_kwh, rel=1e-9
    )


def test_peak_shaving_ohne_pv_meldet_statt_still_null_zu_liefern() -> None:
    """Produkt-Learning L13: der Fall muss sich melden, nicht 0 EUR zurückgeben."""
    last = [1.0] * 40 + [6.0] * 4 + [1.0] * 52
    monate = [1] * len(last)
    ohne = run_peak_shaving(
        last, monate, Battery.new(20.0), peak_threshold_kw=8.0, dt_hours=0.25
    )
    assert ohne.kein_ladefenster is True
    assert ohne.hinweis is not None and "Netzladung" in ohne.hinweis
    assert ohne.battery_charge_kwh == 0.0

    mit = run_peak_shaving(
        last, monate, Battery.new(20.0), peak_threshold_kw=8.0, dt_hours=0.25,
        grid_charge_threshold_kw=5.0,
    )
    assert mit.kein_ladefenster is False
    assert mit.battery_charge_kwh > 0.0
    assert mit.grid_charge_kwh > 0.0
    assert mit.achieved_peak_kw < ohne.achieved_peak_kw
    # Netzladestrom kostet Arbeit — die Energieersparnis darf dadurch negativ werden.
    assert mit.energy_savings_eur < 0.0
    assert mit.demand_savings_eur > 0.0


def test_netzladung_erzeugt_keine_neue_spitze() -> None:
    last = [1.0] * 96
    monate = [1] * 96
    res = run_peak_shaving(
        last, monate, Battery.new(20.0), peak_threshold_kw=8.0, dt_hours=0.25,
        grid_charge_threshold_kw=5.0,
    )
    # Grundlast 4 kW + Laden bis zur 5-kW-Schwelle -> Spitze darf 5 kW nicht überschreiten.
    assert res.achieved_peak_kw <= 5.0 + 1e-6
