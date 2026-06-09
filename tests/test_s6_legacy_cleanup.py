# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""S6: Strip-Guards für den gelöschten energie-only Flat-Gebrauchsabgabe-Pfad.

Beweist, dass der veraltete rate-only-Pfad (Funktion ``gebrauchsabgabe_rate``,
``_regel_trifft``, das match-basierte ``GebrauchsabgabeRegel``-Modell, die
``Abgaben``-Flat-Felder und der ``gebrauchsabgabe``-Block in ``abgaben.json``)
ENTFERNT ist — autoritativ ist die basisgenaue GA (``gebrauchsabgabe_je_vnb`` /
``gebrauchsabgabe_longtail_plz``), die weiterhin lädt.
"""

from __future__ import annotations

import json

from energietools.capabilities.netz import models, resolve
from energietools.capabilities.netz.data import _read_data, load_abgaben


def _raw_abgaben() -> dict:
    return json.loads(_read_data("abgaben.json"))


def test_abgaben_json_no_superseded_block() -> None:
    raw = _raw_abgaben()
    assert "gebrauchsabgabe" not in raw  # der _superseded Flat-Block ist weg
    # Die basisgenauen Daten + föderalen Konstanten bleiben.
    assert "gebrauchsabgabe_je_vnb" in raw
    assert "gebrauchsabgabe_longtail_plz" in raw
    assert "federal" in raw


def test_gebrauchsabgabe_rate_function_removed() -> None:
    assert not hasattr(resolve, "gebrauchsabgabe_rate")
    assert not hasattr(resolve, "_regel_trifft")
    # Die basisgenaue Resolution bleibt.
    assert hasattr(resolve, "gebrauchsabgabe_regel")


def test_abgaben_model_no_flat_ga_fields() -> None:
    felder = set(models.Abgaben.model_fields)
    flat = {"gebrauchsabgabe_basis", "gebrauchsabgabe_regeln", "gebrauchsabgabe_default"}
    assert flat & felder == set()
    # Das match-basierte Modell ist weg; das basisgenaue Detail-Modell bleibt.
    assert not hasattr(models, "GebrauchsabgabeRegel")
    assert hasattr(models, "GebrauchsabgabeRegelDetail")


def test_load_abgaben_basisgenau_intakt() -> None:
    """Regression: S6 darf die gehaltenen basisgenauen Daten nicht beschädigen."""
    abgaben = load_abgaben()
    assert "wiener_netze" in abgaben.gebrauchsabgabe_je_vnb
    wien = abgaben.gebrauchsabgabe_je_vnb["wiener_netze"]
    assert (wien.typ, wien.satz, wien.basis) == ("prozent", 0.07, "energie_und_netz")
    assert len(abgaben.gebrauchsabgabe_longtail_plz) > 0
    assert abgaben.federal  # föderale Konstanten vorhanden
