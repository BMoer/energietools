# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die get_knowledge-Capability (D7 Wissens-Auslieferung, Amendment 9)."""

from __future__ import annotations

import json

import pytest

from energietools.capabilities.knowledge.pages import (
    WikiPageNotFoundError,
    extract_stand,
    find_page,
    load_wiki_pages,
    read_page_text,
)
from energietools.capabilities.registry import default_registry


class TestWikiPages:
    def test_laedt_alle_seiten_aus_llms_txt(self):
        thema_slugs = {p.thema for p in load_wiki_pages()}
        assert "stromkosten-zusammensetzung" in thema_slugs  # Amendment-9-Pflichtthema
        assert "netz-netzentgelte" in thema_slugs
        assert "glossar" in thema_slugs
        assert "markt" in thema_slugs

    def test_jede_seite_ist_lesbar_und_nicht_leer(self):
        for page in load_wiki_pages():
            assert read_page_text(page).strip(), page.relpath

    def test_unbekanntes_thema_wirft(self):
        with pytest.raises(WikiPageNotFoundError):
            find_page("does-not-exist")

    def test_unbekanntes_thema_listet_verfuegbare_themen(self):
        # Ein schwaches LLM riet 'stromkosten_zusammensetzung' (Unterstrich) —
        # der Fehler MUSS die gültigen Slugs nennen, damit es umschwenken kann.
        with pytest.raises(WikiPageNotFoundError) as exc:
            find_page("stromkosten_zusammensetzung")
        msg = str(exc.value)
        assert "Verfügbare Themen" in msg
        assert "stromkosten-zusammensetzung" in msg  # korrekter Slug im Fehler sichtbar

    def test_extract_stand_liest_letzte_stand_zeile(self):
        assert extract_stand("# Titel\n\nText\n\nStand: 2026-06") == "2026-06"
        assert extract_stand("keine Stand-Zeile hier") == ""


class TestGetKnowledgeCapability:
    def test_registriert_als_get_knowledge(self):
        assert "get_knowledge" in default_registry().names

    def test_thema_enum_enthaelt_pflichtthema(self):
        cap = default_registry().get("get_knowledge")
        enum = cap.input_schema["properties"]["thema"]["enum"]
        assert "stromkosten-zusammensetzung" in enum

    def test_erfolgreicher_abruf(self):
        cap = default_registry().get("get_knowledge")
        result = cap.run(thema="stromkosten-zusammensetzung")
        assert result.ok is True
        assert result.data["inhalt"].startswith("# Wie sich der Strompreis")
        assert result.data["stand"] == "2026-06"
        assert result.data["quelle"] == "energietools wiki/stromkosten-zusammensetzung.md"
        # meta trägt dieselben Provenance-Felder (B.6-Konvention: stand/quelle im Envelope)
        assert result.meta["stand"] == result.data["stand"]
        assert result.meta["quelle"] == result.data["quelle"]

    def test_reine_textauslieferung_kein_rechen_result(self):
        # Amendment 9 / D7 harte Regel: get_knowledge liefert KEINE gerechneten
        # €-Werte — das Result trägt ausschließlich Text-/Provenance-Felder.
        cap = default_registry().get("get_knowledge")
        result = cap.run(thema="stromkosten-zusammensetzung")
        assert set(result.data.keys()) == {"thema", "titel", "inhalt", "stand", "quelle"}

    def test_unbekanntes_thema_liefert_ok_false(self):
        cap = default_registry().get("get_knowledge")
        result = cap.run(thema="nicht-vorhanden")
        assert result.ok is False
        assert "nicht-vorhanden" in result.error

    def test_fehlendes_thema_liefert_ok_false(self):
        cap = default_registry().get("get_knowledge")
        result = cap.run()
        assert result.ok is False

    def test_json_roundtrip(self):
        cap = default_registry().get("get_knowledge")
        result = cap.run(thema="glossar")
        json.dumps(result.model_dump(mode="json"))  # darf nicht werfen
