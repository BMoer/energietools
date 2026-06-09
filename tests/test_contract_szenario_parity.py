# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Cross-Repo-Szenario-Paritäts-Contract — der Drift-Guard für den S5-Cutover.

Beweist, dass die EINE Szenario-Kosten-Engine (``energietools.cost.gesamtkosten_szenario``)
feldweise mit gridberts ``_tariff_from_row`` übereinstimmt — inklusive der zwei
Features, die ``GesamtkostenCapability`` allein nicht hatte und den Cutover blockiert
hätten: **Neukundenrabatt** und **Spot/Floater-Effektivpreis** (EPEX-Backtest). Damit
ist „et statt gb rechnen lassen" für den vollen Tarif-Loop sicher, nicht nur für den
plain Fixpreis.

Skippt, wenn gridbert nicht als Sibling ausgecheckt ist. Spot auf der frozen
EPEX-Fixture (netzfrei, deterministisch).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("gridbert")

from energietools.cost import gesamtkosten_szenario  # noqa: E402

_FIXTURE = Path(__file__).parent / "fixtures" / "epex_at_frozen.json"
_KWH = 3500.0


def _frozen_epex() -> list[dict]:
    return json.loads(_FIXTURE.read_text("utf-8"))


def _gb_tariff_from_row(plz: str, row: dict, spot_prices: list[dict]):
    """gridberts Original-Kosten-Math für eine tariffs-Zeile (Referenz)."""
    from gridbert.netz.abgaben import gebrauchsabgabe_regel as gb_regel
    from gridbert.netz.resolve import (
        netzbetreiber_fuer,
        netznutzung_netto_ohne_abgaben_fuer,
    )
    from gridbert.services.tariff_comparison_db import _tariff_from_row

    nb = netzbetreiber_fuer(plz, None)
    netz_netto_ga = netznutzung_netto_ohne_abgaben_fuer(nb, _KWH)
    regel = gb_regel(plz, nb.key if nb else None)
    return _tariff_from_row(row, _KWH, spot_prices, regel, netz_netto_ga)


def test_szenario_rabatt_parity() -> None:
    """Fixpreis MIT Neukundenrabatt (ct/kWh + Pauschale): et == gb feldweise."""
    plz = "1060"  # Wien: prozent-GA energie_und_netz (der Haupt-Drift-Punkt)
    row = {
        "lieferant": "X", "tarif_name": "T", "tariftyp": "Fixpreis",
        "energiepreis_ct_kwh": 10.0, "grundgebuehr_eur_monat": 3.5,
        "neukundenrabatt_ct_kwh": 2.0, "neukundenrabatt_eur": 30.0,
    }
    gb = _gb_tariff_from_row(plz, row, [])
    et = gesamtkosten_szenario(
        plz=plz, verbrauch_kwh=_KWH, netto_ep_ct=10.0, netto_gg_eur_monat=3.5,
        neukundenrabatt_ct_kwh=2.0, neukundenrabatt_eur=30.0,
    )
    assert gb is not None and et is not None
    # Energie-Jahreskosten inkl. Rabatt — DIE Parität, die den Cutover absichert.
    assert et["jahreskosten_energie_brutto_eur"] == pytest.approx(gb.jahreskosten_eur, abs=0.02)
    # Gebrauchsabgabe-Block (Vor-Rabatt-Basis, basisgenau).
    assert et["gebrauchsabgabe_eur"] == pytest.approx(gb.gebrauchsabgabe_eur, abs=0.02)
    # Rechenweg feldweise (netto_nach_rabatt, USt-auf-Energie, Rabatt-netto).
    assert et["rechenweg"].netto_nach_rabatt_eur == pytest.approx(
        gb.rechenweg.netto_nach_rabatt_eur, abs=0.02,
    )
    assert et["rechenweg"].ust_eur == pytest.approx(gb.rechenweg.ust_eur, abs=0.02)


@pytest.mark.parametrize("tariftyp", ["Stundenfloater", "Monatsfloater"])
def test_szenario_spot_parity(tariftyp: str) -> None:
    """Spot/Floater (ep=0 → EPEX-Effektivpreis): et-Energie-Jahreskosten == gb."""
    epex = _frozen_epex()
    plz = "8700"  # Leoben: keine GA → isoliert den Energie/Spot-Pfad
    row = {
        "lieferant": "X", "tarif_name": "T", "tariftyp": tariftyp,
        "energiepreis_ct_kwh": 0.0, "grundgebuehr_eur_monat": 0.0,
        "spot_aufschlag_ct": 1.5,
    }
    gb = _gb_tariff_from_row(plz, row, epex)
    et = gesamtkosten_szenario(
        plz=plz, verbrauch_kwh=_KWH, netto_ep_ct=0.0, netto_gg_eur_monat=0.0,
        tariftyp=tariftyp, spot_aufschlag_ct=1.5, spot_prices=epex,
    )
    assert gb is not None and et is not None
    assert et["jahreskosten_energie_brutto_eur"] > 0
    assert et["jahreskosten_energie_brutto_eur"] == pytest.approx(gb.jahreskosten_eur, abs=0.05)
