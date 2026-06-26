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
from energietools.capabilities.tariffs.catalog import (
    TariffCatalog,
    _ist_gas_eintrag,
    detect_tariftyp,
)
from energietools.capabilities.tariffs.compare import kosten_rechenweg
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
        assert "gesamtkosten" in reg.names  # Kosten-Engine bleibt
        assert "tariff_compare" not in reg.names  # Vergleich lebt im Produkt (S4)
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


class TestGasFilter:
    """Der Strom-only-Katalog darf keine fehl-gescrapten Gas-Tarife enthalten."""

    def test_gas_durch_index(self):
        assert _ist_gas_eintrag({"tarif_name": "E1 Smart Gas", "spot_index": "EEX THE"})

    def test_gas_durch_namen_als_wort(self):
        assert _ist_gas_eintrag({"tarif_name": "E1 Gas Fix", "energiepreis_ct_kwh": 6.5})
        assert _ist_gas_eintrag({"tarif_name": "go green gas plus", "energiepreis_ct_kwh": 5.3})

    def test_gas_durch_implausiblen_strompreis(self):
        # "redgas Optimal 2026" trägt kein "gas" als Wort, aber 7,99 ct ist kein Strompreis.
        assert _ist_gas_eintrag({"tarif_name": "redgas Optimal 2026", "energiepreis_ct_kwh": 7.99})

    def test_strom_von_anbieter_mit_gas_im_namen_bleibt(self):
        # "goldgas"/"redgas" verkaufen auch Strom — Lieferantenname darf NICHT triggern.
        assert not _ist_gas_eintrag(
            {"lieferant": "goldgas GmbH", "tarif_name": "strom: derFixe", "energiepreis_ct_kwh": 15.0},
        )
        assert not _ist_gas_eintrag(
            {"lieferant": "redgas GmbH", "tarif_name": "redgas red strom optimal 2025", "energiepreis_ct_kwh": 18.99},
        )

    def test_strom_spot_ist_kein_gas(self):
        # Strom-Spot hat energiepreis 0 (Aufschlag-Modell) → darf nicht als Gas gelten.
        assert not _ist_gas_eintrag(
            {"tarif_name": "aWATTar HOURLY", "energiepreis_ct_kwh": 0.0, "spot_index": "EPEX AT"},
        )

    def test_explizites_energy_type_gewinnt(self):
        assert _ist_gas_eintrag({"tarif_name": "Irgendwas", "energy_type": "GAS", "energiepreis_ct_kwh": 20.0})
        assert not _ist_gas_eintrag({"tarif_name": "Fix Gas-Schein", "energy_type": "POWER", "energiepreis_ct_kwh": 5.0})

    def test_geladener_katalog_ist_gasfrei(self):
        """Regression: kein geladener Tarif ist Gas (Index/Name/Preis)."""
        for t in TariffCatalog.load().all():
            assert not _ist_gas_eintrag(t.model_dump()), f"Gas im Strom-Katalog: {t.lieferant} — {t.tarif_name}"

    def test_keine_unplausiblen_strom_fixpreise(self):
        fix = TariffCatalog.load().filter(nur_fixpreis=True)
        for t in fix.all():
            assert t.energiepreis_ct_kwh == 0.0 or t.energiepreis_ct_kwh >= 8.5


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
        assert rw.brutto_jahreskosten_eur == pytest.approx(872.0, abs=0.01)  # Energie, ohne GAB
        assert rw.gebrauchsabgabe_eur == pytest.approx(61.04, abs=0.01)  # eigener Brutto-Block
        # interne Konsistenz
        assert abs(rw.netto_gesamt_eur - (rw.netto_energie_eur + rw.netto_grund_eur)) < 0.01
        assert abs(rw.ust_eur - rw.netto_gesamt_eur * 0.2) < 0.01

    def test_rechenweg_kette_lueckenlos_ohne_rabatt(self):
        """Auch ohne Rabatt bleibt die Kette auditierbar: netto_nach_rabatt == netto_gesamt."""
        rw = kosten_rechenweg(
            verbrauch_kwh=3200, netto_ep_ct=20.0, netto_gg_eur_monat=5.0,
            gebrauchsabgabe_rate=0.07,
        )
        assert rw.neukundenrabatt_netto_eur == 0.0
        assert rw.netto_nach_rabatt_eur == rw.netto_gesamt_eur
        # GAB-Block (brutto) aus den gespeicherten Feldern reproduzierbar
        assert abs(rw.gebrauchsabgabe_eur - rw.netto_nach_rabatt_eur * 0.07 * 1.2) < 0.01

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


class TestComparisonSurfaceRemoved:
    """S4: et ist reine Kosten-Engine — die Vergleichs-Oberfläche ist entfernt."""

    def test_compare_against_catalog_removed(self):
        import energietools.capabilities.tariffs.compare as compare_mod

        assert not hasattr(compare_mod, "compare_against_catalog")
        assert hasattr(compare_mod, "kosten_rechenweg")  # die Kosten-Engine bleibt

    def test_compare_capabilities_not_registered(self):
        namen = set(default_registry().names)
        assert {"tariff_compare", "tariff_advice", "tarifvergleich_inkl_netz"} & namen == set()
        assert {"tariff_catalog", "gesamtkosten"} <= namen
