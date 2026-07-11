# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die anonymisierten Beispiel-Dialoge (D7 Testbarkeit, WP-P 2)."""

from __future__ import annotations

from energietools.prozesse.beispiel_check import pruefe_beispiel
from energietools.prozesse.caveats import aktive_caveats
from energietools.prozesse.loader import list_beispiele, load_beispiel, load_prozess
from energietools.prozesse.models import Caveat


def test_aktive_caveats_ueberspringt_kaputten_trigger_ohne_alle_zu_verlieren():
    """Fund 9 (Runtime-Guard): ein Trigger, der zur Laufzeit wirft (z.B. '>' auf
    einer Liste), darf nicht alle Caveats — inkl. des Pflicht-'immer' — kippen."""
    caveats = [Caveat(trigger="immer", text="A"), Caveat(trigger="x.y > 0", text="B")]
    aktiv = aktive_caveats(caveats, {"x": {"y": ["a", "b"]}})
    assert [c.text for c in aktiv] == ["A"]


class TestBeispielDialoge:
    def test_es_gibt_einen_beispiel_dialog_je_v1_prozess(self):
        beispiele = [load_beispiel(d) for d in list_beispiele()]
        assert {b["prozess_id"] for b in beispiele} == {"erstkontakt", "rechnungsanalyse"}

    def test_alle_beispiele_stimmen_mit_ihrem_prozess_ueberein(self):
        for datei in list_beispiele():
            beispiel = load_beispiel(datei)
            prozess = load_prozess(beispiel["prozess_datei"])
            fehler = pruefe_beispiel(beispiel, prozess)
            assert fehler == [], f"{datei}: {fehler}"

    def test_erstkontakt_beispiel_hat_keine_pflichtfragen(self):
        beispiel = load_beispiel("erstkontakt_was_kann_gridbert.json")
        assert beispiel["erwartete_frage_ids"] == []
        assert len(beispiel["erwartete_tool_calls"]) >= 1

    def test_rechnungsanalyse_beispiel_ruft_validate_finalize_compare_in_reihenfolge(self):
        beispiel = load_beispiel("rechnungsanalyse_tarifvergleich.json")
        capabilities = [c["capability"] for c in beispiel["erwartete_tool_calls"]]
        assert capabilities == ["validate_invoice_facts", "finalize_invoice", "tariff_compare"]

    def test_kaputtes_beispiel_wird_vom_checker_erkannt(self):
        prozess = load_prozess("erstkontakt.yaml")
        kaputt = {
            "prozess_id": "erstkontakt",
            "erwartete_frage_ids": ["nicht_existent"],
            "erwartete_tool_calls": [
                {"schritt": "nicht_existent", "capability": "x", "quelle": "extern"},
            ],
            "erwartete_caveats_trigger": ["nie_ausloesend"],
        }
        fehler = pruefe_beispiel(kaputt, prozess)
        assert len(fehler) >= 3
