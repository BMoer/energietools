# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Unit-Tests für die EINE Szenario-Kosten-Engine (``energietools.cost``).

Deckt die zwei Fähigkeiten ab, die ``GesamtkostenCapability`` allein NICHT hatte und
die den S5-Cutover blockiert hätten: **Neukundenrabatt** und **Spot/Floater-Backtest**
— plus die separate-Block-Gebrauchsabgabe und die Delegation der Capability.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from energietools.capabilities.netz.capability import GesamtkostenCapability
from energietools.capabilities.netz.models import GebrauchsabgabeRegelDetail
from energietools.cost import (
    effektiver_energiepreis_netto_ct,
    energie_rechenweg,
    gesamtkosten_szenario,
)
from energietools.models import Rechenweg

_FIXTURE = Path(__file__).parent / "fixtures" / "epex_at_frozen.json"
_KWH = 3500.0
_UST = 1.20


def _frozen_epex() -> list[dict]:
    return json.loads(_FIXTURE.read_text("utf-8"))


def _fix(plz: str) -> dict:
    """Fixpreis-Szenario (10 ct/kWh netto, keine Grundgebühr) für die GA-/Block-Tests."""
    return gesamtkosten_szenario(
        plz=plz, verbrauch_kwh=_KWH, netto_ep_ct=10.0, netto_gg_eur_monat=0.0,
    )


# ---------------------------------------------------------------- Fixpreis-Delegation


def test_capability_delegiert_an_szenario() -> None:
    """GesamtkostenCapability == gesamtkosten_szenario (Fixpreis): Delegation konsistent."""
    res = gesamtkosten_szenario(
        plz="1060", verbrauch_kwh=_KWH, netto_ep_ct=10.0, netto_gg_eur_monat=0.0,
        quelle="berechnet",
    )
    cap = GesamtkostenCapability().run(
        plz="1060", verbrauch_kwh=_KWH,
        energiepreis_netto_ct_kwh=10.0, grundgebuehr_netto_eur_monat=0.0,
    ).data
    assert res["gesamtkosten_eur_jahr_brutto"] == cap["gesamtkosten_eur_jahr_brutto"]
    assert res["jahreskosten_energie_brutto_eur"] == cap["rechenweg"]["energie_brutto_eur"]
    assert res["gebrauchsabgabe_eur"] == cap["rechenweg"]["gebrauchsabgabe_eur"]
    assert res["netzkosten_brutto_eur"] == cap["rechenweg"]["netzkosten_brutto_eur"]


def test_rechenweg_ist_separate_block_modell() -> None:
    """Der Rechenweg ist das gb-angeglichene Separate-Block-Modell (kein netto_inkl_gab)."""
    rw = gesamtkosten_szenario(
        plz="1060", verbrauch_kwh=_KWH, netto_ep_ct=10.0, netto_gg_eur_monat=0.0,
    )["rechenweg"]
    assert isinstance(rw, Rechenweg)
    assert not hasattr(rw, "netto_inkl_gab_eur")  # S4: gefoldetes Feld ist weg
    # gesamt = Energie-Brutto-Kette + Netz + GAB-Block (kein Folding).
    res = _fix("1060")
    erwartet = rw.brutto_jahreskosten_eur + res["netzkosten_brutto_eur"] + rw.gebrauchsabgabe_eur
    assert res["gesamtkosten_eur_jahr_brutto"] == pytest.approx(erwartet, abs=0.01)


# ---------------------------------------------------------------- Neukundenrabatt


def test_rabatt_senkt_nur_energie_jahreskosten_nicht_die_ga() -> None:
    """Rabatt zieht nur von den Energie-Jahreskosten ab; die GAB bleibt (Vor-Rabatt-Basis)."""
    base = _fix("1060")
    disc = gesamtkosten_szenario(
        plz="1060", verbrauch_kwh=_KWH, netto_ep_ct=10.0, netto_gg_eur_monat=0.0,
        neukundenrabatt_ct_kwh=2.0, neukundenrabatt_eur=30.0,
    )
    rabatt_brutto = (_KWH * 2.0 / 100.0) * _UST + 30.0  # = 84 + 30 = 114
    assert disc["jahreskosten_energie_brutto_eur"] == pytest.approx(
        base["jahreskosten_energie_brutto_eur"] - rabatt_brutto, abs=0.01,
    )
    # GAB unverändert (auf Vor-Rabatt-Energie bemessen) + Netz unverändert.
    assert disc["gebrauchsabgabe_eur"] == pytest.approx(base["gebrauchsabgabe_eur"], abs=0.01)
    assert disc["netzkosten_brutto_eur"] == base["netzkosten_brutto_eur"]
    # Gesamt fällt exakt um den Rabatt.
    assert disc["gesamtkosten_eur_jahr_brutto"] == pytest.approx(
        base["gesamtkosten_eur_jahr_brutto"] - rabatt_brutto, abs=0.01,
    )


def test_rabatt_clamped_nicht_negativ() -> None:
    """Übergroßer Rabatt → Energie-Jahreskosten 0 (kein negativer Wert)."""
    res = gesamtkosten_szenario(
        plz="8700", verbrauch_kwh=_KWH, netto_ep_ct=10.0, netto_gg_eur_monat=0.0,
        neukundenrabatt_eur=99999.0,
    )
    assert res["jahreskosten_energie_brutto_eur"] == 0.0


# ---------------------------------------------------------------- Spot/Floater


@pytest.mark.parametrize("tariftyp", ["Stundenfloater", "Monatsfloater"])
def test_spot_wird_ueber_epex_bepreist(tariftyp: str) -> None:
    """ep<=0 + Floater + EPEX-Serie → effektiver Preis aus dem Backtest, > 0."""
    epex = _frozen_epex()
    res = gesamtkosten_szenario(
        plz="8700", verbrauch_kwh=_KWH, netto_ep_ct=0.0, netto_gg_eur_monat=0.0,
        tariftyp=tariftyp, spot_aufschlag_ct=1.5, spot_prices=epex,
    )
    assert res is not None
    assert res["effektiver_ep_netto_ct"] > 0
    assert res["jahreskosten_energie_brutto_eur"] > 0
    # Jahreskosten == effektiver Netto-Preis × Verbrauch × USt (ohne Rabatt/Grund).
    erwartet = round(_KWH * res["effektiver_ep_netto_ct"] / 100.0 * _UST, 2)
    assert res["jahreskosten_energie_brutto_eur"] == pytest.approx(erwartet, abs=0.5)


def test_spot_ohne_epex_ist_none() -> None:
    """Floater ohne EPEX-Daten → None (fail-open: Tarif übersprungen, nicht mit 0 bepreist)."""
    assert gesamtkosten_szenario(
        plz="8700", verbrauch_kwh=_KWH, netto_ep_ct=0.0, netto_gg_eur_monat=0.0,
        tariftyp="Stundenfloater", spot_aufschlag_ct=1.5, spot_prices=None,
    ) is None
    assert gesamtkosten_szenario(
        plz="8700", verbrauch_kwh=_KWH, netto_ep_ct=0.0, netto_gg_eur_monat=0.0,
        tariftyp="Stundenfloater", spot_aufschlag_ct=1.5, spot_prices=[],
    ) is None


def test_effektiver_preis_fixpreis_direkt() -> None:
    """Fixpreis (ep>0) → unverändert; degenerierter 0-Fix bleibt 0 (kein Spot)."""
    assert effektiver_energiepreis_netto_ct(
        netto_ep_ct=12.3, tariftyp="Fixpreis", spot_aufschlag_ct=0.0,
        verbrauch_kwh=_KWH, spot_prices=None,
    ) == 12.3
    assert effektiver_energiepreis_netto_ct(
        netto_ep_ct=0.0, tariftyp="Fixpreis", spot_aufschlag_ct=0.0,
        verbrauch_kwh=_KWH, spot_prices=None,
    ) == 0.0


# ---------------------------------------------------------------- Gebrauchsabgabe-Block


def test_ga_prozent_wien_eigener_block() -> None:
    """Wien: prozent-GA als eigener Brutto-Block, Anzeige-Satz 0.07."""
    res = _fix("1060")
    assert res["gebrauchsabgabe_rate"] == pytest.approx(0.07)
    assert res["gebrauchsabgabe_eur"] == pytest.approx(56.52, abs=0.3)


def test_ga_ctkwh_anzeigesatz_null_betrag_positiv() -> None:
    """ct/kWh-GA-Regel → Anzeige-Satz 0 (kein Prozent), aber echter Euro-Block > 0."""
    regel = GebrauchsabgabeRegelDetail(typ="ct_kwh", satz=1.637, basis="verbrauch")
    rw = energie_rechenweg(
        verbrauch_kwh=_KWH, netto_ep_ct=10.0, netto_gg_eur_monat=0.0, gab_regel=regel,
    )
    assert rw.gebrauchsabgabe_rate == 0.0  # ct/kWh hat keinen Prozent-Anzeigesatz
    assert rw.gebrauchsabgabe_eur == pytest.approx(1.637 * _KWH / 100.0 * _UST, abs=0.01)


def test_ga_leoben_kein_block() -> None:
    """Leoben: keine verifizierte GA-Regel → 0-Block (keine erfundene GA)."""
    res = _fix("8700")
    assert res["gebrauchsabgabe_eur"] == 0.0


# ---------------------------------------------------------------- nb_key-Override (VKZ-Brücke)


def test_nb_key_override_treibt_netz_unabhaengig_von_plz() -> None:
    """Vorgelöster nb_key (VKZ-Brücke) bestimmt die Netzkosten — auch bei unbekannter PLZ."""
    from energietools.capabilities.netz.data import load_alle_vnb
    from energietools.capabilities.netz.resolve import entry_fuer_key, netzkosten_brutto_fuer

    # Irgendein VNB mit eigenem Tarif (Netzkosten > 0) — dynamisch, datenrobust.
    key = next(nb.key for nb in load_alle_vnb() if netzkosten_brutto_fuer(nb, _KWH)[0] > 0)
    erwartet_netz, name = netzkosten_brutto_fuer(entry_fuer_key(key), _KWH)

    # PLZ "0000" würde plz-aufgelöst 0 Netzkosten geben; der nb_key erzwingt den VNB.
    res = gesamtkosten_szenario(
        plz="0000", verbrauch_kwh=_KWH, netto_ep_ct=10.0, netto_gg_eur_monat=0.0, nb_key=key,
    )
    assert res["netzkosten_brutto_eur"] == erwartet_netz > 0
    assert res["netzbetreiber"] == name
