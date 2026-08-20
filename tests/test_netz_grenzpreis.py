# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für den Grenzpreis je kWh (``capabilities/netz/grenzpreis.py``).

Der Grenzpreis beantwortet die Frage, die jede Verbrauchs-Rückmeldung an einen
Haushalt stellt: *was kostet mich eine kWh mehr?* Das ist nicht der
Energiepreis des Lieferanten — Netznutzung, Netzverlust, EAG-Förderbeitrag,
Elektrizitätsabgabe, die kommunale Gebrauchsabgabe und die Umsatzsteuer hängen
alle daran.

Die Tests halten vor allem zwei Eigenschaften fest: dass jeder Summand einzeln
ausgewiesen wird (ohne Rechenweg keine €-Zahl), und dass ein unbekannter
Netzbetreiber ``None`` liefert statt eines erfundenen Werts.
"""

from __future__ import annotations

import pytest

from energietools.capabilities.netz.grenzpreis import (
    UST_SATZ,
    grenzpreis_ct_kwh,
)

# Wiener Netze, Stand 2026: 6,98 Netznutzung + 0,70 Netzverlust
# + 0,583 EAG AP + 0,037 EAG Verlust + 0,10 Elektrizitätsabgabe.
WIEN_NETZ_NETTO = 8.40
# Wiener Gebrauchsabgabe: 7 % auf Energie und Netz, ohne Abgaben.
WIEN_GA_SATZ = 0.07


def test_summanden_werden_einzeln_ausgewiesen():
    """Ohne Rechenweg keine Euro-Zahl — das ist die Hausregel, nicht Kosmetik."""
    p = grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=12.95, vnb_key="wiener_netze")
    assert p is not None
    assert p.energie_ct_kwh == pytest.approx(12.95)
    assert p.netznutzung_ct_kwh == pytest.approx(6.98)
    assert p.netzverlust_ct_kwh == pytest.approx(0.70)
    assert p.eag_ct_kwh == pytest.approx(0.62, abs=0.001)
    assert p.elektrizitaetsabgabe_ct_kwh == pytest.approx(0.10)
    assert p.gebrauchsabgabe_ct_kwh > 0
    assert p.netzbetreiber == "Wiener Netze GmbH"


def test_netto_ist_die_summe_der_summanden():
    p = grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=12.95, vnb_key="wiener_netze")
    summe = (
        p.energie_ct_kwh
        + p.netznutzung_ct_kwh
        + p.netzverlust_ct_kwh
        + p.eag_ct_kwh
        + p.elektrizitaetsabgabe_ct_kwh
        + p.gebrauchsabgabe_ct_kwh
    )
    assert p.netto_ct_kwh == pytest.approx(summe, abs=0.005)


def test_brutto_ist_netto_mal_umsatzsteuer():
    p = grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=12.95, vnb_key="wiener_netze")
    assert p.brutto_ct_kwh == pytest.approx(p.netto_ct_kwh * UST_SATZ, abs=0.005)


def test_wiener_gebrauchsabgabe_auf_energie_und_netz_ohne_abgaben():
    """Sieben Prozent, aber nicht auf alles: EAG-Beitrag und
    Elektrizitätsabgabe gehören laut Wiener Gebrauchsabgabegesetz nicht in die
    Bemessungsgrundlage."""
    energie = 12.95
    p = grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=energie, vnb_key="wiener_netze")
    erwartet = (energie + 6.98 + 0.70) * WIEN_GA_SATZ
    assert p.gebrauchsabgabe_ct_kwh == pytest.approx(erwartet, abs=0.005)


def test_hoeherer_energiepreis_hebt_auch_die_gebrauchsabgabe():
    billig = grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=8.0, vnb_key="wiener_netze")
    teuer = grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=16.4, vnb_key="wiener_netze")
    assert teuer.gebrauchsabgabe_ct_kwh > billig.gebrauchsabgabe_ct_kwh
    assert teuer.brutto_ct_kwh > billig.brutto_ct_kwh


def test_netzbetreiber_ohne_gebrauchsabgabe():
    """Die meisten Netzbereiche verrechnen keine separate Gebrauchsabgabe."""
    p = grenzpreis_ct_kwh(
        energiepreis_netto_ct_kwh=12.0, vnb_key="energienetze_steiermark"
    )
    assert p is not None
    assert p.gebrauchsabgabe_ct_kwh == pytest.approx(0.0)


# --- Fail-open ----------------------------------------------------------------


def test_unbekannter_netzbetreiber_liefert_nichts():
    """Kein erfundener Wert — lieber gar keine Euro-Zahl in der Kundenmail."""
    assert grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=12.0, vnb_key="gibt_es_nicht") is None


def test_ohne_netzbetreiber_liefert_nichts():
    assert grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=12.0, vnb_key="") is None
    assert grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=12.0, vnb_key=None) is None


def test_unsinniger_energiepreis_wird_abgelehnt():
    """Ein negativer oder absurd hoher Preis ist ein Eingabefehler, kein Tarif."""
    assert grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=-1.0, vnb_key="wiener_netze") is None
    assert grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=500.0, vnb_key="wiener_netze") is None


def test_energiepreis_null_ist_zulaessig():
    """Ein Volleinspeiser oder ein Gratis-Kontingent hat 0 ct Energiepreis —
    Netz und Abgaben fallen trotzdem an."""
    p = grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=0.0, vnb_key="wiener_netze")
    assert p is not None
    assert p.netto_ct_kwh > WIEN_NETZ_NETTO


# --- Rechenweg als Text -------------------------------------------------------


def test_rechenweg_nennt_jeden_summanden_und_die_quelle():
    p = grenzpreis_ct_kwh(energiepreis_netto_ct_kwh=12.95, vnb_key="wiener_netze")
    text = p.rechenweg()
    for stichwort in ("Energie", "Netznutzung", "Netzverlust", "EAG",
                      "Elektrizitätsabgabe", "Gebrauchsabgabe", "Umsatzsteuer"):
        assert stichwort in text, f"{stichwort} fehlt im Rechenweg"
    assert "12,95" in text
    assert p.quelle


# --- Gebrauchsabgabe hängt an der PLZ, nicht nur am Netzbetreiber -------------


def test_wien_fallback_greift_ueber_die_plz():
    """Ein Wiener Zählpunkt in einem Netzbereich ohne eigene GA-Regel bekommt
    die Wiener Abgabe trotzdem — über das Bundesland. Ohne PLZ fehlen ihm rund
    2 ct/kWh brutto, und zwar lautlos."""
    ohne = grenzpreis_ct_kwh(
        energiepreis_netto_ct_kwh=12.95, vnb_key="netz_noe", plz=""
    )
    mit = grenzpreis_ct_kwh(
        energiepreis_netto_ct_kwh=12.95, vnb_key="netz_noe", plz="1010"
    )
    assert ohne.gebrauchsabgabe_ct_kwh == pytest.approx(0.0)
    assert mit.gebrauchsabgabe_ct_kwh > 1.0


def test_long_tail_gemeinde_ueber_exakte_plz():
    """33 Gemeinden verrechnen die Abgabe außerhalb der VNB-Tabelle."""
    from energietools.capabilities.netz.data import load_abgaben

    longtail = load_abgaben().gebrauchsabgabe_longtail_plz
    assert longtail, "Fixture-Annahme: es gibt Long-Tail-PLZ"
    plz = next(iter(longtail))
    p = grenzpreis_ct_kwh(
        energiepreis_netto_ct_kwh=12.0, vnb_key="tinetz", plz=plz
    )
    assert p is not None


def test_vnb_regel_schlaegt_die_plz():
    """Der aufgelöste Netzbetreiber ist deterministisch und hat Vorrang."""
    p = grenzpreis_ct_kwh(
        energiepreis_netto_ct_kwh=12.95, vnb_key="wiener_netze", plz="1010"
    )
    ohne_plz = grenzpreis_ct_kwh(
        energiepreis_netto_ct_kwh=12.95, vnb_key="wiener_netze"
    )
    assert p.gebrauchsabgabe_ct_kwh == pytest.approx(ohne_plz.gebrauchsabgabe_ct_kwh)


def test_synthetischer_vkz_key_liefert_nichts():
    """40 der 55 bekannten Kennungen haben kein hinterlegtes Preisblatt. Für sie
    gibt gridbert einen Betreiber MIT Namen, aber OHNE Netzkosten zurück — ein
    Preis daraus sähe plausibel aus und wäre um ein Drittel zu niedrig."""
    assert grenzpreis_ct_kwh(
        energiepreis_netto_ct_kwh=12.95, vnb_key="vkz:AT002110", plz="3300"
    ) is None


# --- Kreuzprobe gegen die sanktionierte Kosten-Engine -------------------------


@pytest.mark.parametrize(
    "plz,vnb_key",
    [
        ("1010", "wiener_netze"),
        ("8010", "stromnetz_graz"),
        ("4020", "netz_ooe"),
        ("5020", "salzburg_netz"),
        ("6020", "tinetz"),
        ("9020", "stadtwerke_klagenfurt"),
    ],
)
def test_grenzpreis_entspricht_der_differenz_zweier_jahresrechnungen(plz, vnb_key):
    """Die eigentliche Prüfung: der komponierte Grenzpreis muss exakt dem
    entsprechen, was ``gesamtkosten_szenario`` mehr berechnet, wenn ein
    Haushalt 100 kWh mehr verbraucht. Stimmen die beiden Wege nicht überein,
    ist einer von beiden falsch — und der andere steht in einer Kundenmail.
    """
    import energietools.capabilities  # noqa: F401 - vermeidet den Zirkelimport
    from energietools.cost import gesamtkosten_szenario

    energie_brutto = 20.0
    energie_netto = energie_brutto / UST_SATZ
    basis, delta = 3500.0, 100.0

    def jahreskosten(kwh: float) -> float:
        ergebnis = gesamtkosten_szenario(
            plz=plz,
            verbrauch_kwh=kwh,
            netto_ep_ct=energie_netto,
            netto_gg_eur_monat=0.0,
            nb_key=vnb_key,
        )
        return float(ergebnis["gesamtkosten_eur_jahr_brutto"])

    differenz_ct_kwh = (jahreskosten(basis + delta) - jahreskosten(basis)) / delta * 100
    komponiert = grenzpreis_ct_kwh(
        energiepreis_netto_ct_kwh=energie_netto, vnb_key=vnb_key, plz=plz
    )
    assert komponiert is not None
    assert komponiert.brutto_ct_kwh == pytest.approx(differenz_ct_kwh, abs=0.02)
