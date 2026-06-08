# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Cross-Repo-Spot-Paritäts-Contract (Drift-Guard für S3).

Beweist, dass der nach et portierte Spot/Floater-Backtest feldweise mit gridberts
Original übereinstimmt — auf einer **frozen** EPEX-Fixture (netzfrei, deterministisch).
Skippt automatisch, wenn gridbert nicht als Sibling ausgecheckt ist
(``importorskip``). Die Fixture wird im MAIN-Shell erzeugt (Subagents = kein Netz).

Kritisch (Cross-Cutting-Risk #3): leere EPEX-Serie → 0 Spot-Zeilen → falsche
„0 == 0"-Parität. Daher wird VOR der Parität asserted, dass die Fixture nicht leer
ist UND mindestens eine Spot-Zeile mit Kosten > 0 bepreist wurde.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

gb_spot = pytest.importorskip("gridbert.tools.spot_pricing")

from energietools.capabilities.tariffs.models import CatalogTariff  # noqa: E402
from energietools.tools import spot_pricing as et_spot  # noqa: E402

_FIXTURE = Path(__file__).parent / "fixtures" / "epex_at_frozen.json"


def _frozen_epex() -> list[dict]:
    return json.loads(_FIXTURE.read_text("utf-8"))


def _et_tariff(tariftyp: str, aufschlag: float) -> CatalogTariff:
    return CatalogTariff(
        key="x", lieferant="x", tarif_name="t", tariftyp=tariftyp, spot_aufschlag_ct=aufschlag,
    )


def _gb_tariff(tariftyp: str, aufschlag: float):
    from gridbert.models.tariff import Tariff

    return Tariff(
        lieferant="x", tarif_name="t", energiepreis_ct_kwh=0.0,
        grundgebuehr_eur_monat=0.0, jahreskosten_eur=0.0,
        tariftyp=tariftyp, spot_aufschlag_ct=aufschlag,
    )


def test_fixture_nonempty() -> None:
    epex = _frozen_epex()
    assert len(epex) > 0, "Frozen EPEX-Fixture ist leer — Spot-Parität wäre vacuously true."


@pytest.mark.parametrize("tariftyp", ["Stundenfloater", "Monatsfloater"])
def test_spot_effective_parity(tariftyp: str) -> None:
    epex = _frozen_epex()
    aufschlag = 1.5
    annual_kwh = 3500.0

    et_res = et_spot.effective_for_tariff(_et_tariff(tariftyp, aufschlag), annual_kwh, epex)
    gb_res = gb_spot.effective_for_tariff(_gb_tariff(tariftyp, aufschlag), annual_kwh, epex)

    # Mindestens eine Spot-Zeile wurde tatsächlich bepreist (kein false 0==0).
    assert et_res["jahreskosten_energie_netto_eur"] > 0
    assert gb_res["jahreskosten_energie_netto_eur"] > 0

    # Feldweise Parität (verbatim-Port → identisch).
    assert et_res["effektiver_arbeitspreis_netto_ct"] == pytest.approx(
        gb_res["effektiver_arbeitspreis_netto_ct"], abs=0.01,
    )
    assert et_res["avg_spot_volumengewichtet_ct"] == pytest.approx(
        gb_res["avg_spot_volumengewichtet_ct"], abs=0.01,
    )
    assert et_res["jahreskosten_energie_netto_eur"] == pytest.approx(
        gb_res["jahreskosten_energie_netto_eur"], abs=0.01,
    )
    assert et_res["profilkostenfaktor_pct"] == pytest.approx(
        gb_res["profilkostenfaktor_pct"], abs=0.01,
    )


def test_spot_breakdown_parity() -> None:
    epex = _frozen_epex()
    et_res = et_spot.compute_spot_breakdown(_et_tariff("Stundenfloater", 1.5), 3500.0, epex)
    gb_res = gb_spot.compute_spot_breakdown(_gb_tariff("Stundenfloater", 1.5), 3500.0, epex)
    assert et_res["anzahl_jahre"] == gb_res["anzahl_jahre"] >= 1
    assert et_res["mittel_arbeitspreis_netto_ct"] == pytest.approx(
        gb_res["mittel_arbeitspreis_netto_ct"], abs=0.01,
    )
