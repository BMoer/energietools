# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Wiki-Seiten-Index für die ``get_knowledge``-Capability (D7, Amendment 9).

Spiegelt das Daten-Lade-Muster der netz-/tariffs-/providers-Snapshots
(``importlib.resources`` aus dem gebündelten Package, ``lru_cache`` für
Idempotenz, ``CapabilityError`` bei fehlenden Dateien) — nur dass hier
Markdown-Seiten statt JSON-Snapshots gelesen werden.

Der ``thema``-Enum von ``get_knowledge`` wird NICHT von Hand gepflegt, sondern
aus ``wiki/llms.txt`` geparst — demselben maschinenlesbaren Index, den auch
ein Agent nutzt, der direkt auf den Wiki-Ordner zeigt (D7 „Wissens-
Auslieferung"). Das Parsen läuft beim ersten Zugriff (``lru_cache``, faktisch
einmal pro Prozess) direkt aus dem package-data-Dist — das ist das Buildzeit-
Muster, das Python hier zur Verfügung hat: eine neue Wiki-Seite in
``llms.txt`` verlinken lässt sie automatisch als neues Thema erscheinen, ohne
Code an der Capability zu ändern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from energietools.capabilities.base import CapabilityError

_WIKI_PACKAGE = "energietools"
_WIKI_SUBDIR = "wiki"
_LLMS_TXT = "llms.txt"

# Markdown-Links "[Titel](pfad.md)" — llms.txt listet jede Seite genau einmal,
# mit Pfaden relativ zum Wiki-Root (z.B. "index.md", "netz/netzentgelte.md").
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+\.md)\)")
# Konvention jeder Wiki-Seite: letzte Zeile "Stand: 2026-06" (siehe alle
# bestehenden Seiten). Nimmt das letzte Vorkommen, falls "Stand:" auch im
# Fließtext auftaucht.
_STAND_RE = re.compile(r"^Stand:\s*(.+?)\.?\s*$", re.MULTILINE)


class WikiPageNotFoundError(CapabilityError):
    """Kein Wiki-Thema mit dieser ID bekannt (thema-Enum ist die Quelle der Wahrheit)."""


@dataclass(frozen=True)
class WikiPage:
    """Ein Eintrag aus ``wiki/llms.txt``."""

    thema: str  # stabiler Slug — Enum-Wert von get_knowledge(thema=...)
    titel: str  # Linktext aus llms.txt
    relpath: str  # Pfad relativ zum Wiki-Root, z.B. "netz/netzentgelte.md"


def _read_wiki(relpath: str) -> str:
    """Liest eine Datei aus dem gebündelten ``wiki/``-Ordner (Package-Data)."""
    try:
        return (
            resources.files(_WIKI_PACKAGE)
            .joinpath(_WIKI_SUBDIR)
            .joinpath(relpath)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise CapabilityError(
            f"Wiki-Datei '{relpath}' nicht gefunden — ist wiki/ im Package (pyproject "
            "package-data)?",
        ) from exc


def _slug_fuer(relpath: str) -> str:
    """Leitet einen stabilen Thema-Slug aus dem Wiki-relativen Pfad ab.

    ``.../index.md`` trägt den Namen seines Elternordners (die Wiki-Startseite
    ``index.md`` selbst wird ``wiki-index`), alles andere ist der Pfad mit
    ``-`` statt ``/``, ohne ``.md``-Endung. Beispiele: ``markt/index.md`` ->
    ``markt``; ``netz/netzentgelte.md`` -> ``netz-netzentgelte``;
    ``glossar.md`` -> ``glossar``.
    """
    stem = relpath[:-3] if relpath.endswith(".md") else relpath
    teile = [t for t in stem.split("/") if t]
    if teile and teile[-1] == "index":
        teile = teile[:-1]
        if not teile:
            return "wiki-index"
    return "-".join(teile)


@lru_cache(maxsize=1)
def load_wiki_pages() -> tuple[WikiPage, ...]:
    """Parst ``wiki/llms.txt`` zur Seiten-Liste (Quelle des ``thema``-Enums)."""
    text = _read_wiki(_LLMS_TXT)
    seiten: list[WikiPage] = []
    gesehen: set[str] = set()
    for titel, relpath in _LINK_RE.findall(text):
        if relpath in gesehen:
            continue
        gesehen.add(relpath)
        seiten.append(WikiPage(thema=_slug_fuer(relpath), titel=titel, relpath=relpath))
    if not seiten:
        raise CapabilityError("wiki/llms.txt enthält keine erkennbaren Seiten-Links")
    return tuple(seiten)


def find_page(thema: str) -> WikiPage:
    """Löst ein ``thema`` zur WikiPage auf. Wirft ``WikiPageNotFoundError``, wenn unbekannt."""
    for page in load_wiki_pages():
        if page.thema == thema:
            return page
    raise WikiPageNotFoundError(f"Unbekanntes Wiki-Thema: '{thema}'")


def read_page_text(page: WikiPage) -> str:
    """Liest den vollen Markdown-Inhalt einer Wiki-Seite."""
    return _read_wiki(page.relpath)


def extract_stand(text: str) -> str:
    """Letzte 'Stand: ...'-Zeile der Seite (Konvention aller Wiki-Seiten)."""
    matches = _STAND_RE.findall(text)
    return matches[-1] if matches else ""
