# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Capability-Hülle der Wissens-Auslieferung (D7 „Wissens-Auslieferung", Amendment 9).

``get_knowledge`` liefert deterministisch genau EINE kuratierte Wiki-Seite als
reinen Text — kein Rechen-Result, keine gerechneten €-Werte. Das ist bewusst
schwächer als „das ganze Wiki in den Kontext drücken" (D7 Option (b),
verworfen: Kontext-Ballast, skaliert nicht) — der Client ruft on demand genau
das Thema ab, das er gerade braucht.
"""

from __future__ import annotations

from importlib import metadata
from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.knowledge.pages import (
    WikiPageNotFoundError,
    extract_stand,
    find_page,
    load_wiki_pages,
    read_page_text,
)


def _paket_version() -> str:
    try:
        return metadata.version("energietools")
    except metadata.PackageNotFoundError:
        return "dev"


def _thema_beschreibung() -> str:
    """Menschenlesbare 'slug: Titel'-Liste für die Schema-Description (Auswahlhilfe)."""
    zeilen = [f"{p.thema}: {p.titel}" for p in load_wiki_pages()]
    return "; ".join(zeilen)


class GetKnowledgeCapability(Capability):
    """Liefert eine kuratierte Wiki-Seite der WISSEN-Schicht als reinen Text."""

    name = "get_knowledge"
    summary = (
        "Liefert den Inhalt einer kuratierten Wiki-Seite von energietools (WISSEN-"
        "Schicht, z. B. wie sich Stromkosten in Österreich zusammensetzen) als "
        "reinen Text plus Stand und Quellenverweis. Reine Text-Auslieferung — kein "
        "Rechen-Result, keine gerechneten €-Werte (die liefern tariff_compare, "
        "gesamtkosten, netzkosten & co.)."
    )

    @property
    def input_schema(self) -> dict[str, Any]:  # noqa: D102 — dynamisch aus llms.txt (Buildzeit-Muster)
        return {
            "type": "object",
            "properties": {
                "thema": {
                    "type": "string",
                    "enum": [p.thema for p in load_wiki_pages()],
                    "description": (
                        "Welches Wiki-Thema (Slug: Titel je Seite aus wiki/llms.txt): "
                        + _thema_beschreibung()
                    ),
                },
            },
            "required": ["thema"],
        }

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        thema = kwargs.get("thema")
        meta: dict[str, Any] = {"snapshot_version": _paket_version()}
        if not thema:
            return meta
        try:
            page = find_page(str(thema))
        except WikiPageNotFoundError:
            return meta
        meta["quelle"] = f"energietools wiki/{page.relpath}"
        meta["stand"] = extract_stand(read_page_text(page))
        return meta

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        thema = kwargs.get("thema")
        if not thema or not isinstance(thema, str):
            raise CapabilityError("thema ist erforderlich (siehe input_schema.enum)")
        try:
            page = find_page(thema)
        except WikiPageNotFoundError as exc:
            raise CapabilityError(str(exc)) from exc
        inhalt = read_page_text(page)
        return {
            "thema": page.thema,
            "titel": page.titel,
            "inhalt": inhalt,
            "stand": extract_stand(inhalt),
            "quelle": f"energietools wiki/{page.relpath}",
        }
