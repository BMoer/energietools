# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Struktur-Linter für ``prozesse/*.yaml`` (D7 Testbarkeit, WP-P 2).

Prüft deterministisch, was ein Reviewer sonst von Hand nachschlagen müsste:

(a) jede ``tool_mapping``-Capability existiert — in ``default_registry()`` bei
    ``quelle: energietools``, in ``EXTERN_TOOLS_V1`` (v1-Gateway-Katalog) bei
    ``quelle: extern``;
(b) jeder Pflicht-Input einer referenzierten energietools-Capability ist
    durch ``benoetigte_daten`` oder eine ``frage`` (per ``feld``) gedeckt;
(c) die Pflichtblöcke ``tool_mapping`` und ``caveats`` sind nicht leer;
(d) die Block-Reihenfolge der Rohdatei folgt dem D7-Kanon.

SemVer wird schon beim Laden geprüft (``ProzessMeta``, wirft dort) — ein
Verstoß erscheint hier nicht als ``LintFehler``, sondern als Exception beim
``load_prozess``-Aufruf.
"""

from __future__ import annotations

from dataclasses import dataclass

from energietools.capabilities.base import CapabilityRegistry
from energietools.capabilities.registry import default_registry
from energietools.prozesse.external_tools import EXTERN_TOOLS_V1
from energietools.prozesse.models import Prozess


@dataclass(frozen=True)
class LintFehler:
    prozess_id: str
    schritt: str | None
    regel: str
    meldung: str

    def __str__(self) -> str:  # pragma: no cover — Bequemlichkeit fürs Debuggen/CLI
        ort = f"{self.prozess_id}.{self.schritt}" if self.schritt else self.prozess_id
        return f"[{ort}] {self.regel}: {self.meldung}"


def lint_prozess(
    prozess: Prozess, *, registry: CapabilityRegistry | None = None,
) -> list[LintFehler]:
    """Struktur-Linter über ein bereits geladenes :class:`Prozess`-Objekt."""
    reg = registry or default_registry()
    fehler: list[LintFehler] = []
    pid = prozess.meta.id
    gedeckt = prozess.gedeckte_felder

    if not prozess.tool_mapping:
        fehler.append(LintFehler(pid, None, "pflichtblock", "tool_mapping ist leer"))
    if not prozess.caveats:
        fehler.append(LintFehler(pid, None, "pflichtblock", "caveats ist leer"))

    for schritt in prozess.tool_mapping:
        if schritt.quelle == "energietools":
            if schritt.capability not in reg.names:
                fehler.append(
                    LintFehler(
                        pid,
                        schritt.schritt,
                        "tool_mapping.existenz",
                        f"Capability '{schritt.capability}' nicht in default_registry()",
                    ),
                )
                continue
            if schritt.rolle == "ausblick":
                # Nur genannt, nicht aufgerufen — keine Pflicht-Input-Deckung nötig.
                continue
            cap = reg.get(schritt.capability)
            required = set(cap.input_schema.get("required", []))
            fehlend = required - gedeckt - set(schritt.nicht_benutzerdaten)
            if fehlend:
                fehler.append(
                    LintFehler(
                        pid,
                        schritt.schritt,
                        "tool_mapping.pflicht_inputs",
                        f"Capability '{schritt.capability}' braucht {sorted(fehlend)} — "
                        "nicht durch benoetigte_daten/fragen gedeckt",
                    ),
                )
        elif schritt.quelle == "extern":
            if schritt.capability not in EXTERN_TOOLS_V1:
                fehler.append(
                    LintFehler(
                        pid,
                        schritt.schritt,
                        "tool_mapping.extern_unbekannt",
                        f"'{schritt.capability}' ist weder in default_registry() noch in "
                        "EXTERN_TOOLS_V1 (v1-Gateway-Katalog, ARCHITECTURE-2.0.md §3.3 "
                        "WP-G1) — Tippfehler oder fehlende Katalog-Pflege?",
                    ),
                )
    return fehler


def lint_datei(filename: str, *, registry: CapabilityRegistry | None = None) -> list[LintFehler]:
    """Struktur-Linter über eine ``prozesse/<id>.yaml``-Datei (inkl. Block-Reihenfolge)."""
    from energietools.prozesse.loader import (
        load_prozess,
        load_prozess_raw,
        pruefe_blockreihenfolge,
    )

    raw = load_prozess_raw(filename)
    prozess = load_prozess(filename)
    pid = prozess.meta.id
    fehler = [
        LintFehler(pid, None, "blockreihenfolge", m) for m in pruefe_blockreihenfolge(raw)
    ]
    fehler.extend(lint_prozess(prozess, registry=registry))
    return fehler


def lint_alle(*, registry: CapabilityRegistry | None = None) -> dict[str, list[LintFehler]]:
    """Struktur-Linter über alle im MANIFEST gelisteten Prozesse."""
    from energietools.prozesse.loader import manifest_dateien

    return {datei: lint_datei(datei, registry=registry) for datei in manifest_dateien()}


def pruefe_manifest_konsistenz() -> list[str]:
    """MANIFEST-Einträge (id/prozess_version/stand) müssen zum meta-Block passen."""
    from energietools.prozesse.loader import load_manifest, load_prozess

    fehler: list[str] = []
    for eintrag in load_manifest().get("prozesse", []):
        datei = eintrag.get("datei", "")
        prozess = load_prozess(datei)
        if prozess.meta.id != eintrag.get("id"):
            fehler.append(
                f"{datei}: MANIFEST id={eintrag.get('id')!r} != meta.id={prozess.meta.id!r}",
            )
        if prozess.meta.prozess_version != eintrag.get("prozess_version"):
            fehler.append(
                f"{datei}: MANIFEST prozess_version={eintrag.get('prozess_version')!r} != "
                f"meta.prozess_version={prozess.meta.prozess_version!r}",
            )
        if str(prozess.meta.stand) != eintrag.get("stand"):
            fehler.append(
                f"{datei}: MANIFEST stand={eintrag.get('stand')!r} != "
                f"meta.stand={prozess.meta.stand!r}",
            )
    return fehler
