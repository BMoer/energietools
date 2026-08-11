# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests der centgenauen Rechnungs-Nachrechnung.

Der Fall, um den es geht (Anforderung best connect/spotty, 06.08.2026): „Jeder
aufgeschlüsselte Detailpunkt durchgerechnet, alle Kostenpunkte summiert und
gegen den Gesamtbetrag gestellt. Weicht es ab, gilt der Kunde als nicht fair
behandelt." Die bisherige Plausibilitätsprüfung hat eine Toleranz von ±15 % —
ein Rechenfehler von 3 % rutscht durch. Genau das prüft
``test_ein_rechenfehler_von_drei_prozent_wird_gefunden``.
"""

from __future__ import annotations

from datetime import date

import pytest

from energietools.capabilities.invoice.facts import InvoiceFacts
from energietools.capabilities.invoice.nachrechnung import (
    BEFUND_ABWEICHUNG,
    BEFUND_STIMMIG,
    BEFUND_UNVOLLSTAENDIG,
    GUENSTIGER,
    NICHT_PRUEFBAR,
    STIMMT,
    ZU_HOCH,
    rechne_nach,
)

_VON = date(2025, 1, 1)
_BIS = date(2025, 12, 31)
_VERBRAUCH = 3500.0
_PREIS_CT = 20.0  # netto
_GG_MONAT = 5.0  # netto

# Energie netto = 3500 × 0,20 € + 12 × 5 € = 700 + 60 = 760,00 €
_ENERGIE = 760.00
_NETZ = 380.00
_ABGABEN = 120.00
# (760 + 380 + 120) × 1,2 = 1.512,00 €
_BRUTTO_STIMMIG = 1512.00


def _facts(**overrides) -> InvoiceFacts:
    daten = {
        "energieart": "strom",
        "lieferant": "Testversorger",
        "zeitraum_von": _VON,
        "zeitraum_bis": _BIS,
        "verbrauch_kwh": _VERBRAUCH,
        "plz": "1100",
        "summe_energieentgelte": {"wert_eur": _ENERGIE, "ist_netto": True},
        "summe_netzentgelte": {"wert_eur": _NETZ, "ist_netto": True},
        "summe_steuern_abgaben": {"wert_eur": _ABGABEN, "ist_netto": True},
        "rechnungsbetrag_brutto_eur": _BRUTTO_STIMMIG,
        "arbeitspreis": {"wert_ct_kwh": _PREIS_CT, "ist_netto": True},
        "grundgebuehr": {"wert_eur": _GG_MONAT, "zeitraum": "monat", "ist_netto": True},
        "quellen_anker": [
            {"feld": "verbrauch_kwh", "zitat": "Verbrauch 3.500 kWh"},
            {"feld": "rechnungsbetrag_brutto_eur", "zitat": "Rechnungsbetrag 1.512,00 EUR"},
        ],
    }
    daten.update(overrides)
    return InvoiceFacts(**daten)


def _position(ergebnis, block: str):
    return next(p for p in ergebnis.positionen if p.block == block)


# --- Härtegrad 1: die Summenprüfung ----------------------------------------


def test_eine_stimmige_rechnung_geht_centgenau_auf():
    ergebnis = rechne_nach(_facts())
    summe = _position(ergebnis, "gesamtsumme")
    assert summe.status == STIMMT
    assert summe.erwartet_eur == pytest.approx(1512.00, abs=0.01)
    assert ergebnis.befund == BEFUND_STIMMIG
    assert ergebnis.zu_viel_verrechnet_eur is None


def test_ein_rechenfehler_von_drei_prozent_wird_gefunden():
    """Der Fall, an dem die alte ±15-%-Plausibilitätsprüfung vorbeisieht."""
    zu_hoch = round(_BRUTTO_STIMMIG * 1.03, 2)  # 1.557,36 €
    ergebnis = rechne_nach(_facts(rechnungsbetrag_brutto_eur=zu_hoch))

    summe = _position(ergebnis, "gesamtsumme")
    assert summe.status == ZU_HOCH
    assert summe.abweichung_eur == pytest.approx(45.36, abs=0.01)
    assert ergebnis.befund == BEFUND_ABWEICHUNG
    assert ergebnis.zu_viel_verrechnet_eur == pytest.approx(45.36, abs=0.01)
    assert "geht nicht auf" in ergebnis.zusammenfassung


def test_ein_fehler_von_fuenf_cent_bleibt_innerhalb_der_rundungstoleranz():
    """Kaufmännische Rundung je Block darf keinen Alarm auslösen."""
    ergebnis = rechne_nach(_facts(rechnungsbetrag_brutto_eur=_BRUTTO_STIMMIG + 0.05))
    assert _position(ergebnis, "gesamtsumme").status == STIMMT


def test_zehn_cent_zu_viel_sind_bereits_ein_befund():
    """Centgenau heißt centgenau — die Grenze liegt bei 5 Cent, nicht bei 15 %."""
    ergebnis = rechne_nach(_facts(rechnungsbetrag_brutto_eur=_BRUTTO_STIMMIG + 0.10))
    assert _position(ergebnis, "gesamtsumme").status == ZU_HOCH


def test_ein_niedrigerer_betrag_ist_kein_fehler_sondern_ein_rabatt():
    ergebnis = rechne_nach(_facts(rechnungsbetrag_brutto_eur=_BRUTTO_STIMMIG - 50.0))
    summe = _position(ergebnis, "gesamtsumme")
    assert summe.status == GUENSTIGER
    assert ergebnis.befund == BEFUND_STIMMIG
    assert ergebnis.zu_viel_verrechnet_eur is None
    assert "Gutschrift oder ein Rabatt" in ergebnis.zusammenfassung


def test_brutto_bloecke_werden_nicht_noch_einmal_versteuert():
    """``ist_netto=False`` heißt: der Wert enthält die USt bereits."""
    ergebnis = rechne_nach(
        _facts(
            summe_energieentgelte={"wert_eur": _ENERGIE * 1.2, "ist_netto": False},
            summe_netzentgelte={"wert_eur": _NETZ * 1.2, "ist_netto": False},
            summe_steuern_abgaben={"wert_eur": _ABGABEN * 1.2, "ist_netto": False},
        )
    )
    assert _position(ergebnis, "gesamtsumme").status == STIMMT


def test_ohne_gesamtbetrag_gibt_es_keine_summenpruefung_und_das_wird_gesagt():
    ergebnis = rechne_nach(_facts(rechnungsbetrag_brutto_eur=None))
    summe = _position(ergebnis, "gesamtsumme")
    assert summe.status == NICHT_PRUEFBAR
    assert "rechnungsbetrag_brutto_eur fehlt" in summe.grund
    assert ergebnis.befund == BEFUND_UNVOLLSTAENDIG


def test_ein_fehlender_block_erzeugt_keinen_fehlalarm():
    """Über unvollständige Blöcke zu summieren würde jede Rechnung anschwärzen."""
    ergebnis = rechne_nach(_facts(summe_netzentgelte=None))
    summe = _position(ergebnis, "gesamtsumme")
    assert summe.status == NICHT_PRUEFBAR
    assert "Netz" in summe.grund
    assert ergebnis.befund == BEFUND_UNVOLLSTAENDIG


# --- Härtegrad 2: die Positionsprüfung --------------------------------------


def test_arbeitspreis_mal_menge_plus_grundgebuehr_ergibt_den_energieblock():
    ergebnis = rechne_nach(_facts())
    energie = _position(ergebnis, "energie")
    assert energie.status == STIMMT
    assert energie.erwartet_eur == pytest.approx(760.00, abs=0.05)
    assert "3500 kWh × 20.0000 ct netto" in energie.rechenweg


def test_ein_zu_hoher_energieblock_faellt_auf():
    ergebnis = rechne_nach(
        _facts(summe_energieentgelte={"wert_eur": _ENERGIE + 40.0, "ist_netto": True})
    )
    energie = _position(ergebnis, "energie")
    assert energie.status == ZU_HOCH
    assert energie.abweichung_eur == pytest.approx(40.00, abs=0.01)
    assert ergebnis.befund == BEFUND_ABWEICHUNG


def test_ein_gerundet_abgetippter_arbeitspreis_loest_keinen_fehlalarm_aus():
    """Unscharf ist die Transkription, nicht die Rechnung.

    Auf der Rechnung steht 19,9967 ct, im Fakten-Feld landet 20,00 ct. Die
    Differenz von 0,0033 ct/kWh ergibt bei 3.500 kWh 0,12 € — das darf kein
    Befund sein.
    """
    echte_summe = 19.9967 * _VERBRAUCH / 100.0 + 60.0
    ergebnis = rechne_nach(
        _facts(summe_energieentgelte={"wert_eur": round(echte_summe, 2), "ist_netto": True})
    )
    assert _position(ergebnis, "energie").status == STIMMT


def test_eine_jahres_grundgebuehr_wird_nicht_zwoelfmal_verrechnet():
    ergebnis = rechne_nach(
        _facts(grundgebuehr={"wert_eur": 60.0, "zeitraum": "jahr", "ist_netto": True})
    )
    assert _position(ergebnis, "energie").erwartet_eur == pytest.approx(760.00, abs=0.05)


def test_ein_halbjahr_bekommt_die_halbe_grundgebuehr():
    ergebnis = rechne_nach(
        _facts(
            zeitraum_bis=date(2025, 6, 30),
            verbrauch_kwh=1750.0,
            summe_energieentgelte={"wert_eur": 380.0, "ist_netto": True},
        )
    )
    energie = _position(ergebnis, "energie")
    # 1750 × 0,20 € = 350 € + ~6 Monate × 5 € = ~380 €
    assert energie.erwartet_eur == pytest.approx(380.0, abs=1.0)
    assert energie.status == STIMMT


def test_ohne_arbeitspreis_ist_die_position_nicht_pruefbar_und_sagt_warum():
    ergebnis = rechne_nach(_facts(arbeitspreis=None))
    energie = _position(ergebnis, "energie")
    assert energie.status == NICHT_PRUEFBAR
    assert "arbeitspreis fehlt" in energie.grund


# --- Härtegrad 3: der Referenzvergleich -------------------------------------


def test_netzentgelt_wird_gegen_den_regulierten_tarif_gestellt():
    ergebnis = rechne_nach(_facts())
    netz = _position(ergebnis, "netzentgelte")
    assert netz.haertegrad == "referenz"
    assert netz.erwartet_eur is not None
    assert "Wiener Netze" in netz.rechenweg
    assert "Wiener Netze" in ergebnis.geprueft_gegen


def test_bei_geteilter_plz_ohne_netzbetreiber_wird_nicht_geraten():
    """1230 umfasst Wien UND Perchtoldsdorf — kein eindeutiger Betreiber."""
    ergebnis = rechne_nach(_facts(plz="1230"))
    netz = _position(ergebnis, "netzentgelte")
    assert netz.status == NICHT_PRUEFBAR
    assert "1230" in netz.grund
    assert ergebnis.geprueft_gegen == "nur die Zahlen der Rechnung"


def test_der_referenzvergleich_taugt_nicht_als_forderungsbetrag():
    """Ein abweichendes Netzentgelt kann legitime Gründe haben (Netzebene,
    Zählertyp). Es darf deshalb NICHT in ``zu_viel_verrechnet_eur`` landen."""
    ergebnis = rechne_nach(
        _facts(summe_netzentgelte={"wert_eur": _NETZ + 300.0, "ist_netto": True},
               rechnungsbetrag_brutto_eur=round((_ENERGIE + _NETZ + 300.0 + _ABGABEN) * 1.2, 2))
    )
    netz = _position(ergebnis, "netzentgelte")
    assert netz.status == ZU_HOCH
    assert ergebnis.zu_viel_verrechnet_eur is None
    assert ergebnis.befund == BEFUND_STIMMIG


def test_jede_position_traegt_einen_rechenweg_oder_einen_grund():
    """No-LLM-Math: keine Zahl ohne nachvollziehbare Herkunft."""
    ergebnis = rechne_nach(_facts())
    for p in ergebnis.positionen:
        assert p.rechenweg or p.grund, f"{p.block} hat weder Rechenweg noch Grund"
