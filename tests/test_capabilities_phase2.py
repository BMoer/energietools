# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Phase 2: Rechnungs-Zusammenführung, EEG-Kennzahlen, Tool-Bridge, Registry-Breite."""

from __future__ import annotations

import pytest

from energietools.capabilities.base import CapabilityError, FunctionCapability
from energietools.capabilities.community.metrics import community_metrics
from energietools.capabilities.registry import default_registry
from energietools.capabilities.tariffs.advice import advise_from_invoice
from energietools.models.invoice import Invoice

# =============================================================================
# 1. Pfeiler: Rechnung → auditierbarer Katalogvergleich
# =============================================================================


class TestTariffAdvice:
    def _invoice(self, **over) -> Invoice:
        base = dict(
            lieferant="Teuer AG",
            energiepreis_ct_kwh=40.0,
            grundgebuehr_eur_monat=10.0,
            jahresverbrauch_kwh=3200.0,
            plz="1060",
        )
        base.update(over)
        return Invoice(**base)

    def test_advise_produces_auditable_comparison(self):
        result = advise_from_invoice(self._invoice(), gebrauchsabgabe_rate=0.07)
        assert len(result.alternativen) > 0
        assert all(t.rechenweg is not None for t in result.alternativen)
        assert result.max_ersparnis_eur > 0

    def test_advise_uses_invoice_netzkosten_in_gesamtkosten(self):
        result = advise_from_invoice(
            self._invoice(netzkosten_eur_jahr=500.0), gebrauchsabgabe_rate=0.0,
        )
        best = result.beste_fix[0]
        assert best.gesamtkosten_eur == round(best.jahreskosten_eur + 500.0, 2)

    def test_advise_rejects_zero_consumption(self):
        with pytest.raises(CapabilityError):
            advise_from_invoice(self._invoice(jahresverbrauch_kwh=0.0))

    def test_advice_capability_via_registry(self):
        result = default_registry().get("tariff_advice").run(
            jahresverbrauch_kwh=3200,
            energiepreis_ct_kwh=40.0,
            grundgebuehr_eur_monat=10.0,
            gebrauchsabgabe_rate=0.07,
            plz="1060",
        )
        assert result.ok is True
        assert result.data["max_ersparnis_eur"] > 0


# =============================================================================
# 2. EEG-Community-Kennzahlen
# =============================================================================


class TestCommunityMetrics:
    def test_full_self_supply(self):
        """Erzeugung deckt Verbrauch exakt → SSR=SCR=100%."""
        m = community_metrics([2.0, 2.0], [2.0, 2.0])
        assert m.ssr_pct == 100.0
        assert m.scr_pct == 100.0
        assert m.reststrom_kwh == 0.0
        assert m.ueberschuss_kwh == 0.0

    def test_partial_overlap(self):
        """gen=[1,3], cons=[2,2]: intern=min=[1,2]=3, cons=4, gen=4."""
        m = community_metrics([1.0, 3.0], [2.0, 2.0])
        assert m.intern_gedeckt_kwh == 3.0
        assert m.reststrom_kwh == 1.0      # slot1: 2-1
        assert m.ueberschuss_kwh == 1.0    # slot2: 3-2
        assert m.ssr_pct == 75.0           # 3/4
        assert m.scr_pct == 75.0           # 3/4

    def test_no_generation(self):
        m = community_metrics([0.0, 0.0], [2.0, 2.0])
        assert m.ssr_pct == 0.0
        assert m.scr_pct == 0.0
        assert m.reststrom_kwh == 4.0

    def test_length_mismatch_raises(self):
        with pytest.raises(CapabilityError):
            community_metrics([1.0], [1.0, 2.0])

    def test_negative_raises(self):
        with pytest.raises(CapabilityError):
            community_metrics([-1.0], [1.0])

    def test_empty_raises(self):
        with pytest.raises(CapabilityError):
            community_metrics([], [])

    def test_via_registry(self):
        result = default_registry().get("community_metrics").run(
            erzeugung_kwh=[1.0, 3.0], verbrauch_kwh=[2.0, 2.0],
        )
        assert result.ok is True
        assert result.data["ssr_pct"] == 75.0

    def test_registry_rejects_non_list(self):
        result = default_registry().get("community_metrics").run(
            erzeugung_kwh="nope", verbrauch_kwh=[1.0],
        )
        assert result.ok is False
        assert "Listen" in result.error


# =============================================================================
# 3. FunctionCapability (Lazy-Import-Adapter)
# =============================================================================


class TestFunctionCapability:
    def test_callable_target(self):
        cap = FunctionCapability(
            name="double", summary="x2", target=lambda x: {"r": x * 2},
        )
        result = cap.run(x=21)
        assert result.ok is True
        assert result.data == {"r": 42}

    def test_lazy_import_target(self):
        cap = FunctionCapability(
            name="detect", summary="typ",
            target="energietools.capabilities.tariffs.catalog:detect_tariftyp",
        )
        result = cap.run(tarif_name="aWATTar Spot")
        assert result.ok is True
        assert result.data == "Stundenfloater"

    def test_bad_target_errors_in_envelope(self):
        cap = FunctionCapability(name="bad", summary="x", target="nonexistent.mod:fn")
        result = cap.run()
        assert result.ok is False
        assert "nicht ladbar" in result.error or "target" in result.error

    def test_pydantic_return_is_jsonable(self):
        cap = FunctionCapability(
            name="comm", summary="metrics",
            target="energietools.capabilities.community.metrics:community_metrics",
        )
        result = cap.run(erzeugung_kwh=[1.0], verbrauch_kwh=[1.0])
        assert result.ok is True
        assert isinstance(result.data, dict)
        assert result.data["ssr_pct"] == 100.0


# =============================================================================
# 4. Registry-Breite: das Rückgrat trägt alle Fähigkeiten
# =============================================================================


class TestRegistryBreadth:
    def test_all_expected_capabilities_registered(self):
        names = set(default_registry().names)
        expected = {
            "tariff_catalog", "tariff_compare", "tariff_advice", "community_metrics",
            # scenarios ersetzt das frühere battery_sim (tools/battery_sim.py gelöscht).
            "scenarios", "pv_sim", "beg_advisor", "spot_analysis",
            "load_profile", "energy_monitor", "web_search",
            # Rechenmodule aus dem pvtool-Merge:
            "grid_fees", "finance",
        }
        assert expected <= names

    def test_tool_definitions_complete(self):
        defs = default_registry().tool_definitions()
        assert len(defs) >= 11
        assert all(d["name"] and d["description"] and "input_schema" in d for d in defs)
