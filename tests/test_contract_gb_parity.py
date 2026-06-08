# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Cross-Repo-Contract: et's basisgenaue Gebrauchsabgabe == gridbert's (Drift-Guard).

Läuft nur im kombinierten Sibling-Checkout (``~/Projekte/gridbert`` neben
``~/Projekte/energietools``); fehlt gridbert, wird der Test geskippt. Er hält
während des Migrationsfensters fest, dass et's GA-COMPUTE 1:1 dem gridbert-
Referenz-Compute (``gridbert/netz/abgaben.py``) entspricht.

Scope dieses Tests (S1): die GA-Regel-Auflösung + ``betrag_netto_eur`` (typ/satz/
basis). Die End-to-End-Parität über ``compare_from_db`` vs ``GesamtkostenCapability``
(inkl. PLZ→VNB-Auflösung + gesamtkosten) folgt mit S2 (voller PLZ-Index) und S4
(Capability-Verdrahtung) — siehe docs/PLAN_PRIO1_ET_KONSOLIDIERUNG.md.
"""

from __future__ import annotations

import pytest

from energietools.capabilities.netz.resolve import gebrauchsabgabe_regel as et_regel

# Skippt sauber, wenn gridbert (AGPL-Produkt) nicht als Sibling ausgecheckt ist.
gb_abgaben = pytest.importorskip("gridbert.netz.abgaben")
gb_regel = gb_abgaben.gebrauchsabgabe_regel

# Bemessungs-Inputs für den betrag-Vergleich (fix, deterministisch).
_E, _N, _KWH = 350.0, 322.80, 3500.0


def _triple(regel: object) -> tuple[str, float, str]:
    return (regel.typ, regel.satz, regel.basis)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "nb_key", ["wiener_netze", "ikb", "stadtwerke_klagenfurt", "salzburg_netz"]
)
def test_gab_regel_parity_je_vnb(nb_key: str) -> None:
    """Die 4 je-VNB-Regeln sind in et und gb identisch (typ/satz/basis + Betrag)."""
    et_r = et_regel("0000", nb_key)
    gb_r = gb_regel("0000", nb_key)
    assert et_r is not None and gb_r is not None
    assert _triple(et_r) == _triple(gb_r)
    assert et_r.betrag_netto_eur(_E, _N, _KWH) == pytest.approx(
        gb_r.betrag_netto_eur(_E, _N, _KWH)
    )


@pytest.mark.parametrize("plz", ["6300", "6130"])  # Wörgl, Schwaz: Single-Gemeinde in BEIDEN
def test_gab_regel_parity_longtail(plz: str) -> None:
    et_r = et_regel(plz, None)
    gb_r = gb_regel(plz, None)
    assert et_r is not None and gb_r is not None
    assert _triple(et_r) == _triple(gb_r)
    assert et_r.betrag_netto_eur(_E, _N, _KWH) == pytest.approx(
        gb_r.betrag_netto_eur(_E, _N, _KWH)
    )


def test_gab_regel_parity_wien_fallback() -> None:
    et_r = et_regel("1010", None)
    gb_r = gb_regel("1010", None)
    assert et_r is not None and gb_r is not None
    assert _triple(et_r) == _triple(gb_r)


def test_gab_regel_parity_no_ga_region() -> None:
    assert et_regel("8700", None) is None
    assert gb_regel("8700", None) is None


def test_gab_regel_parity_guard_multigemeinde() -> None:
    """Single-Gemeinde-Guard greift in BEIDEN Repos identisch (S2-Resultat).

    6330 Kufstein ist im Voll-Schema multi-Gemeinde (Kufstein + Söll) -> der
    Guard liefert in gb UND et None (kein Mis-Apply des Long-Tail).
    """
    assert gb_regel("6330", None) is None
    assert et_regel("6330", None) is None
