# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die basisgenaue Gebrauchsabgabe (S1: typ/satz/basis-Compute in netz).

Prüft das neue, aus gridbert portierte GA-Modell: ``GebrauchsabgabeRegelDetail``
+ ``betrag_netto_eur`` (basis energie | netz | energie_und_netz | verbrauch),
den Resolver ``gebrauchsabgabe_regel(plz, nb_key)`` und den Netz-Netto-Helfer
``netznutzung_netto_ohne_abgaben_fuer``. Golden-Werte gegen
``gridbert/netz/abgaben.py`` (Referenz der basisgenauen Berechnung).

S1 ist ADDITIV: die ``GesamtkostenCapability`` rechnet noch energie-only (Upgrade
auf basisgenau ist S4). Diese Tests prüfen daher die neuen Funktionen direkt.
"""

from __future__ import annotations

import pytest

from energietools.capabilities.netz.data import load_abgaben
from energietools.capabilities.netz.models import GebrauchsabgabeRegelDetail
from energietools.capabilities.netz.resolve import (
    gebrauchsabgabe_regel,
    netznutzung_netto_ohne_abgaben_fuer,
    resolve_netzbetreiber,
    tarif_fuer,
)


def test_loader_counts() -> None:
    """abgaben.json trägt die basisgenauen Sektionen (4 VNB + 33 Long-Tail-PLZ)."""
    ab = load_abgaben()
    assert len(ab.gebrauchsabgabe_je_vnb) == 4
    assert len(ab.gebrauchsabgabe_longtail_plz) == 33


@pytest.mark.parametrize(
    ("nb_key", "typ", "satz", "basis"),
    [
        ("wiener_netze", "prozent", 0.07, "energie_und_netz"),
        ("ikb", "prozent", 0.06, "energie"),
        ("stadtwerke_klagenfurt", "ct_kwh", 1.637, "verbrauch"),
        ("salzburg_netz", "ct_kwh", 0.3789, "verbrauch"),
    ],
)
def test_regel_je_vnb(nb_key: str, typ: str, satz: float, basis: str) -> None:
    """Der nb_key-Pfad liefert die basisgenaue Regel (unabhängig von der PLZ)."""
    regel = gebrauchsabgabe_regel("0000", nb_key)
    assert regel is not None
    assert (regel.typ, regel.satz, regel.basis) == (typ, satz, basis)


@pytest.mark.parametrize("plz", ["6300", "6130"])  # Wörgl, Schwaz: Single-Gemeinde + Long-Tail
def test_regel_longtail_via_plz(plz: str) -> None:
    regel = gebrauchsabgabe_regel(plz, None)
    assert regel is not None
    assert (regel.typ, regel.satz, regel.basis) == ("prozent", 0.06, "energie_und_netz")


def test_regel_longtail_guard_multigemeinde() -> None:
    """Single-Gemeinde-Guard: geteilte PLZ wenden den Long-Tail NICHT an (-> None)."""
    # 6330 Kufstein ist multi-Gemeinde (Kufstein + Söll) -> Guard -> None.
    assert gebrauchsabgabe_regel("6330", None) is None


def test_regel_wien_fallback() -> None:
    """Wien (eigenes Bundesland) löst ohne nb_key auf die wiener_netze-Regel auf."""
    regel = gebrauchsabgabe_regel("1010", None)
    assert regel is not None
    assert (regel.typ, regel.satz, regel.basis) == ("prozent", 0.07, "energie_und_netz")


def test_regel_none_fail_open() -> None:
    assert gebrauchsabgabe_regel("8700", None) is None  # Leoben: keine GA-Region
    assert gebrauchsabgabe_regel("99999", None) is None  # unbekannte PLZ


def test_betrag_prozent_energie_und_netz() -> None:
    regel = gebrauchsabgabe_regel("0000", "wiener_netze")
    assert regel is not None
    assert regel.betrag_netto_eur(350.0, 322.80, 3500.0) == pytest.approx(0.07 * (350.0 + 322.80))


def test_betrag_prozent_energie_only() -> None:
    regel = gebrauchsabgabe_regel("0000", "ikb")
    assert regel is not None
    # basis=energie → Netz-Block geht NICHT in die Bemessung ein.
    assert regel.betrag_netto_eur(350.0, 322.80, 3500.0) == pytest.approx(0.06 * 350.0)


def test_betrag_ct_kwh_ignoriert_basisbloecke() -> None:
    regel = gebrauchsabgabe_regel("0000", "stadtwerke_klagenfurt")
    assert regel is not None
    assert regel.betrag_netto_eur(350.0, 322.80, 3500.0) == pytest.approx(1.637 * 3500.0 / 100.0)


def test_betrag_basis_netz() -> None:
    """basis=netz bemisst nur den Netz-Netto-Block (z.B. Imst 6 % auf Netz)."""
    regel = GebrauchsabgabeRegelDetail(typ="prozent", satz=0.06, basis="netz")
    assert regel.betrag_netto_eur(350.0, 322.80, 3500.0) == pytest.approx(0.06 * 322.80)


def test_netznutzung_netto_ohne_abgaben_fuer() -> None:
    nb = resolve_netzbetreiber("8700")  # Leoben → Energienetze Steiermark
    assert nb is not None
    tarif = tarif_fuer(nb)
    assert tarif is not None
    netz_netto = netznutzung_netto_ohne_abgaben_fuer(nb, 3500.0)
    assert netz_netto > 0.0
    # = (AP + Verlust) × kWh/100 + Pauschale, OHNE EAG/Elektrizitätsabgabe.
    erwartet = (
        tarif.netznutzung_arbeitspreis_ct_kwh + tarif.netzverlust_ct_kwh
    ) * 3500.0 / 100.0 + tarif.netznutzung_pauschale_eur_jahr
    assert netz_netto == pytest.approx(erwartet)


def test_netznutzung_netto_ohne_abgaben_fuer_none_fail_open() -> None:
    assert netznutzung_netto_ohne_abgaben_fuer(None, 3500.0) == 0.0
