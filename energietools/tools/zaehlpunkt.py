# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Österreichischer Zählpunkt (Metering Point): Kanonisierung + Validierung.

Ein Zählpunkt ist ein 33-Zeichen-Identifier für einen österreichischen Strom-
oder Gas-Zählpunkt. Die kanonische Form ist::

    AT + 6-stellige Netzbetreiber-VKZ + 5-stellige Anlagengruppe + 20-Zeichen-Anlagencode

Warum ein eigenes Modul?
- OCR/LLM-Transkription fügt Punkte/Leerzeichen ein oder verschluckt Ziffern.
  Derselbe Zählpunkt erscheint als ``AT.001000.00000.…`` auf einer Rechnung
  und als ``AT0010000000…`` auf der nächsten — ohne gemeinsame kanonische
  Form registrieren zwei korrekte Ablesungen als Mismatch.
- Pauschalanlagen (unmetered) nutzen eine Sentinel-Form
  ``AT399999999999PAUSCHALE…``, die die Ziffern-Normalisierung überleben muss.

Eine Bundesland-Ableitung aus dem VKZ-Präfix ist bewusst NICHT enthalten: das
öffentliche VKZ→Bundesland-Mapping überlappt (z.B. deckt VKZ 001000 die
Wiener Netze für Wien UND Teile Niederösterreichs) — ein naiver Cross-Check
produziert mehr False Positives als Nutzen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Standard-Zählpunktform: AT + 31 Ziffern = 33 Zeichen gesamt.
_STANDARD_LENGTH = 33
_PAUSCHAL_TOKEN = "PAUSCHALE"

# Strikte (post-normalisierte) Form. Bewusst [0-9] statt \d: \d matcht auch
# Unicode-Ziffern (arabisch-indisch, Fullwidth), die downstream gegen ASCII-
# Referenzdaten nie matchen würden — hier deterministisch als ungültig führen.
_STRICT_RE = re.compile(r"^AT[0-9]{31}$")
# Pauschal-Sentinel — von manchen Lieferanten für unbemessene Anlagen genutzt.
_PAUSCHAL_RE = re.compile(r"^AT[0-9]{12}PAUSCHALE[0-9]+$")


@dataclass(frozen=True)
class ZaehlpunktResult:
    """Ergebnis der Zählpunkt-Prüfung.

    ``canonical`` ist immer befüllt (best-effort). ``valid_strict`` ist nur
    True, wenn die kanonische Form die 33-Zeichen-Standardform (bzw. die
    Pauschal-Sentinel-Form) erfüllt.
    """

    raw: str
    canonical: str
    valid_strict: bool
    is_pauschal: bool


def _strip_separators(text: str) -> str:
    """Whitespace, Punkte und Bindestriche entfernen — Ziffern/Buchstaben bleiben."""
    return re.sub(r"[\s.\-]", "", text)


def is_pauschal(raw: str) -> bool:
    """True, wenn der String den Pauschalanlagen-Sentinel trägt."""
    if not raw:
        return False
    return _PAUSCHAL_TOKEN in raw.upper()


def canonical_zaehlpunkt(raw: str) -> str:
    """Normalisiert einen Zählpunkt-String für Vergleich und Speicherung.

    Gibt bei unbrauchbarer Form den Input (uppercase, Separatoren entfernt)
    zurück, damit Aufrufer das Roh-Ergebnis noch verwenden können.
    Pauschal-Sentinels behalten das PAUSCHALE-Token.
    """
    if not raw or not raw.strip():
        return ""

    s = raw.strip().upper()

    if _PAUSCHAL_TOKEN in s:
        # Separatoren rund um das Token entfernen, Token selbst behalten.
        return _strip_separators(s)

    cleaned = _strip_separators(s)
    if not cleaned.startswith("AT"):
        # Manche Transkriptionen stellen Fremdzeichen voran — AT-Präfix
        # irgendwo im String wiederfinden.
        m = re.search(r"AT[0-9]{20,}", cleaned)
        if m:
            cleaned = m.group(0)
        else:
            return cleaned  # nichts rekonstruierbar — Rohform zurückgeben

    return cleaned


def is_valid(zp: str) -> bool:
    """True für die strikte 33-Zeichen-Standardform."""
    if not zp:
        return False
    return bool(_STRICT_RE.match(zp))


def validate(raw: str) -> ZaehlpunktResult:
    """Normalisieren + klassifizieren in einem Aufruf (strukturierter Outcome)."""
    canonical = canonical_zaehlpunkt(raw)
    pauschal = is_pauschal(canonical)
    valid_strict = (
        bool(_PAUSCHAL_RE.match(canonical)) if pauschal else is_valid(canonical)
    )
    return ZaehlpunktResult(
        raw=raw or "",
        canonical=canonical,
        valid_strict=valid_strict,
        is_pauschal=pauschal,
    )
