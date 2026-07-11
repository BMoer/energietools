# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Checker für anonymisierte Beispiel-Dialoge (``prozesse/beispiele/*.json``, D7).

Ein Beispiel-Dialog fixiert für einen Prozess: erwartete Frage-IDs, erwartete
Tool-Calls (Schritt + Capability + Quelle aus dem ``tool_mapping``) und
erwartete Pflicht-Caveats (als Trigger-Strings, ausgewertet gegen einen
mitgelieferten Kontext). ``pruefe_beispiel`` prüft das Beispiel deterministisch
gegen den tatsächlich geladenen Prozess — Drift zwischen Beispiel und YAML
wird so sichtbar, nicht erst beim manuellen Review.
"""

from __future__ import annotations

from typing import Any

from energietools.prozesse.caveats import aktive_caveats
from energietools.prozesse.models import Prozess


def pruefe_beispiel(beispiel: dict[str, Any], prozess: Prozess) -> list[str]:
    """Prüft einen Beispiel-Dialog gegen den geladenen Prozess. Leere Liste = ok."""
    fehler: list[str] = []
    if beispiel.get("prozess_id") != prozess.meta.id:
        fehler.append(
            f"prozess_id {beispiel.get('prozess_id')!r} != geladener Prozess "
            f"{prozess.meta.id!r}",
        )

    bekannte_frage_ids = {f.id for f in prozess.fragen}
    for fid in beispiel.get("erwartete_frage_ids", []):
        if fid not in bekannte_frage_ids:
            fehler.append(
                f"erwartete frage_id '{fid}' existiert nicht in {prozess.meta.id}.fragen",
            )

    schritte_by_name = {s.schritt: s for s in prozess.tool_mapping}
    for call in beispiel.get("erwartete_tool_calls", []):
        schritt = schritte_by_name.get(call.get("schritt"))
        if schritt is None:
            fehler.append(
                f"erwarteter Tool-Call-Schritt '{call.get('schritt')}' existiert nicht "
                "in tool_mapping",
            )
            continue
        if schritt.capability != call.get("capability"):
            fehler.append(
                f"Schritt '{call.get('schritt')}': erwartete capability "
                f"{call.get('capability')!r}, tool_mapping hat {schritt.capability!r}",
            )
        if schritt.quelle != call.get("quelle"):
            fehler.append(
                f"Schritt '{call.get('schritt')}': erwartete quelle {call.get('quelle')!r}, "
                f"tool_mapping hat {schritt.quelle!r}",
            )

    kontext = beispiel.get("kontext", {})
    erwartete_trigger = sorted(beispiel.get("erwartete_caveats_trigger", []))
    tatsaechliche_trigger = sorted(c.trigger for c in aktive_caveats(prozess.caveats, kontext))
    if erwartete_trigger != tatsaechliche_trigger:
        fehler.append(
            f"Pflicht-Caveats weichen ab: erwartet {erwartete_trigger}, tatsächlich "
            f"aktiv {tatsaechliche_trigger} (Kontext: {kontext})",
        )
    return fehler
