# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Netz-Capabilities (Open-Data-Netzkosten + Abgaben, offline)."""

from __future__ import annotations

import pytest

from energietools.capabilities.netz.capability import (
    GesamtkostenCapability,
    NetzkostenCapability,
    VerfuegbarkeitCapability,
)
from energietools.capabilities.netz.resolve import (
    akzeptierte_vnb_namen,
    netzkosten_brutto_eur,
    resolve_netzbetreiber,
    vnb_name_akzeptiert,
)
from energietools.capabilities.registry import default_registry


def test_netzkosten_wien_1010() -> None:
    """Wien (Wiener Netze), 3500 kWh → brutto ≈ 440.42 EUR/Jahr."""
    brutto, name = netzkosten_brutto_eur("1010", 3500)
    assert name == "Wiener Netze GmbH"
    assert brutto == pytest.approx(440.42, abs=0.5)


def test_netzkosten_steiermark_8530() -> None:
    """Deutschlandsberg (Energienetze Steiermark, keine Graz-Enklave) → ≈ 502.42."""
    brutto, name = netzkosten_brutto_eur("8530", 3500)
    assert name == "Energienetze Steiermark GmbH"
    assert brutto == pytest.approx(502.42, abs=0.5)


def test_netzkosten_capability_wien() -> None:
    """Capability-Envelope für Wien liefert VNB + Brutto-Betrag + Rechenweg."""
    result = NetzkostenCapability().run(plz="1010", verbrauch_kwh=3500)
    assert result.ok is True
    assert result.data["netzbetreiber"] == "Wiener Netze GmbH"
    assert result.data["netzkosten_eur_jahr_brutto"] == pytest.approx(440.42, abs=0.5)
    assert result.data["rechenweg"]["komponenten"]["brutto_eur_jahr"] == pytest.approx(
        440.42, abs=0.5
    )


def test_unbekannte_plz_fail_open() -> None:
    """Unbekannte PLZ → fail-open: kein VNB, Netzkosten 0."""
    assert resolve_netzbetreiber("99999") is None
    brutto, name = netzkosten_brutto_eur("99999", 3500)
    assert brutto == 0.0
    assert name == ""

    result = NetzkostenCapability().run(plz="99999", verbrauch_kwh=3500)
    assert result.ok is True
    assert result.data["netzbetreiber"] is None
    assert result.data["netzkosten_eur_jahr_brutto"] == 0.0


def test_gesamtkosten_plausibel() -> None:
    """Gesamtkosten Wien (20 ct/kWh netto, 10 EUR/Monat netto Grund) > 0 und plausibel."""
    result = GesamtkostenCapability().run(
        plz="1010",
        verbrauch_kwh=3500,
        energiepreis_netto_ct_kwh=20.0,
        grundgebuehr_netto_eur_monat=10.0,
    )
    assert result.ok is True
    gesamt = result.data["gesamtkosten_eur_jahr_brutto"]
    # Energie netto 700 + Grund 120 = 820, +7% GAB nur auf Energie, ×1.20 + Netz ~440.
    assert gesamt > 0
    assert 1300 < gesamt < 1600


def test_verfuegbarkeit() -> None:
    """'AT' immer verfügbar; Bundesland-Match aus PLZ; unbekannte PLZ fail-open True."""
    assert VerfuegbarkeitCapability().run(service_area="AT", plz="1010").data["verfuegbar"] is True
    wien = VerfuegbarkeitCapability().run(service_area="Wien", plz="1010").data
    assert wien["verfuegbar"] is True
    assert wien["bundeslaender"] == ["Wien"]
    assert (
        VerfuegbarkeitCapability().run(service_area="Tirol", plz="1010").data["verfuegbar"] is False
    )
    assert (
        VerfuegbarkeitCapability().run(service_area="Tirol", plz="99999").data["verfuegbar"] is True
    )


def test_stadt_netzbereiche_loesen_inklusion_first() -> None:
    """Single-Gemeinde-Stadt-PLZ lösen via Inklusion auf ihren eigenen VNB auf."""
    assert resolve_netzbetreiber("8020").key == "stromnetz_graz"  # Graz (eine Gemeinde)
    assert resolve_netzbetreiber("4030").key == "linz_netz"  # Linz (eine Gemeinde)


def test_geteilte_plz_fail_open_none() -> None:
    """Geteilte PLZ (mehrere Gemeinden über mehrere VNB) → fail-open None (Schema v2)."""
    # 6020 = Innsbruck (IKB) + Mutters/Natters/... (TINETZ); 8605 = Kapfenberg + St. Lorenzen.
    assert resolve_netzbetreiber("6020") is None
    assert resolve_netzbetreiber("8605") is None
    assert netzkosten_brutto_eur("8605", 3500) == (0.0, "")


def test_kleinwalsertal_evk_hoechster_tarif() -> None:
    """Kleinwalsertal (Mittelberg, 6991) → EVK, höchster NE7-Tarif Österreichs."""
    brutto, name = netzkosten_brutto_eur("6991", 3500)
    assert resolve_netzbetreiber("6991").key == "evk"
    assert name.startswith("Energieversorgung Kleinwalsertal")
    # AP 17,73 ist mit Abstand der höchste → deutlich teurer als jeder Landes-VNB.
    assert brutto > 800


def test_attribution_feldkirch_realer_name_vorarlberg_tarif() -> None:
    """Feldkirch (6800) → realer Name 'Stadtwerke Feldkirch', Tarif = Vorarlberg.

    (8605 Kapfenberg ist im Voll-Schema eine geteilte PLZ; 6800 Feldkirch ist die
    verbleibende Single-Gemeinde-Attributions-PLZ.)
    """
    brutto, name = netzkosten_brutto_eur("6800", 3500)
    assert name == "Stadtwerke Feldkirch"  # realer Betreiber, nicht der Landes-VNB
    # Kosten exakt wie ein Vorarlberg-Landes-Anschluss (Bürs 6706).
    landes_brutto, _ = netzkosten_brutto_eur("6706", 3500)
    assert brutto == pytest.approx(landes_brutto)


def test_aequivalenz_beide_namen_akzeptiert() -> None:
    """An einer Feldkirch-PLZ gelten realer Name UND Netzbereich-Name."""
    assert akzeptierte_vnb_namen("6800") == {
        "Stadtwerke Feldkirch",
        "Vorarlberger Energienetze GmbH",
    }
    assert vnb_name_akzeptiert("6800", "Stadtwerke Feldkirch")
    assert vnb_name_akzeptiert("6800", "Vorarlberger Energienetze")  # ohne GmbH
    assert vnb_name_akzeptiert("6800", "vorarlberger energienetze gmbh")  # tolerant
    assert not vnb_name_akzeptiert("6800", "Wiener Netze")  # fremder VNB


def test_attribution_capability_rechenweg_korrekt() -> None:
    """Capability zeigt realen Namen + korrekten (referenzierten) Rechenweg."""
    result = NetzkostenCapability().run(plz="6800", verbrauch_kwh=3500)
    assert result.ok is True
    assert result.data["netzbetreiber"] == "Stadtwerke Feldkirch"
    assert result.data["netzbereich"] == "Vorarlberger Energienetze GmbH"  # Tarif-Herkunft
    # Rechenweg-AP ist der Vorarlberg-Tarif (4,96), NICHT 0 (Attributions-VNB).
    komp = result.data["rechenweg"]["komponenten"]
    assert komp["netznutzung_arbeitspreis_ct_kwh"] == pytest.approx(4.96, abs=1e-3)
    assert result.data["netzkosten_eur_jahr_brutto"] == pytest.approx(342.69, abs=0.5)


def test_default_registry_enthaelt_netz_capabilities() -> None:
    """Die Netz-Capabilities sind registriert; die Vergleichs-Capability ist entfernt (S4)."""
    namen = set(default_registry().names)
    assert {"netzkosten", "gesamtkosten", "netz_verfuegbar"} <= namen
    assert "tarifvergleich_inkl_netz" not in namen


# --- Geteilte PLZ aufloesbar machen (ergaenzt 2026-07-30) -------------------
#
# resolve_netzbetreiber() bleibt bei einer geteilten PLZ bewusst bei None.
# Die beiden Funktionen hier machen die Mehrdeutigkeit sichtbar und aufloesbar,
# ohne dieses Verhalten anzutasten.


def test_kandidaten_bei_geteilter_plz() -> None:
    """4020 deckt Linz und Leonding ab, also zwei Netzbereiche."""
    from energietools.capabilities.netz import netzbetreiber_kandidaten

    kandidaten = netzbetreiber_kandidaten("4020")
    keys = {nb.key for nb, _ in kandidaten}
    assert keys == {"linz_netz", "netz_ooe"}
    gemeinden = {nb.key: gem for nb, gem in kandidaten}
    assert gemeinden["linz_netz"] == ["Linz"]
    assert gemeinden["netz_ooe"] == ["Leonding"]


def test_kandidaten_bei_eindeutiger_plz() -> None:
    """Eindeutige PLZ liefert genau einen Kandidaten, denselben wie der Resolver."""
    from energietools.capabilities.netz import (
        netzbetreiber_kandidaten,
        resolve_netzbetreiber,
    )

    kandidaten = netzbetreiber_kandidaten("1010")
    assert len(kandidaten) == 1
    assert kandidaten[0][0].key == resolve_netzbetreiber("1010").key == "wiener_netze"


def test_kandidaten_bei_unbekannter_plz() -> None:
    """Unbekannte PLZ → leere Liste, nicht None. Fail-open wie der Resolver."""
    from energietools.capabilities.netz import netzbetreiber_kandidaten

    assert netzbetreiber_kandidaten("99999") == []


def test_gemeinde_loest_geteilte_plz_auf() -> None:
    """Mit der Gemeinde ist der Netzbereich eindeutig."""
    from energietools.capabilities.netz import netzbetreiber_fuer_gemeinde

    assert netzbetreiber_fuer_gemeinde("4020", "Linz").key == "linz_netz"
    assert netzbetreiber_fuer_gemeinde("4020", "Leonding").key == "netz_ooe"
    assert netzbetreiber_fuer_gemeinde("9020", "Klagenfurt am Wörthersee").key == (
        "stadtwerke_klagenfurt"
    )


def test_gemeinde_wird_gegen_die_plz_geprueft() -> None:
    """Eine Gemeinde, die nicht zur PLZ gehoert, liefert nichts.

    Sonst koennte eine geratene Gemeinde eine falsche Netzrechnung erzeugen, und
    das ist genau der Fehler, den das fail-open verhindern soll.
    """
    from energietools.capabilities.netz import netzbetreiber_fuer_gemeinde

    assert netzbetreiber_fuer_gemeinde("4020", "Wien") is None
    assert netzbetreiber_fuer_gemeinde("99999", "Linz") is None


def test_gemeinde_unabhaengig_von_gross_klein() -> None:
    """Nutzereingaben kommen selten in der Schreibweise des Registers."""
    from energietools.capabilities.netz import netzbetreiber_fuer_gemeinde

    assert netzbetreiber_fuer_gemeinde("4020", "linz").key == "linz_netz"
    assert netzbetreiber_fuer_gemeinde("4020", "  LEONDING ").key == "netz_ooe"


def test_resolver_verhalten_unveraendert() -> None:
    """Die Ergaenzungen aendern nichts am bestehenden Resolver."""
    from energietools.capabilities.netz import resolve_netzbetreiber

    assert resolve_netzbetreiber("4020") is None
    assert resolve_netzbetreiber("6020") is None
    assert resolve_netzbetreiber("1010").key == "wiener_netze"
    assert resolve_netzbetreiber("4030").key == "linz_netz"


# --- Geteilte PLZ: netzkosten aufloesbar machen (ergaenzt 2026-08-03) -------
#
# Bis hierher war netzbetreiber_kandidaten/-fuer_gemeinde gebaut, aber von keiner
# Capability genutzt: `netzkosten` loeste ausschliesslich ueber die PLZ auf und
# lieferte bei einer geteilten PLZ leere `komponenten`. Aufrufer, die daraus einen
# arbeitsabhaengigen Anteil brauchen (pv_potenzial, speicher_dimensionierung im
# Gateway), brachen deshalb an 75 der 2233 AT-PLZ komplett ab — darunter 1140,
# 1190, 1210 und 1230. Die beiden Wege hier loesen das, ohne den PLZ-Pfad oder das
# fail-open anzutasten.


def _netzkosten(**kwargs: object) -> dict:
    from energietools.capabilities.netz import NetzkostenCapability

    res = NetzkostenCapability().run(**kwargs)
    assert res.ok, res.error
    return res.data


def test_netzkosten_geteilte_plz_bleibt_fail_open() -> None:
    """Ohne Zusatzangabe bleibt eine geteilte PLZ fail-open — unveraendert."""
    data = _netzkosten(plz="1140", verbrauch_kwh=3500.0)
    assert data["netzbetreiber"] is None
    assert data["rechenweg"]["komponenten"] == {}


def test_netzkosten_mit_nb_key_loest_geteilte_plz_auf() -> None:
    """Der vorgeloeste VNB-Key (Gateway: aus der Zaehlpunkt-VKZ) gewinnt.

    Das ist der deterministische Weg: wer den Zaehlpunkt hat, muss nicht raten
    und nicht rueckfragen.
    """
    data = _netzkosten(plz="1140", verbrauch_kwh=3500.0, nb_key="wiener_netze")
    assert data["netzbetreiber"] == "Wiener Netze GmbH"
    komponenten = data["rechenweg"]["komponenten"]
    assert komponenten["arbeitspreis_summe_ct_kwh"] > 0

    # Gegenprobe: der ANDERE Betreiber derselben PLZ rechnet auch, mit anderem Wert.
    noe = _netzkosten(plz="1140", verbrauch_kwh=3500.0, nb_key="netz_noe")
    assert noe["netzbetreiber"] == "Netz Niederösterreich GmbH"
    assert noe["netzkosten_eur_jahr_brutto"] != data["netzkosten_eur_jahr_brutto"]


def test_netzkosten_mit_gemeinde_loest_geteilte_plz_auf() -> None:
    """Der Rueckfrage-Weg: der Nutzer nennt seine Gemeinde."""
    data = _netzkosten(plz="4020", verbrauch_kwh=3500.0, gemeinde="Linz")
    assert data["netzbetreiber"] == "LINZ NETZ GmbH"
    assert data["rechenweg"]["komponenten"]["arbeitspreis_summe_ct_kwh"] > 0

    leonding = _netzkosten(plz="4020", verbrauch_kwh=3500.0, gemeinde="Leonding")
    assert leonding["netzbetreiber"] == "Netz Oberösterreich GmbH"


def test_netzkosten_unbekannter_nb_key_faellt_auf_die_plz_zurueck() -> None:
    """Ein Key, den es nicht gibt, darf nichts erfinden und nichts kaputtmachen."""
    data = _netzkosten(plz="1010", verbrauch_kwh=3500.0, nb_key="gibt_es_nicht")
    assert data["netzbetreiber"] == "Wiener Netze GmbH"


def test_netzkosten_falsche_gemeinde_bleibt_fail_open() -> None:
    """Eine Gemeinde, die nicht zur PLZ gehoert, darf keine Rechnung erzeugen."""
    data = _netzkosten(plz="1140", verbrauch_kwh=3500.0, gemeinde="Linz")
    assert data["netzbetreiber"] is None
    assert data["rechenweg"]["komponenten"] == {}


def test_netzkosten_geteilte_plz_nennt_die_kandidaten() -> None:
    """Fail-open ohne Hinweis ist eine Sackgasse: der Aufrufer muss fragen koennen."""
    data = _netzkosten(plz="1140", verbrauch_kwh=3500.0)
    kandidaten = data["kandidaten"]
    assert {k["nb_key"] for k in kandidaten} == {"wiener_netze", "netz_noe"}
    nach_key = {k["nb_key"]: k for k in kandidaten}
    assert nach_key["wiener_netze"]["gemeinden"] == ["Wien"]
    assert "Klosterneuburg" in nach_key["netz_noe"]["gemeinden"]


def test_netzkosten_eindeutige_plz_unveraendert() -> None:
    """Der bestehende PLZ-Pfad rechnet exakt wie vorher."""
    data = _netzkosten(plz="1010", verbrauch_kwh=3500.0)
    assert data["netzbetreiber"] == "Wiener Netze GmbH"
    assert data["rechenweg"]["komponenten"]["arbeitspreis_summe_ct_kwh"] == 8.4
    assert data["kandidaten"] == []
