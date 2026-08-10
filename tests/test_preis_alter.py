# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Preis-Alter: wann wurde ein Katalogpreis zuletzt BESTÄTIGT?

Der Katalog trägt seit 10.08.2026 je Tarif ein ``zuletzt_bestaetigt``-Datum.
Es beantwortet eine andere Frage als ``gueltig_ab``: nicht „seit wann gilt
dieser Preis", sondern „wann konnte er zuletzt an der Quelle nachgeprüft
werden".

Der Unterschied ist keine Feinheit. Ein Anbieter, dessen Preisblatt seit Wochen
nicht mehr erreichbar ist, behält seinen alten Preis unverändert im Katalog —
er sieht dort genauso gültig aus wie ein täglich bestätigter. Genau das ist im
August 2026 passiert (ein Anbieter lieferte elf Tage lang 404, ohne dass es im
Katalog auffiel).

**Gekennzeichnet, nicht ausgeblendet:** ein Tarif mit altem Bestätigungsdatum
bleibt im Vergleich und trägt sein Datum sichtbar. Ihn zu entfernen hieße, ein
real existierendes Angebot zu verschweigen.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from energietools.capabilities.tariffs.models import PREIS_MAX_ALTER_TAGE, CatalogTariff


def _tarif(zuletzt: str = "") -> CatalogTariff:
    return CatalogTariff(
        key="test", lieferant="Test GmbH", tarif_name="Testtarif",
        energiepreis_ct_kwh=15.0, grundgebuehr_eur_monat=3.0,
        zuletzt_bestaetigt=zuletzt,
    )


def _vor(tagen: int) -> str:
    return (date.today() - timedelta(days=tagen)).isoformat()


class TestPreisAlterTage:
    def test_heute_bestaetigt_ist_null_tage(self):
        assert _tarif(_vor(0)).preis_alter_tage() == 0

    def test_zaehlt_kalendertage(self):
        assert _tarif(_vor(9)).preis_alter_tage() == 9

    def test_ohne_datum_ist_es_unbekannt(self):
        """Ältere Katalog-Snapshots tragen das Feld nicht — das ist kein Alter."""
        assert _tarif().preis_alter_tage() is None

    def test_unlesbares_datum_ist_unbekannt_statt_absturz(self):
        """Ein kaputter Wert im Katalog darf keinen Vergleich sprengen."""
        assert _tarif("kein-datum").preis_alter_tage() is None

    def test_datum_mit_uhrzeit_wird_akzeptiert(self):
        """Der Exporter liefert ISO-Zeitstempel, nicht nur Datumsteile."""
        stempel = f"{_vor(3)}T04:12:33"
        assert _tarif(stempel).preis_alter_tage() == 3

    def test_zukunftsdatum_zaehlt_nicht_negativ(self):
        assert _tarif(_vor(-5)).preis_alter_tage() == 0


class TestPreisVeraltet:
    @pytest.mark.parametrize("tage,erwartet", [(0, False), (13, False), (14, False), (15, True)])
    def test_die_grenze_liegt_bei_14_tagen(self, tage, erwartet):
        assert _tarif(_vor(tage)).preis_veraltet is erwartet

    def test_ohne_datum_gilt_der_preis_nicht_als_veraltet(self):
        """„Nie gemessen" ist keine Aussage über das Alter — und ein Hinweis,
        der auf jeden Tarif eines alten Snapshots zutrifft, ist wertlos."""
        assert _tarif().preis_veraltet is False

    def test_die_grenze_ist_eine_benannte_konstante(self):
        assert PREIS_MAX_ALTER_TAGE == 14


class TestImVergleichsergebnis:
    """Der Punkt, an dem ein Kunde es sieht.

    Ohne diesen Schritt bliebe die Kennzeichnung im Open-Data-Katalog stecken:
    ``CatalogTariffSource`` reicht zwar alle Modellfelder weiter, aber
    ``compare`` baut sein Ergebnis-``Tariff`` feldweise auf.
    """

    def _vergleich(self, zuletzt: str):
        from energietools.capabilities.tariff_compare import vergleiche_tarife

        class _Quelle:
            """Minimale TariffSource mit genau einem Tarif."""

            def get_latest(self, *, status: str, energy_type: str) -> list[dict]:
                eintrag = {
                    "key": "test", "lieferant": "Test GmbH", "tarif_name": "Testtarif",
                    "energiepreis_ct_kwh": 15.0, "grundgebuehr_eur_monat": 3.0,
                    "energy_type": "POWER",
                }
                if zuletzt:
                    eintrag["zuletzt_bestaetigt"] = zuletzt
                return [eintrag]

            @property
            def meta(self) -> dict:
                return {"quelle": "test"}

        return vergleiche_tarife(
            plz="1010",
            jahresverbrauch_kwh=3500,
            aktueller_lieferant="Alt AG",
            aktueller_energiepreis_brutto_ct_kwh=25.0,
            aktuelle_grundgebuehr_brutto_eur_monat=10.0,
            tariff_source=_Quelle(),
            mit_abdeckung=False,
        )

    def test_das_ergebnis_traegt_das_bestaetigungsdatum(self):
        stand = _vor(20)
        gefunden = self._vergleich(stand).alternativen[0]

        assert gefunden.zuletzt_bestaetigt == stand
        assert gefunden.preis_veraltet is True
        assert gefunden.preis_alter_tage() == 20

    def test_ein_frischer_tarif_traegt_keinen_hinweis(self):
        assert self._vergleich(_vor(1)).alternativen[0].preis_veraltet is False

    def test_ein_tarif_ohne_datum_bleibt_im_vergleich(self):
        """Bestandsdaten duerfen nicht aus dem Vergleich fallen."""
        ergebnis = self._vergleich("")

        assert len(ergebnis.alternativen) == 1
        assert ergebnis.alternativen[0].preis_veraltet is False
