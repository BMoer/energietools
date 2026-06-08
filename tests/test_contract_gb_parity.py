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


@pytest.mark.parametrize("plz", ["6300"])  # Wörgl: Single-Gemeinde in BEIDEN Repos
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


@pytest.mark.xfail(
    strict=True,
    reason="et PLZ-Index 21->2233 erst mit S2; Schwaz 6130 noch nicht im et-Snapshot. "
    "Flippt nach S2 auf XPASS und erzwingt das Entfernen dieses xfail.",
)
def test_gab_regel_parity_longtail_pending_s2() -> None:
    """6130 (Schwaz) ist in gb (2233 PLZ), aber noch nicht in et (21 PLZ) -> heute None."""
    plz = "6130"
    gb_r = gb_regel(plz, None)
    assert gb_r is not None  # gb kennt Schwaz als Long-Tail
    assert et_regel(plz, None) is not None  # et HEUTE None -> failt (erwartet); S2 fügt PLZ hinzu


@pytest.mark.xfail(
    strict=True,
    reason="Single-Gemeinde-Guard fehlt bei et's skalarer PlzInfo (S1); 6330 Kufstein ist "
    "in gb multi-Gemeinde (Guard -> None), et wendet Long-Tail an. Fix mit S2.",
)
def test_gab_regel_guard_multigemeinde_pending_s2() -> None:
    """Cross-Cutting-Risk #7: ohne Listen-PLZ kann et den Single-Gemeinde-Guard nicht erzwingen."""
    plz = "6330"  # Kufstein: in gb multi-Gemeinde -> Guard -> None
    assert gb_regel(plz, None) is None
    assert et_regel(plz, None) is None  # et HEUTE: Regel (kein Guard) -> failt; S2 fixt
