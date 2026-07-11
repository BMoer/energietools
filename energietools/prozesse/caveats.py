# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Sichere, minimale Trigger-Auswertung für Prozess-Caveats (D7, WP-P 2).

Ein Trigger ist entweder das Literal ``"immer"`` (immer wahr) oder ein
einfacher Vergleich ``"<dotted.key> <op> <wert>"`` gegen einen Kontext
(verschachteltes Dict, z. B. aus einem Tool-Result). Bewusst KEIN ``eval()``:
Trigger-Strings kommen aus YAML-Dateien — Bens Review, aber die Auswertung
selbst soll auch bei einem fehlerhaften/böswilligen Trigger keinen beliebigen
Code ausführen (Eingaben an Systemgrenzen nie vertrauen).
"""

from __future__ import annotations

import re
from typing import Any

from energietools.prozesse.models import Caveat

_TRIGGER_RE = re.compile(r"^([\w.]+)\s*(==|!=|>=|<=|>|<)\s*(.+)$")

_OPS: dict[str, Any] = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">=": lambda a, b: a is not None and a >= b,
    "<=": lambda a, b: a is not None and a <= b,
    ">": lambda a, b: a is not None and a > b,
    "<": lambda a, b: a is not None and a < b,
}


def _get_dotted(context: dict[str, Any], pfad: str) -> Any:
    wert: Any = context
    for teil in pfad.split("."):
        if not isinstance(wert, dict) or teil not in wert:
            return None
        wert = wert[teil]
    return wert


def _parse_literal(text: str) -> Any:
    text = text.strip()
    if text == "true":
        return True
    if text == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text.strip("'\"")


def trigger_aktiv(trigger: str, context: dict[str, Any] | None = None) -> bool:
    """Wertet EINEN Trigger-String gegen einen Kontext aus (kein ``eval()``)."""
    if trigger.strip() == "immer":
        return True
    match = _TRIGGER_RE.match(trigger.strip())
    if not match:
        # Unbekanntes Format: konservativ NICHT auslösen, statt zu raten.
        return False
    pfad, op, wert_text = match.groups()
    ist = _get_dotted(context or {}, pfad)
    soll = _parse_literal(wert_text)
    return _OPS[op](ist, soll)


def aktive_caveats(caveats: list[Caveat], context: dict[str, Any] | None = None) -> list[Caveat]:
    """Alle Caveats, deren Trigger im gegebenen Kontext zutrifft."""
    return [c for c in caveats if trigger_aktiv(c.trigger, context)]
