# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Renderer-Tests + Drift-Guard gegen die committeten ``skills/``-Artefakte (D7).

Der Drift-Guard rendert live aus den ``prozesse/*.yaml``-Quellen und
vergleicht gegen die committeten ``skills/gridbert-<id>/SKILL.md``-Dateien —
weichen sie ab, ist der Build-Schritt (``python -m energietools.prozesse.
renderer skills``) nicht erneut gelaufen.
"""

from __future__ import annotations

from pathlib import Path

from energietools.prozesse.loader import load_prozess, manifest_dateien
from energietools.prozesse.renderer import render_instructions_block, render_kurzform, render_skill

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestRenderSkill:
    def test_enthaelt_frontmatter_und_alle_bloecke(self):
        prozess = load_prozess("erstkontakt.yaml")
        skill = render_skill(prozess)
        assert skill.startswith("---\nname: gridbert-erstkontakt")
        for ueberschrift in (
            "## Ziel",
            "## Benötigte Daten",
            "## Fragen",
            "## Tool-Mapping",
            "## Datenqualität & Abbruch",
            "## Caveats (MÜSSEN in die Antwort)",
        ):
            assert ueberschrift in skill

    def test_alle_caveats_erscheinen_im_skill(self):
        prozess = load_prozess("rechnungsanalyse.yaml")
        skill = render_skill(prozess)
        for caveat in prozess.caveats:
            assert caveat.trigger in skill


class TestRenderKurzform:
    def test_enthaelt_id_und_version(self):
        prozess = load_prozess("erstkontakt.yaml")
        kurz = render_kurzform(prozess)
        assert "erstkontakt" in kurz
        assert "1.0.0" in kurz

    def test_instructions_block_nennt_get_knowledge_und_alle_prozesse(self):
        prozesse = [load_prozess(d) for d in manifest_dateien()]
        block = render_instructions_block(prozesse)
        assert "get_knowledge" in block
        for p in prozesse:
            assert p.meta.id in block


class TestSkillDriftGuard:
    def test_gerenderte_skills_stimmen_mit_committeten_dateien_ueberein(self):
        for datei in manifest_dateien():
            prozess = load_prozess(datei)
            erwartet = render_skill(prozess) + "\n"
            pfad = REPO_ROOT / "skills" / f"gridbert-{prozess.meta.id}" / "SKILL.md"
            assert pfad.exists(), f"{pfad} fehlt — Renderer erneut laufen lassen"
            assert pfad.read_text(encoding="utf-8") == erwartet, (
                f"{pfad} ist veraltet gegenüber {datei} — Renderer erneut laufen lassen"
            )

    def test_instructions_kurzform_stimmt_ueberein(self):
        prozesse = [load_prozess(d) for d in manifest_dateien()]
        erwartet = render_instructions_block(prozesse) + "\n"
        pfad = REPO_ROOT / "skills" / "_instructions_kurzform.md"
        assert pfad.exists()
        assert pfad.read_text(encoding="utf-8") == erwartet
