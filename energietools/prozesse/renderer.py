# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Deterministischer Renderer: Prozess (YAML) -> Skill-Markdown / Kurzform (D7).

Zwei Ausgabeformen, ein Prozess:

- :func:`render_skill` — vollständiges ``SKILL.md`` (YAML-Frontmatter +
  Markdown-Body), ausgeliefert über den engram-``GET /skills``-Mechanismus an
  Coding-Agents, die Skills installieren können.
- :func:`render_kurzform` / :func:`render_instructions_block` — die Kurzform
  für Chat-Clients, die keine Skills installieren können: der existierende
  MCP-``initialize.instructions``-Kanal bzw. die Tool-Description des
  jeweiligen Einstiegs-Tools (D7 „Rendering in Skills").

Beide sind reine Funktionen über ein bereits geladenes :class:`Prozess` —
kein I/O hier, das übernimmt ``loader.py`` bzw. der Aufrufer (Skript, Test).
"""

from __future__ import annotations

from energietools.prozesse.models import Prozess

_TITEL_UEBERSCHREIBUNG = {
    "erstkontakt": "Erstkontakt",
    "rechnungsanalyse": "Rechnungsanalyse",
    "lastganganalyse": "Lastgang-Analyse",
}


def _titel(prozess: Prozess) -> str:
    return _TITEL_UEBERSCHREIBUNG.get(prozess.meta.id, prozess.meta.id.replace("_", " ").title())


def _erste_satz(text: str) -> str:
    """Erster Satz eines Fließtexts (für kompakte description-Felder)."""
    kompakt = " ".join(text.split())
    ende = kompakt.find(". ")
    return kompakt[: ende + 1] if ende != -1 else kompakt


def render_skill(prozess: Prozess) -> str:
    """Rendert ``prozesse/<id>.yaml`` zu einem vollständigen ``SKILL.md``."""
    meta = prozess.meta
    zeilen: list[str] = []
    zeilen.append("---")
    zeilen.append(f"name: gridbert-{meta.id}")
    zeilen.append(f"description: {_erste_satz(prozess.ziel)}")
    zeilen.append("---")
    zeilen.append("")
    zeilen.append(f"# {_titel(prozess)}")
    zeilen.append("")
    zeilen.append(
        f"**Version:** {meta.prozess_version} · **Stand:** {meta.stand} · "
        f"**Markt:** {meta.market} · **Lizenz:** {meta.license}",
    )
    zeilen.append("")
    zeilen.append("## Ziel")
    zeilen.append("")
    zeilen.append(prozess.ziel.strip())
    zeilen.append("")

    zeilen.append("## Benötigte Daten")
    zeilen.append("")
    if not prozess.benoetigte_daten:
        zeilen.append("Keine — dieser Prozess stellt bewusst keine Pflichtdaten voraus.")
    else:
        for d in prozess.benoetigte_daten:
            status = "Pflicht" if d.pflicht else "Optional"
            zusatz = f" — {d.format}" if d.format else ""
            zeilen.append(f"- **{d.feld}** (Quelle: {d.quelle}, {status}){zusatz}")
    zeilen.append("")

    zeilen.append("## Fragen")
    zeilen.append("")
    if not prozess.fragen:
        zeilen.append("Keine — dieser Prozess stellt keine strukturierten Rückfragen.")
    else:
        for f in prozess.fragen:
            zeilen.append(f"### {f.id} (Hebel: {f.hebel})")
            zeilen.append(f"- Frage: {f.text}")
            if f.bedingung:
                zeilen.append(f"- Nur wenn: {f.bedingung}")
            if f.ableitung:
                zeilen.append(f"- Ableitung: {f.ableitung}")
            zeilen.append("")
    if prozess.fragen:
        zeilen.pop()  # letzte Leerzeile der Schleife entfernen (einheitlicher Abstand unten)
    zeilen.append("")

    if prozess.signale:
        zeilen.append("## Signal-Präzedenz (Fakt vor Heuristik)")
        zeilen.append("")
        for signal, eintrag in prozess.signale.items():
            zeilen.append(f"- **{signal}** ist Heuristik für `{eintrag.fakt}`")
        zeilen.append("")

    zeilen.append("## Tool-Mapping")
    zeilen.append("")
    for schritt in prozess.tool_mapping:
        titel = f"{schritt.schritt} — `{schritt.capability}` ({schritt.quelle}, {schritt.rolle})"
        zeilen.append(f"### {titel}")
        if schritt.pflicht_inputs:
            zeilen.append(f"- Pflicht-Inputs: {', '.join(schritt.pflicht_inputs)}")
        for regel in schritt.regeln:
            zeilen.append(f"- {regel}")
        zeilen.append("")
    zeilen.pop()  # letzte Leerzeile

    zeilen.append("")
    zeilen.append("## Datenqualität & Abbruch")
    zeilen.append("")
    if not prozess.datenqualitaet_abbruch:
        zeilen.append("Keine besonderen Abbruchregeln über die Tool-eigene Validierung hinaus.")
    else:
        for regel in prozess.datenqualitaet_abbruch:
            zeilen.append(f"- {regel}")
    zeilen.append("")

    zeilen.append("## Caveats (MÜSSEN in die Antwort)")
    zeilen.append("")
    for c in prozess.caveats:
        zeilen.append(f"- **Trigger `{c.trigger}`:** {c.text.strip()}")
    zeilen.append("")

    return "\n".join(zeilen)


def render_kurzform(prozess: Prozess) -> str:
    """Kurzform für ``initialize.instructions`` / Tool-Descriptions (Chat-Clients).

    Ein bis zwei Sätze: Ziel + Anzahl Pflicht-Caveats — genug, damit ein
    Chat-Client WEISS, dass es diesen Prozess gibt, ohne das ganze Skill in
    den Kontext zu drücken (das Wissen selbst kommt on demand, D7).
    """
    meta = prozess.meta
    ziel_kurz = _erste_satz(prozess.ziel)
    return (
        f"Prozess '{meta.id}' (v{meta.prozess_version}, Stand {meta.stand}): {ziel_kurz} "
        f"({len(prozess.caveats)} Pflicht-Caveat(s), Tool-Mapping gegen den v1-Katalog gelintet.)"
    )


def render_instructions_block(prozesse: list[Prozess]) -> str:
    """Kombinierte Kurzform aller Prozesse für den MCP-``initialize.instructions``-Kanal."""
    zeilen = [
        "Gridbert kennt versionierte Gesprächsleitfäden (Prozesse) für die folgenden "
        "Anwendungsfälle — Details on demand über die jeweilige Capability, nicht "
        "vorab in den Kontext geladen:",
        "",
    ]
    for p in prozesse:
        zeilen.append(f"- {render_kurzform(p)}")
    zeilen.append("")
    zeilen.append(
        "Wissen zur WISSEN-Schicht (z. B. 'wie setzen sich Stromkosten in Österreich "
        "zusammen') kommt on demand über die Capability `get_knowledge` (Parameter "
        "`thema`, siehe deren input_schema.enum) — nicht ungefragt in jede Antwort drücken.",
    )
    return "\n".join(zeilen)


def render_all(output_dir: str) -> None:
    """Rendert alle im MANIFEST gelisteten Prozesse nach ``<output_dir>/gridbert-<id>/SKILL.md``
    plus die kombinierte Kurzform nach ``<output_dir>/_instructions_kurzform.md``.

    Reiner Dateisystem-Schreib-Helper für den Build-Schritt (``python -m
    energietools.prozesse.renderer <output_dir>``); die eigentliche
    Render-Logik bleibt in den reinen Funktionen oben, damit sie ohne I/O
    testbar ist (``tests/test_prozesse_renderer.py`` prüft Drift dagegen).
    """
    from pathlib import Path

    from energietools.prozesse.loader import load_prozess, manifest_dateien

    out = Path(output_dir)
    prozesse = [load_prozess(d) for d in manifest_dateien()]
    for p in prozesse:
        ziel_ordner = out / f"gridbert-{p.meta.id}"
        ziel_ordner.mkdir(parents=True, exist_ok=True)
        (ziel_ordner / "SKILL.md").write_text(render_skill(p) + "\n", encoding="utf-8")
    (out / "_instructions_kurzform.md").write_text(
        render_instructions_block(prozesse) + "\n", encoding="utf-8",
    )


if __name__ == "__main__":
    import sys

    render_all(sys.argv[1] if len(sys.argv) > 1 else "skills")
