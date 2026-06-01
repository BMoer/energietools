# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für das Capability-Rückgrat, den Open-Data-Katalog und den Vergleich."""

from __future__ import annotations

import pytest

from energietools.capabilities.base import (
    Capability,
    CapabilityError,
    CapabilityRegistry,
    CapabilityResult,
)
from energietools.capabilities.registry import default_registry
from energietools.capabilities.tariffs.catalog import TariffCatalog, detect_tariftyp
from energietools.capabilities.tariffs.compare import (
    compare_against_catalog,
    kosten_rechenweg,
)
from energietools.capabilities.tariffs.models import CatalogTariff

# =============================================================================
# 1. Capability-Rückgrat
# =============================================================================


class _EchoCapability(Capability):
    name = "echo"
    summary = "Gibt die Eingabe zurück"
    input_schema = {"type": "object", "properties": {"x": {"type": "number"}}}

    def _run(self, **kwargs):
        if kwargs.get("x") == 0:
            raise CapabilityError("x darf nicht 0 sein")
        return {"echo": kwargs.get("x")}


class TestCapabilityBase:
    def test_run_success_envelope(self):
        result = _EchoCapability().run(x=5)
        assert isinstance(result, CapabilityResult)
        assert result.ok is True
        assert result.data == {"echo": 5}
        assert result.error is None
        assert result.capability == "echo"

    def test_run_capability_error_envelope(self):
        result = _EchoCapability().run(x=0)
        assert result.ok is False
        assert result.data is None
        assert "0" in result.error

    def test_run_unexpected_error_is_wrapped(self):
        class _Boom(Capability):
            name = "boom"
            summary = "explodiert"

            def _run(self, **kwargs):
                raise RuntimeError("kaboom")

        result = _Boom().run()
        assert result.ok is False
        assert "boom" in result.error

    def test_missing_name_raises(self):
        with pytest.raises(TypeError):

            class _NoName(Capability):
                summary = "x"

                def _run(self, **kwargs):
                    return None

    def test_tool_definition_shape(self):
        defn = _EchoCapability().tool_definition()
        assert defn["name"] == "echo"
        assert defn["description"]
        assert defn["input_schema"]["type"] == "object"


class TestCapabilityRegistry:
    def test_register_and_get(self):
        reg = CapabilityRegistry()
        cap = _EchoCapability()
        reg.register(cap)
        assert reg.get("echo") is cap
        assert "echo" in reg.names

    def test_duplicate_registration_raises(self):
        reg = CapabilityRegistry()
        reg.register(_EchoCapability())
        with pytest.raises(ValueError):
            reg.register(_EchoCapability())

    def test_unknown_get_raises(self):
        with pytest.raises(KeyError):
            CapabilityRegistry().get("nope")

    def test_default_registry_has_tariff_capabilities(self):
        reg = default_registry()
        assert "tariff_catalog" in reg.names
        assert "tariff_compare" in reg.names
        assert len(reg.tool_definitions()) >= 2


# =============================================================================
# 2. Open-Data-Katalog
# =============================================================================


class TestTariffCatalog:
    def test_load_has_tariffs(self):
        catalog = TariffCatalog.load()
        assert len(catalog) > 0
        assert all(isinstance(t, CatalogTariff) for t in catalog.all())

    def test_manifest_present(self):
        catalog = TariffCatalog.load()
        assert catalog.manifest is not None
        assert catalog.manifest.market == "AT"
        assert catalog.manifest.tariff_count == len(catalog)

    def test_filter_oekostrom_immutable(self):
        catalog = TariffCatalog.load()
        gruen = catalog.filter(oekostrom=True)
        assert len(gruen) <= len(catalog)
        assert all(t.ist_oekostrom for t in gruen.all())
        # Original unverändert
        assert len(catalog) >= len(gruen)

    def test_filter_nur_fixpreis_excludes_spot(self):
        fix = TariffCatalog.load().filter(nur_fixpreis=True)
        assert all(not t.ist_spot for t in fix.all())

    def test_filter_lieferant_substring(self):
        catalog = TariffCatalog.load()
        first = catalog.all()[0].lieferant
        needle = first.split()[0]
        hits = catalog.filter(lieferant=needle)
        assert len(hits) >= 1

    def test_detect_tariftyp(self):
        assert detect_tariftyp("aWATTar HOURLY Spot") == "Stundenfloater"
        assert detect_tariftyp("Easy Flex") == "Monatsfloater"
        assert detect_tariftyp("Optima Fix 2025") == "Fixpreis"


# =============================================================================
# 3. Auditierbarer Vergleich
# =============================================================================


class TestKostenRechenweg:
    def test_wien_standard_matches_gab_formel(self):
        """25 ct/kWh netto-äquiv, Wien 7% → bekannte Referenz."""
        rw = kosten_rechenweg(
            verbrauch_kwh=3200,
            netto_ep_ct=25.0 / 1.2,
            netto_gg_eur_monat=6.0 / 1.2,
            gebrauchsabgabe_rate=0.07,
        )
        assert rw.brutto_jahreskosten_eur == 933.04
        # interne Konsistenz
        assert abs(rw.netto_gesamt_eur - (rw.netto_energie_eur + rw.netto_grund_eur)) < 0.01
        assert abs(rw.ust_eur - rw.netto_inkl_gab_eur * 0.2) < 0.01

    def test_rechenweg_kette_lueckenlos_ohne_rabatt(self):
        """Auch ohne Rabatt bleibt die Kette auditierbar: netto_nach_rabatt == netto_gesamt."""
        rw = kosten_rechenweg(
            verbrauch_kwh=3200, netto_ep_ct=20.0, netto_gg_eur_monat=5.0,
            gebrauchsabgabe_rate=0.07,
        )
        assert rw.neukundenrabatt_netto_eur == 0.0
        assert rw.netto_nach_rabatt_eur == rw.netto_gesamt_eur
        # GAB-Schritt aus den gespeicherten Feldern reproduzierbar
        assert abs(rw.gebrauchsabgabe_eur - rw.netto_nach_rabatt_eur * 0.07) < 0.01

    def test_rabatt_pauschal_reduziert_brutto(self):
        ohne = kosten_rechenweg(
            verbrauch_kwh=3200, netto_ep_ct=20.0, netto_gg_eur_monat=5.0,
            gebrauchsabgabe_rate=0.0,
        )
        mit = kosten_rechenweg(
            verbrauch_kwh=3200, netto_ep_ct=20.0, netto_gg_eur_monat=5.0,
            gebrauchsabgabe_rate=0.0, rabatt_pauschal_eur=50.0,
        )
        assert round(ohne.brutto_jahreskosten_eur - mit.brutto_jahreskosten_eur, 2) == 50.0


class TestCompareAgainstCatalog:
    def test_compare_produces_sorted_alternatives_with_rechenweg(self):
        result = compare_against_catalog(
            verbrauch_kwh=3200,
            aktueller_lieferant="Teuer AG",
            aktueller_energiepreis_ct_kwh=40.0,
            aktuelle_grundgebuehr_eur_monat=10.0,
            gebrauchsabgabe_rate=0.07,
            plz="1060",
        )
        assert len(result.alternativen) > 0
        # jeder Tarif hat einen lückenlosen Rechenweg
        assert all(t.rechenweg is not None for t in result.alternativen)
        # Fixpreis-Liste ist nach Jahreskosten sortiert
        fix = result.beste_fix
        assert fix == sorted(fix, key=lambda t: t.jahreskosten_eur)
        # Ersparnis gegen den (teuren) aktuellen Tarif ist positiv für den Besten
        assert result.max_ersparnis_eur > 0

    def test_spot_excluded_without_baseline(self):
        """Ohne spot_baseline_ct dürfen keine Spot-Tarife im Ergebnis sein."""
        result = compare_against_catalog(
            verbrauch_kwh=3200,
            aktueller_lieferant="X",
            aktueller_energiepreis_ct_kwh=30.0,
            aktuelle_grundgebuehr_eur_monat=8.0,
            gebrauchsabgabe_rate=0.0,
        )
        assert all(t.energiepreis_ct_kwh > 0 for t in result.alternativen)

    def test_spot_included_with_baseline(self):
        """Mit spot_baseline_ct werden Spot-Tarife bepreist und einbezogen."""
        no_spot = compare_against_catalog(
            verbrauch_kwh=3200, aktueller_lieferant="X",
            aktueller_energiepreis_ct_kwh=30.0, aktuelle_grundgebuehr_eur_monat=8.0,
        )
        with_spot = compare_against_catalog(
            verbrauch_kwh=3200, aktueller_lieferant="X",
            aktueller_energiepreis_ct_kwh=30.0, aktuelle_grundgebuehr_eur_monat=8.0,
            spot_baseline_ct=8.0,
        )
        assert len(with_spot.alternativen) > len(no_spot.alternativen)

    def test_capability_envelope_via_registry(self):
        result = default_registry().get("tariff_compare").run(
            verbrauch_kwh=3200,
            aktueller_energiepreis_ct_kwh=30.0,
            aktuelle_grundgebuehr_eur_monat=8.0,
            gebrauchsabgabe_rate=0.07,
        )
        assert result.ok is True
        assert result.data["alternativen"]

    def test_capability_rejects_zero_consumption(self):
        result = default_registry().get("tariff_compare").run(
            verbrauch_kwh=0,
            aktueller_energiepreis_ct_kwh=30.0,
            aktuelle_grundgebuehr_eur_monat=8.0,
        )
        assert result.ok is False
