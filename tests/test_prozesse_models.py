# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für das Prozess-Format (D7): sieben Blöcke, SemVer, Pflichtblöcke."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from energietools.prozesse.models import (
    Caveat,
    Prozess,
    ProzessMeta,
    SignalPraezedenz,
    ToolMappingSchritt,
)

_STAND = date(2026, 7, 11)


class TestSemVer:
    @pytest.mark.parametrize("version", ["1.0.0", "0.1.0", "10.20.30"])
    def test_gueltige_semver_wird_akzeptiert(self, version):
        ProzessMeta(id="x", prozess_version=version, stand=_STAND)

    @pytest.mark.parametrize("version", ["1.0", "v1.0.0", "1.0.0-beta", "1", "latest", ""])
    def test_ungueltige_semver_wirft(self, version):
        with pytest.raises(ValidationError):
            ProzessMeta(id="x", prozess_version=version, stand=_STAND)


class TestPflichtbloecke:
    def test_tool_mapping_darf_nicht_leer_sein(self):
        with pytest.raises(ValidationError):
            Prozess(
                meta=ProzessMeta(id="x", prozess_version="1.0.0", stand=_STAND),
                ziel="Test.",
                tool_mapping=[],
                caveats=[Caveat(trigger="immer", text="Test.")],
            )

    def test_caveats_duerfen_nicht_leer_sein(self):
        with pytest.raises(ValidationError):
            Prozess(
                meta=ProzessMeta(id="x", prozess_version="1.0.0", stand=_STAND),
                ziel="Test.",
                tool_mapping=[ToolMappingSchritt(schritt="s1", capability="tariff_compare")],
                caveats=[],
            )

    def test_unbekannter_top_level_block_wird_abgelehnt(self):
        with pytest.raises(ValidationError):
            Prozess(
                meta=ProzessMeta(id="x", prozess_version="1.0.0", stand=_STAND),
                ziel="Test.",
                tool_mapping=[ToolMappingSchritt(schritt="s1", capability="tariff_compare")],
                caveats=[Caveat(trigger="immer", text="Test.")],
                unbekannter_block="darf nicht durchgehen",
            )

    def test_benoetigte_daten_und_fragen_duerfen_leer_sein(self):
        # Amendment 9: der Erstkontakt-Prozess hat bewusst leere benoetigte_daten/fragen.
        prozess = Prozess(
            meta=ProzessMeta(id="x", prozess_version="1.0.0", stand=_STAND),
            ziel="Test.",
            benoetigte_daten=[],
            fragen=[],
            tool_mapping=[ToolMappingSchritt(schritt="s1", capability="tariff_compare")],
            caveats=[Caveat(trigger="immer", text="Test.")],
        )
        assert prozess.benoetigte_daten == []
        assert prozess.fragen == []


class TestSignaleBlock:
    """Optionaler Block ``signale`` (Fakt-vor-Heuristik-Deklaration, nach ``fragen``)."""

    def test_signale_block_wird_geparst_und_extra_key_abgelehnt(self):
        prozess = Prozess(
            meta=ProzessMeta(id="x", prozess_version="1.0.0", stand=_STAND),
            ziel="Test.",
            tool_mapping=[ToolMappingSchritt(schritt="s1", capability="tariff_compare")],
            caveats=[Caveat(trigger="immer", text="Test.")],
            signale={
                "electric_heating": {"fakt": "asset.heating.type", "rolle": "heuristik_fuer"},
            },
        )
        assert prozess.signale["electric_heating"].fakt == "asset.heating.type"
        assert prozess.signale["electric_heating"].rolle == "heuristik_fuer"

        with pytest.raises(ValidationError):
            SignalPraezedenz(
                fakt="asset.heating.type", rolle="heuristik_fuer", unbekannter_key="x"
            )

    def test_signale_default_ist_leeres_dict(self):
        prozess = Prozess(
            meta=ProzessMeta(id="x", prozess_version="1.0.0", stand=_STAND),
            ziel="Test.",
            tool_mapping=[ToolMappingSchritt(schritt="s1", capability="tariff_compare")],
            caveats=[Caveat(trigger="immer", text="Test.")],
        )
        assert prozess.signale == {}

    def test_signale_eintrag_lehnt_falsche_rolle_ab(self):
        with pytest.raises(ValidationError):
            SignalPraezedenz(fakt="asset.heating.type", rolle="falsche_rolle")


class TestGedeckteFelder:
    def test_vereinigt_benoetigte_daten_und_frage_felder(self):
        prozess = Prozess(
            meta=ProzessMeta(id="x", prozess_version="1.0.0", stand=_STAND),
            ziel="Test.",
            benoetigte_daten=[
                {"feld": "plz", "quelle": "rechnung", "pflicht": True},
            ],
            fragen=[
                {"id": "f1", "hebel": "tarif", "text": "?", "feld": "praeferenz"},
                {"id": "f2", "hebel": "tarif", "text": "?"},  # kein feld -> nicht gedeckt
            ],
            tool_mapping=[ToolMappingSchritt(schritt="s1", capability="tariff_compare")],
            caveats=[Caveat(trigger="immer", text="Test.")],
        )
        assert prozess.gedeckte_felder == {"plz", "praeferenz"}
