# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für den Tarifvergleichs-Kern (B.1-Move) + Capability-Hülle (B.2/B.3/B.6).

Die Zahlen-Erwartungen der Paritäts-Tests stammen aus den Referenz-Tests des
Ursprungs-Repos (gridbert ``tests/services/test_tariff_comparison_db*.py``,
gleiche Fixtures/Inputs) und wurden zusätzlich per Live-Cross-Run gegen
``compare_from_db`` verifiziert: gleiche Inputs → identische €-Zahlen.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from energietools.capabilities.tariff_compare import (
    TariffCompareCapability,
    vergleiche_tarife,
)


class FakeTariffSource:
    """Strukturelle TariffSource — In-Memory-Zeilen, kein Storage."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def get_latest(self, *, status: str, energy_type: str) -> list[dict]:
        return [r for r in self._rows if (r.get("energy_type") or "POWER") == energy_type]


class FakeSpotPriceSource:
    """Strukturelle SpotPriceSource ohne EPEX-Daten (Spot-Tarife entfallen)."""

    def available_years(self) -> list[int]:
        return []

    def get_prices(self, start: datetime, end: datetime) -> list[dict]:
        return []


def _fix(key, lieferant, name, ep_netto, gg_netto=5.0, **extra) -> dict:
    return {
        "key": key, "lieferant": lieferant, "tarif_name": name,
        "tariftyp": "Fixpreis", "energiepreis_ct_kwh": ep_netto,
        "grundgebuehr_eur_monat": gg_netto, "ist_oekostrom": False, **extra,
    }


def _vergleich(rows: list[dict], plz: str = "1060", **kwargs):
    args = dict(
        plz=plz,
        jahresverbrauch_kwh=3500,
        aktueller_lieferant="Alt",
        aktueller_energiepreis_brutto_ct_kwh=15.0,
        aktuelle_grundgebuehr_brutto_eur_monat=0.0,
        tariff_source=FakeTariffSource(rows),
        spot_source=FakeSpotPriceSource(),
    )
    args.update(kwargs)
    return vergleiche_tarife(**args)


# =============================================================================
# 1. Paritäts-Tests (gleiche Inputs wie die gridbert-Referenz → gleiche Zahlen)
# =============================================================================


class TestParitaet:
    def test_ranks_cheapest_first_and_computes_savings(self):
        cmp = _vergleich(
            [_fix("a", "Anbieter A", "Günstig", 8.0), _fix("b", "Anbieter B", "Teuer", 20.0)],
            aktueller_energiepreis_brutto_ct_kwh=30.0,
            aktuelle_grundgebuehr_brutto_eur_monat=6.0,
        )
        assert cmp.alternativen[0].lieferant == "Anbieter A"
        assert cmp.alternativen[0].jahreskosten_eur < cmp.alternativen[1].jahreskosten_eur
        assert cmp.max_ersparnis_eur > 0
        assert cmp.bester_gesamt.lieferant == "Anbieter A"

    def test_brutto_conversion(self):
        # 10 ct/kWh netto, 3500 kWh, GG 0 → netto 350 EUR → brutto 420 EUR (×1.2).
        # Referenzwert identisch zu gridbert test_brutto_conversion (PLZ 1060).
        cmp = _vergleich([_fix("a", "A", "T", 10.0, gg_netto=0.0)])
        assert abs(cmp.alternativen[0].jahreskosten_eur - 420.0) < 0.5

    def test_gebrauchsabgabe_eigener_block_nicht_in_jahreskosten(self):
        # Wien (PLZ 1060, 7 % GAB): jahreskosten = nur Energie (420 €); GAB eigener
        # Block 56,52 € (Energie-Netto 350 + Netznutzungs-Netto 322,80 = 672,80
        # × 7 % × 1,2); gesamtkosten = Energie + Netz + GAB. Referenz: gridbert.
        cmp = _vergleich([_fix("a", "A", "T", 10.0, gg_netto=0.0)])
        t = cmp.alternativen[0]
        assert abs(t.jahreskosten_eur - 420.0) < 0.5
        assert abs(t.gebrauchsabgabe_eur - 56.52) < 0.3
        erwartet = t.jahreskosten_eur + cmp.netzkosten_eur_jahr + t.gebrauchsabgabe_eur
        assert abs(t.gesamtkosten_eur - erwartet) < 0.05

    def test_rechenweg_energie_kette_schliesst_zeile_fuer_zeile(self):
        # Mit Rabatt: die Energie-Kette muss Zeile-für-Zeile aufgehen (Audit-Prinzip).
        cmp = _vergleich(
            [_fix("a", "A", "T", 12.0, gg_netto=5.0,
                  neukundenrabatt_ct_kwh=1.0, neukundenrabatt_eur=30.0)],
            aktueller_energiepreis_brutto_ct_kwh=20.0,
            aktuelle_grundgebuehr_brutto_eur_monat=6.0,
        )
        rw = cmp.alternativen[0].rechenweg
        assert rw is not None
        # (1) netto_gesamt − Rabatt(netto) = netto_nach_rabatt
        nach_rabatt = rw.netto_gesamt_eur - rw.neukundenrabatt_netto_eur
        assert abs(nach_rabatt - rw.netto_nach_rabatt_eur) < 0.05
        # (2) netto_nach_rabatt + USt = brutto_jahreskosten (Kette schließt)
        assert abs((rw.netto_nach_rabatt_eur + rw.ust_eur) - rw.brutto_jahreskosten_eur) < 0.05
        # (3) USt liegt auf netto_nach_rabatt (nicht auf netto_gesamt)
        assert abs(rw.ust_eur - rw.netto_nach_rabatt_eur * 0.2) < 0.05
        # (4) GAB ist BRUTTO und NICHT in brutto_jahreskosten enthalten
        assert rw.gebrauchsabgabe_eur > 0  # Wien
        assert cmp.alternativen[0].gebrauchsabgabe_eur == rw.gebrauchsabgabe_eur

    def test_gebrauchsabgabe_null_ausserhalb_wien(self):
        cmp = _vergleich([_fix("a", "A", "T", 10.0, gg_netto=0.0)], plz="8700")
        assert cmp.alternativen[0].gebrauchsabgabe_eur == 0.0

    def test_neukundenrabatt_year1_vs_year2(self):
        cmp = _vergleich([_fix(
            "a", "A", "Bonus-Tarif", 10.0, gg_netto=0.0,
            neukundenrabatt_eur=60.0, neukundenrabatt_name="60 EUR Bonus",
        )])
        t = cmp.alternativen[0]
        assert t.jahreskosten_eur < t.jahreskosten_ohne_rabatt_eur
        assert abs(t.jahreskosten_ohne_rabatt_eur - t.jahreskosten_eur - 60.0) < 0.5

    def test_regionale_verfuegbarkeit_filtert_fremden_landesversorger(self):
        """Out-of-Region-Landesversorger (TIWAG/Tirol) darf an NÖ-Adresse NICHT ranken."""
        rows = [
            _fix("verbund", "VERBUND Energy4Business GmbH", "Fix V", 12.0, gg_netto=3.0),
            _fix("tiwag", "TIWAG-Tiroler Wasserkraft AG", "Fix T", 9.0, gg_netto=2.0),
        ]
        noe = _vergleich(rows, plz="2103")
        assert [t.lieferant for t in noe.alternativen] == ["VERBUND Energy4Business GmbH"]
        tirol = _vergleich(rows, plz="6020")
        assert {t.lieferant for t in tirol.alternativen} == {
            "VERBUND Energy4Business GmbH", "TIWAG-Tiroler Wasserkraft AG",
        }
        assert tirol.alternativen[0].lieferant == "TIWAG-Tiroler Wasserkraft AG"

    def test_gas_filter_uses_injected_source(self):
        rows = [
            _fix("p", "Strom AG", "Fix S", 20.0, gg_netto=4.0),
            {**_fix("g", "Gas AG", "Fix G", 10.0, gg_netto=3.0), "energy_type": "GAS"},
        ]
        cmp = _vergleich(
            rows, plz="1010", jahresverbrauch_kwh=12000,
            aktueller_lieferant="Alt-Gas",
            aktueller_energiepreis_brutto_ct_kwh=14.0,
            aktuelle_grundgebuehr_brutto_eur_monat=5.0,
            energy_type="GAS",
        )
        assert [t.lieferant for t in cmp.alternativen] == ["Gas AG"]
        # Gas: keine Strom-Gebrauchsabgabe, kein Netzkosten-Block
        assert cmp.alternativen[0].gebrauchsabgabe_eur == 0.0
        assert cmp.netzkosten_eur_jahr == 0.0

    def test_quelle_extern_default(self):
        """Default ohne explizites ``quelle=`` ist neutral ("extern"), nicht
        gridbert-spezifisch ("scraper") — injizierte Fremd-Quellen sind nicht
        zwingend ein Scraper."""
        cmp = _vergleich([_fix("a", "A", "T", 10.0)])
        assert all(t.quelle == "extern" for t in cmp.alternativen)

    def test_nb_key_vorgeloest_wird_verwendet(self):
        """Vorgelöster nb_key (B.1-Schnitt) übersteuert die PLZ-Auflösung."""
        # PLZ 9999 existiert nicht → ohne nb_key kein Netzbetreiber; mit
        # vorgelöstem Wiener-Netze-Key kommen Wiener Netz-/GA-Werte.
        ohne = _vergleich([_fix("a", "A", "T", 10.0, gg_netto=0.0)], plz="9999")
        mit = _vergleich(
            [_fix("a", "A", "T", 10.0, gg_netto=0.0)], plz="9999", nb_key="wiener_netze",
        )
        assert ohne.netzkosten_eur_jahr == 0.0
        assert mit.netzkosten_eur_jahr > 0.0
        assert mit.netzbetreiber
        assert mit.alternativen[0].gebrauchsabgabe_eur > 0.0  # Wien-GA folgt dem nb_key


# =============================================================================
# 2. Leerer Vergleich = gültiges Ergebnis (kein EControlUnavailableError-Erbe)
# =============================================================================


class TestLeerVertrag:
    def test_leerer_vergleich_ist_ok(self):
        cmp = _vergleich([])
        assert cmp.alternativen == []
        assert cmp.bester_gesamt is None
        assert cmp.max_ersparnis_eur == 0.0

    def test_capability_leer_ist_ok_nicht_error(self):
        cap = TariffCompareCapability(
            tariff_source=FakeTariffSource([]), spot_source=FakeSpotPriceSource(),
        )
        result = cap.run(
            plz="1060", jahresverbrauch_kwh=3500, aktueller_lieferant="Alt",
            aktueller_energiepreis_brutto_ct_kwh=30.0,
            aktuelle_grundgebuehr_brutto_eur_monat=6.0,
        )
        assert result.ok is True
        assert result.data["alternativen"] == []
        assert "leeres" in result.data["hinweis"]


# =============================================================================
# 3. B.2 Abdeckungs-Output-Block
# =============================================================================


class TestAbdeckungsBlock:
    def test_block_vorhanden_mit_drei_listen(self):
        cmp = _vergleich([_fix("a", "aWATTar", "HOURLY Fix", 10.0)], plz="2103")
        block = cmp.versorger_abdeckung
        assert block is not None
        assert block.verfuegbar  # bundesweite Anbieter sind immer da
        # NÖ: Landesversorger anderer Bundesländer sind ausgeschlossen (z.B. TIWAG)
        assert any("TIWAG" in e.brand for e in block.nicht_verfuegbar)
        # Nur 1 Katalog-Lieferant → fast alle verfügbaren fehlen im Katalog
        assert block.im_katalog_fehlend
        assert "aWATTar" not in block.im_katalog_fehlend

    def test_kein_block_fuer_gas(self):
        cmp = _vergleich(
            [{**_fix("g", "Gas AG", "Fix G", 10.0), "energy_type": "GAS"}],
            plz="1010", energy_type="GAS",
        )
        assert cmp.versorger_abdeckung is None

    def test_block_im_capability_result(self):
        cap = TariffCompareCapability(
            tariff_source=FakeTariffSource([_fix("a", "aWATTar", "Fix", 10.0)]),
            spot_source=FakeSpotPriceSource(),
        )
        result = cap.run(
            plz="1060", jahresverbrauch_kwh=3500, aktueller_lieferant="Alt",
            aktueller_energiepreis_brutto_ct_kwh=30.0,
            aktuelle_grundgebuehr_brutto_eur_monat=6.0,
        )
        assert result.ok
        block = result.data["versorger_abdeckung"]
        assert set(block) == {"verfuegbar", "nicht_verfuegbar", "im_katalog_fehlend"}


# =============================================================================
# 4. B.3 Rechenweg: kompakt per Default, voll on demand; Result-Größe < 150k
# =============================================================================


def _viele_rows(n: int) -> list[dict]:
    return [
        _fix(
            f"anbieter_{i}", f"Anbieter {i} Energie GmbH", f"Fix Tarif {i} 2026",
            8.0 + (i % 40) * 0.5, gg_netto=2.0 + (i % 10) * 0.5,
            neukundenrabatt_eur=float(i % 4) * 25.0,
            wechsel_link=f"https://beispiel-anbieter-{i}.at/tarife/fix-{i}",
        )
        for i in range(n)
    ]


class TestRechenwegUndGroesse:
    def _cap(self, n: int = 80) -> TariffCompareCapability:
        return TariffCompareCapability(
            tariff_source=FakeTariffSource(_viele_rows(n)),
            spot_source=FakeSpotPriceSource(),
        )

    _ARGS = dict(
        plz="1060", jahresverbrauch_kwh=3500, aktueller_lieferant="Alt",
        aktueller_energiepreis_brutto_ct_kwh=30.0,
        aktuelle_grundgebuehr_brutto_eur_monat=6.0,
    )

    def test_default_kompakt_mit_kurzform(self):
        result = self._cap().run(**self._ARGS)
        assert result.ok
        assert result.data["anzahl_im_result"] == 10  # Top-N-Default
        assert result.data["anzahl_alternativen_gesamt"] > 10
        for alt in result.data["alternativen"]:
            assert alt["rechenweg_kurz"]  # Kurzform immer dabei (No-LLM-Math)
            assert "rechenweg" not in alt  # voller Rechenweg nur on demand

    def test_voller_rechenweg_on_demand_fuer_alle(self):
        result = self._cap().run(**self._ARGS, rechenweg="voll", top_n=100)
        assert result.ok
        assert result.data["anzahl_im_result"] == result.data["anzahl_alternativen_gesamt"]
        for alt in result.data["alternativen"]:
            assert "rechenweg" in alt
            rw = alt["rechenweg"]
            # Kette schließt: netto_nach_rabatt + USt = brutto (auditierbar)
            kette = (rw["netto_nach_rabatt_eur"] + rw["ust_eur"]) - rw["brutto_jahreskosten_eur"]
            assert abs(kette) < 0.05

    def test_result_groesse_unter_150k(self):
        """B.3-Abnahme: Default-Result bleibt weit unter dem ~150k-Zeichen-Limit."""
        result = self._cap(80).run(**self._ARGS)
        default_chars = len(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
        assert default_chars < 150_000, f"Default-Result: {default_chars} Zeichen"
        # Auch der Voll-Abruf (alle Alternativen, voller Rechenweg) bleibt unter dem Limit.
        voll = self._cap(80).run(**self._ARGS, rechenweg="voll", top_n=100)
        voll_chars = len(json.dumps(voll.model_dump(mode="json"), ensure_ascii=False))
        assert voll_chars < 150_000, f"Voll-Result: {voll_chars} Zeichen"
        # Kompakt ist deutlich kleiner als voll (der Sinn des Defaults).
        assert default_chars < voll_chars / 2

    def test_result_ist_stdlib_json_serialisierbar(self):
        result = self._cap().run(**self._ARGS)
        json.dumps(result.model_dump(mode="json"))  # darf nicht werfen


# =============================================================================
# 5. B.6 meta-Befüllung + Input-Validierung der Hülle
# =============================================================================


class TestCapabilityEnvelope:
    def test_meta_traegt_quelle(self):
        cap = TariffCompareCapability(
            tariff_source=FakeTariffSource([]), spot_source=FakeSpotPriceSource(),
        )
        result = cap.run(
            plz="1060", jahresverbrauch_kwh=3500, aktueller_lieferant="Alt",
            aktueller_energiepreis_brutto_ct_kwh=30.0,
            aktuelle_grundgebuehr_brutto_eur_monat=6.0,
        )
        assert result.meta.get("quelle")

    def test_default_katalog_meta_hat_stand_und_version(self):
        result = TariffCompareCapability().run(
            plz="1060", jahresverbrauch_kwh=3500, aktueller_lieferant="Alt",
            aktueller_energiepreis_brutto_ct_kwh=30.0,
            aktuelle_grundgebuehr_brutto_eur_monat=6.0,
        )
        assert result.ok
        assert result.meta.get("stand")
        assert result.meta.get("snapshot_version")
        assert "katalog" in result.meta.get("quelle", "")

    @pytest.mark.parametrize("kwargs, fragment", [
        ({"plz": "abc"}, "plz"),
        ({"jahresverbrauch_kwh": 0}, "jahresverbrauch"),
        ({"aktueller_lieferant": ""}, "lieferant"),
        ({"top_n": 0}, "top_n"),
        ({"rechenweg": "episch"}, "rechenweg"),
    ])
    def test_input_validierung(self, kwargs, fragment):
        base = dict(
            plz="1060", jahresverbrauch_kwh=3500, aktueller_lieferant="Alt",
            aktueller_energiepreis_brutto_ct_kwh=30.0,
            aktuelle_grundgebuehr_brutto_eur_monat=6.0,
        )
        base.update(kwargs)
        cap = TariffCompareCapability(
            tariff_source=FakeTariffSource([]), spot_source=FakeSpotPriceSource(),
        )
        result = cap.run(**base)
        assert result.ok is False
        assert fragment in result.error


# =============================================================================
# 6. Herkunfts-Kennung der Alternativen-Tarife (``Tariff.quelle``)
# =============================================================================


class TestQuelleAbleitung:
    """Keine hartkodierte, gridbert-spezifische "scraper"-Annahme mehr für
    injizierte Fremd-Quellen: Katalog bleibt "katalog", eine injizierte
    Quelle mit ``meta["quelle"]`` liefert diese Kennung, sonst neutral
    "extern"."""

    def test_katalog_bleibt_katalog(self):
        cap = TariffCompareCapability()
        assert cap._quelle_fuer_alternativen() == "katalog"

    def test_injizierte_quelle_ohne_meta_wird_extern(self):
        cap = TariffCompareCapability(
            tariff_source=FakeTariffSource([]), spot_source=FakeSpotPriceSource(),
        )
        assert cap._quelle_fuer_alternativen() == "extern"

    def test_injizierte_quelle_mit_meta_quelle_wird_uebernommen(self):
        class FakeSourceMitMeta(FakeTariffSource):
            @property
            def meta(self) -> dict[str, str]:
                return {"quelle": "eigene-tarifdb"}

        cap = TariffCompareCapability(
            tariff_source=FakeSourceMitMeta([]), spot_source=FakeSpotPriceSource(),
        )
        assert cap._quelle_fuer_alternativen() == "eigene-tarifdb"
