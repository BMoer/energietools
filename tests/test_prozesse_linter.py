# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Struktur-Linter-Tests (D7 Testbarkeit, WP-P 2).

Der zentrale Beweis dieses Moduls: ein absichtlich kaputtes Tool-Mapping
(nicht existente Capability, egal ob energietools oder extern) MUSS vom
Linter als Fehler erkannt werden — sonst wäre der Struktur-Linter nur
Kosmetik.
"""

from __future__ import annotations

from datetime import date

from energietools.prozesse.linter import lint_alle, lint_prozess, pruefe_manifest_konsistenz
from energietools.prozesse.models import Caveat, Prozess, ProzessMeta, ToolMappingSchritt

_STAND = date(2026, 7, 11)


def _prozess(tool_mapping, *, benoetigte_daten=None) -> Prozess:
    return Prozess(
        meta=ProzessMeta(id="kaputter_test", prozess_version="1.0.0", stand=_STAND),
        ziel="Test.",
        benoetigte_daten=benoetigte_daten or [],
        tool_mapping=tool_mapping,
        caveats=[Caveat(trigger="immer", text="Test.")],
    )


class TestEchteProzesse:
    """Beide realen v1-Prozesse müssen sauber gegen die echte Registry linten."""

    def test_beide_prozesse_lint_fehlerfrei(self):
        ergebnis = lint_alle()
        assert set(ergebnis) == {"erstkontakt.yaml", "rechnungsanalyse.yaml"}
        for datei, fehler in ergebnis.items():
            assert fehler == [], f"{datei}: {fehler}"

    def test_manifest_konsistent_mit_meta_bloecken(self):
        assert pruefe_manifest_konsistenz() == []


class TestKaputtesMapping:
    """Der Delete-Evidence-artige Beweis: absichtlich kaputte Mappings → Fehler."""

    def test_unbekannte_energietools_capability_wird_erkannt(self):
        schritt = ToolMappingSchritt(
            schritt="s1", capability="tariff_compare_TYPO", quelle="energietools",
        )
        fehler = lint_prozess(_prozess([schritt]))
        assert len(fehler) == 1
        assert fehler[0].regel == "tool_mapping.existenz"
        assert "tariff_compare_TYPO" in fehler[0].meldung

    def test_unbekanntes_externes_tool_wird_erkannt(self):
        schritt = ToolMappingSchritt(schritt="s1", capability="search_pages_TYPO", quelle="extern")
        fehler = lint_prozess(_prozess([schritt]))
        assert len(fehler) == 1
        assert fehler[0].regel == "tool_mapping.extern_unbekannt"

    def test_echte_externe_tools_werden_akzeptiert(self):
        schritt = ToolMappingSchritt(schritt="s1", capability="search_pages", quelle="extern")
        fehler = lint_prozess(_prozess([schritt]))
        assert fehler == []

    def test_fehlende_pflicht_input_deckung_wird_erkannt(self):
        schritt = ToolMappingSchritt(
            schritt="vergleich", capability="tariff_compare", quelle="energietools",
        )
        fehler = lint_prozess(_prozess([schritt], benoetigte_daten=[]))
        assert any(f.regel == "tool_mapping.pflicht_inputs" for f in fehler)

    def test_gedeckte_pflicht_inputs_erzeugen_keinen_fehler(self):
        benoetigt = [
            {"feld": f, "quelle": "rechnung", "pflicht": True}
            for f in (
                "plz", "jahresverbrauch_kwh", "aktueller_lieferant",
                "aktueller_energiepreis_brutto_ct_kwh", "aktuelle_grundgebuehr_brutto_eur_monat",
            )
        ]
        schritt = ToolMappingSchritt(
            schritt="vergleich", capability="tariff_compare", quelle="energietools",
        )
        fehler = lint_prozess(_prozess([schritt], benoetigte_daten=benoetigt))
        assert fehler == []

    def test_ausblick_schritt_braucht_keine_pflicht_input_deckung(self):
        fehler = lint_prozess(
            _prozess(
                [
                    ToolMappingSchritt(
                        schritt="ausblick", capability="tariff_compare",
                        quelle="energietools", rolle="ausblick",
                    ),
                ],
                benoetigte_daten=[],
            ),
        )
        assert fehler == []

    def test_nicht_benutzerdaten_nimmt_feld_von_deckungspruefung_aus(self):
        fehler = lint_prozess(
            _prozess(
                [
                    ToolMappingSchritt(
                        schritt="wissen", capability="get_knowledge", quelle="energietools",
                        nicht_benutzerdaten=["thema"],
                    ),
                ],
                benoetigte_daten=[],
            ),
        )
        assert fehler == []

    def test_leerer_tool_mapping_block_wird_als_pflichtblock_fehler_erkannt(self):
        # Pydantic verhindert das normalerweise (min_length=1) — model_construct
        # umgeht die Validierung, damit der Linter defensiv selbst geprüft wird.
        prozess = Prozess.model_construct(
            meta=ProzessMeta(id="x", prozess_version="1.0.0", stand=_STAND),
            ziel="Test.",
            benoetigte_daten=[],
            fragen=[],
            tool_mapping=[],
            datenqualitaet_abbruch=[],
            caveats=[Caveat(trigger="immer", text="Test.")],
        )
        fehler = lint_prozess(prozess)
        assert any(f.regel == "pflichtblock" and "tool_mapping" in f.meldung for f in fehler)
