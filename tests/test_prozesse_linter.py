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

from energietools.capabilities.base import Capability, CapabilityRegistry
from energietools.capabilities.lastgang.reconcile import SIGNAL_FELD_MAPPING
from energietools.prozesse.linter import (
    lint_alle,
    lint_datei,
    lint_prozess,
    pruefe_manifest_konsistenz,
)
from energietools.prozesse.models import Caveat, Prozess, ProzessMeta, ToolMappingSchritt

_STAND = date(2026, 7, 11)


def _prozess(
    tool_mapping, *, benoetigte_daten=None, caveats=None, signale=None
) -> Prozess:
    kwargs: dict = dict(
        meta=ProzessMeta(id="kaputter_test", prozess_version="1.0.0", stand=_STAND),
        ziel="Test.",
        benoetigte_daten=benoetigte_daten or [],
        tool_mapping=tool_mapping,
        caveats=caveats or [Caveat(trigger="immer", text="Test.")],
    )
    if signale is not None:
        kwargs["signale"] = signale
    return Prozess(**kwargs)


def _lastgang_schritt(**kwargs) -> ToolMappingSchritt:
    return ToolMappingSchritt(
        schritt="ursachen_signale",
        capability="lastgang_signals",
        quelle="energietools",
        rolle="aktiv",
        nicht_benutzerdaten=["consumption"],
        **kwargs,
    )


def _signale_korrekt() -> dict:
    return {
        signal: {"fakt": fakt, "rolle": "heuristik_fuer"}
        for signal, fakt in SIGNAL_FELD_MAPPING.items()
    }


def _gedeckte_felder_fuer_signale() -> list[dict]:
    return [
        {"feld": fakt, "quelle": "rechnung|frage", "pflicht": False}
        for fakt in SIGNAL_FELD_MAPPING.values()
    ]


_TARIFF_COMPARE_BENOETIGT = [
    {"feld": f, "quelle": "rechnung", "pflicht": True}
    for f in (
        "plz", "jahresverbrauch_kwh", "aktueller_lieferant",
        "aktueller_energiepreis_brutto_ct_kwh", "aktuelle_grundgebuehr_brutto_eur_monat",
    )
]


class TestCaveatTriggerPfade:
    """Fund 9: caveat-Trigger-Feldpfade werden gegen die realen Result-Felder der
    aktiv aufgerufenen Capability gelintet — damit die 'abdeckung'-vs-
    'versorger_abdeckung'-Drift-Fehlerklasse nicht wiederkommt."""

    def _mit_caveat(self, trigger: str) -> Prozess:
        schritt = ToolMappingSchritt(
            schritt="vergleich", capability="tariff_compare", quelle="energietools",
        )
        return _prozess(
            [schritt],
            benoetigte_daten=_TARIFF_COMPARE_BENOETIGT,
            caveats=[Caveat(trigger="immer", text="A"), Caveat(trigger=trigger, text="B")],
        )

    def test_falscher_feld_namespace_wird_erkannt(self):
        fehler = lint_prozess(self._mit_caveat("abdeckung.im_katalog_fehlend > 0"))
        assert any(f.regel == "caveat.trigger_pfad" for f in fehler), fehler

    def test_realer_output_pfad_lintet_sauber(self):
        fehler = lint_prozess(
            self._mit_caveat("versorger_abdeckung.im_katalog_fehlend_anzahl > 0"),
        )
        assert fehler == [], fehler

    def test_ordnungsvergleich_auf_liste_wird_erkannt(self):
        # im_katalog_fehlend ist eine Liste — '>' darauf ist ein Typfehler (crasht sonst).
        fehler = lint_prozess(self._mit_caveat("versorger_abdeckung.im_katalog_fehlend > 0"))
        assert any(f.regel == "caveat.trigger_typ" for f in fehler), fehler


class TestSignalPraezedenzLint:
    """``signale``-Block (Fakt-vor-Heuristik-Deklaration) — Regel (f)."""

    def test_lastganganalyse_signale_lintet_fehlerfrei(self):
        fehler = lint_datei("lastganganalyse.yaml")
        assert not any(f.regel.startswith("signale.") for f in fehler), fehler

    def test_fehlende_signale_deklaration_bei_lastgang_signals_wird_erkannt(self):
        schritt = _lastgang_schritt()
        prozess = _prozess([schritt], benoetigte_daten=_gedeckte_felder_fuer_signale())

        fehler = lint_prozess(prozess)

        assert any(f.regel == "signale.fehlt" for f in fehler), fehler

    def test_praezedenz_drift_zwischen_yaml_und_code_wird_erkannt(self):
        schritt = _lastgang_schritt()
        signale_mit_drift = _signale_korrekt()
        erstes_signal = next(iter(signale_mit_drift))
        signale_mit_drift[erstes_signal] = {
            "fakt": "asset.absichtlich_falsches_feld", "rolle": "heuristik_fuer",
        }
        prozess = _prozess(
            [schritt],
            benoetigte_daten=_gedeckte_felder_fuer_signale()
            + [{"feld": "asset.absichtlich_falsches_feld", "quelle": "frage", "pflicht": False}],
            signale=signale_mit_drift,
        )

        fehler = lint_prozess(prozess)

        assert any(f.regel == "signale.praezedenz_drift" for f in fehler), fehler

    def test_signale_fakt_muss_gedecktes_feld_sein(self):
        schritt = _lastgang_schritt()
        prozess = _prozess([schritt], benoetigte_daten=[], signale=_signale_korrekt())

        fehler = lint_prozess(prozess)

        assert any(f.regel == "signale.fakt_nicht_gedeckt" for f in fehler), fehler

    def test_verwaister_signale_block_wird_erkannt(self):
        schritt = ToolMappingSchritt(
            schritt="s1", capability="tariff_compare", quelle="energietools",
        )
        prozess = _prozess(
            [schritt],
            benoetigte_daten=_TARIFF_COMPARE_BENOETIGT,
            signale=_signale_korrekt(),
        )

        fehler = lint_prozess(prozess)

        assert any(f.regel == "signale.verwaist" for f in fehler), fehler

    def test_unbekanntes_signal_bei_fehlendem_result_feld_wird_erkannt(self):
        """E4: eine Fake-Registry, deren lastgang_signals-Result-Feldpfade
        ein Signal NICHT enthalten, muss 'signale.unbekanntes_signal' auslösen —
        vorher gab es dafür keinen Test."""

        class _FakeLastgangSignalsCapability(Capability):
            name = "lastgang_signals"
            summary = "Fake für den Linter-Test: ein Signal fehlt in result_field_paths."
            input_schema = {
                "type": "object",
                "properties": {"consumption": {"type": "array"}},
                "required": ["consumption"],
            }

            def _run(self, **kwargs):  # pragma: no cover — im Linter-Test nie aufgerufen
                return {}

            def result_field_paths(self) -> dict[str, str]:
                # 'high_continuous_load' bewusst ausgelassen.
                return {
                    signal: "str"
                    for signal in SIGNAL_FELD_MAPPING
                    if signal != "high_continuous_load"
                }

        reg = CapabilityRegistry()
        reg.register(_FakeLastgangSignalsCapability())
        schritt = _lastgang_schritt()
        prozess = _prozess(
            [schritt],
            benoetigte_daten=_gedeckte_felder_fuer_signale(),
            signale=_signale_korrekt(),
        )

        fehler = lint_prozess(prozess, registry=reg)

        unbekannt = [f for f in fehler if f.regel == "signale.unbekanntes_signal"]
        assert len(unbekannt) == 1, fehler
        assert "high_continuous_load" in unbekannt[0].meldung

    def test_caveat_trigger_auf_profil_abgleich_zaehler_lintet_sauber(self):
        schritt = _lastgang_schritt()
        prozess = _prozess(
            [schritt],
            benoetigte_daten=_gedeckte_felder_fuer_signale(),
            signale=_signale_korrekt(),
            caveats=[
                Caveat(trigger="immer", text="A"),
                Caveat(trigger="profil_abgleich.anzahl_widersprueche > 0", text="B"),
            ],
        )

        fehler = lint_prozess(prozess)

        assert fehler == [], fehler


class TestEchteProzesse:
    """Alle realen v1-Prozesse müssen sauber gegen die echte Registry linten."""

    def test_beide_prozesse_lint_fehlerfrei(self):
        ergebnis = lint_alle()
        assert set(ergebnis) == {
            "erstkontakt.yaml", "rechnungsanalyse.yaml", "lastganganalyse.yaml",
        }
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
