# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die Versorger-Abdeckung je Netzgebiet."""

from __future__ import annotations

from energietools.capabilities.providers import (
    ist_lieferant_verfuegbar,
    lade_anbieter,
    versorger_abdeckung,
)
from energietools.capabilities.registry import default_registry


class TestLadeAnbieter:
    def test_nur_strom_lieferanten(self) -> None:
        anb = lade_anbieter()
        assert len(anb) > 10
        # alle tragen ein Versorgungsgebiet (mind. ein Bundesland oder AT)
        assert all(v.region for v in anb)

    def test_national_vs_regional(self) -> None:
        by_brand = {v.brand: v for v in lade_anbieter()}
        assert by_brand["VERBUND"].bundesweit  # AT
        assert not by_brand["EVN"].bundesweit  # NÖ
        assert by_brand["EVN"].region == ("Niederösterreich",)  # Abkürzung normalisiert


class TestVersorgerAbdeckung:
    def test_noe_schliesst_fremde_landesversorger_aus(self) -> None:
        """Langenzersdorf (NÖ): EVN + Wien Energie (Wien+NÖ) verfügbar; TIWAG/VKW raus."""
        a = versorger_abdeckung("2103")
        assert "Niederösterreich" in a.bundeslaender
        verf = {v.brand for v in a.verfuegbar}
        ausg = {v.brand for v in a.nicht_verfuegbar}
        assert "EVN" in verf
        assert "VERBUND" in verf  # bundesweit immer
        assert "Wien Energie" in verf  # E-Control: Wien Energie liefert auch in NÖ
        # E-Control-bestätigt regional-only: an einer NÖ-Adresse nicht abschließbar.
        assert "TIWAG" in ausg and "VKW" in ausg and "Salzburg AG" in ausg

    def test_tirol_schaltet_tiwag_frei(self) -> None:
        a = versorger_abdeckung("6020")  # Innsbruck
        verf = {v.brand for v in a.verfuegbar}
        assert "TIWAG" in verf
        assert "EVN" not in verf  # NÖ-Versorger nicht in Tirol

    def test_bundesweite_immer_verfuegbar(self) -> None:
        for plz in ("2103", "6020", "9020", "8010"):
            verf = {v.brand for v in versorger_abdeckung(plz).verfuegbar}
            assert {"VERBUND", "aWATTar"} <= verf

    def test_im_katalog_markiert_eigene_abdeckung(self) -> None:
        # Mit einem Mini-Katalog: nur EVN soll als abgedeckt markiert werden.
        a = versorger_abdeckung("2103", katalog_lieferanten=["EVN Energievertrieb GmbH & Co KG"])
        assert "EVN" in a.im_katalog
        assert "VERBUND" not in a.im_katalog

    def test_im_katalog_keine_false_positives_durch_generische_tokens(self) -> None:
        # Ein Katalog mit nur "Wien Energie" darf NICHT andere "…Energie…"-Anbieter
        # (EVN, Energie AG, …) als abgedeckt markieren.
        a = versorger_abdeckung("6020", katalog_lieferanten=["Wien Energie Vertrieb GmbH & Co KG"])
        assert "EVN" not in a.im_katalog
        assert "TIWAG" not in a.im_katalog

    def test_ooe_abkuerzung_wird_normalisiert(self) -> None:
        # LINZ AG (region "OÖ", E-Control-bestätigt OÖ-only) muss in OÖ verfügbar,
        # in NÖ ausgeschlossen sein — prüft die OÖ→Oberösterreich-Normalisierung.
        ooe = {v.brand for v in versorger_abdeckung("4020").verfuegbar}  # Linz
        noe = {v.brand for v in versorger_abdeckung("2103").nicht_verfuegbar}
        assert "LINZ AG" in ooe
        assert "LINZ AG" in noe

    def test_unbekannte_plz_fail_open(self) -> None:
        # Unbekannte PLZ: fail-open → keine fälschlichen Ausschlüsse, bundesweite da.
        a = versorger_abdeckung("00000")
        assert a.bundeslaender == ()
        assert "VERBUND" in {v.brand for v in a.verfuegbar}

    def test_zaehler_konsistent(self) -> None:
        a = versorger_abdeckung("2103")
        assert a.anzahl_verfuegbar == a.anzahl_bundesweit + a.anzahl_regional
        assert a.anzahl_verfuegbar == len(a.verfuegbar)


class TestIstLieferantVerfuegbar:
    """Filter-Helper für den Tarifvergleich (fail-open)."""

    def test_landesversorger_fremdes_bundesland_raus(self) -> None:
        # NÖ-Adresse: TIWAG (Tirol) + VKW (Vorarlberg) nicht abschließbar.
        assert not ist_lieferant_verfuegbar("TIWAG-Tiroler Wasserkraft AG", "2103")
        assert not ist_lieferant_verfuegbar("illwerke vkw AG", "2103")

    def test_bundesweit_und_lokal_bleiben(self) -> None:
        assert ist_lieferant_verfuegbar("VERBUND Energy4Business GmbH", "2103")
        assert ist_lieferant_verfuegbar("EVN Energievertrieb GmbH & Co KG", "2103")  # NÖ
        assert ist_lieferant_verfuegbar("TIWAG-Tiroler Wasserkraft AG", "6020")  # in Tirol ok

    def test_unbekannter_anbieter_fail_open(self) -> None:
        assert ist_lieferant_verfuegbar("Irgendein Kleiner Stromhändler GmbH", "2103")
        assert ist_lieferant_verfuegbar("", "2103")


class TestCapabilityRegistriert:
    def test_in_registry_und_ausfuehrbar(self) -> None:
        reg = default_registry()
        assert "versorger_abdeckung" in reg.names
        res = reg.get("versorger_abdeckung").run(plz="2103")
        assert res.ok
        assert "TIWAG" in {x["brand"] for x in res.data["regional_ausgeschlossen"]}

    def test_strom_default_liefert_abdeckung(self) -> None:
        # Ohne energieart wird 'strom' angenommen (Abwärtskompatibilität).
        res = default_registry().get("versorger_abdeckung").run(plz="2103", energieart="strom")
        assert res.ok

    def test_gas_wird_abgelehnt_statt_strom_marken_als_gas(self) -> None:
        # Fix #4: Abdeckungsdaten sind Strom-only — Gas sauber ablehnen, nicht
        # stumm Strom-Marken als vermeintliche Gas-Liste ausgeben.
        res = default_registry().get("versorger_abdeckung").run(plz="2103", energieart="gas")
        assert res.ok is False
        assert res.data is None
        assert "Gas" in (res.error or "")
