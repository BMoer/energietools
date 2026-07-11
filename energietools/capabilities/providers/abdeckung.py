# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Versorger-Abdeckung je Netzgebiet.

Österreich ist ein bundesweiter Strommarkt: die meisten Lieferanten liefern
überall, die Landesversorger/Stadtwerke aber primär in ihrem Bundesland
(``region`` in ``anbieter.json``). Diese Schicht beantwortet für eine PLZ:

- in welchem **Netzgebiet** (VNB) + Bundesland sie liegt,
- welche bekannten **Lieferanten** dort verfügbar sind (bundesweit + regional passend),
- welche **regional ausgeschlossen** sind (Landesversorger anderer Bundesländer),
- und welche davon im **Open-Data-Tarifkatalog** vertreten sind (unsere Abdeckung).

Wichtig für den Tarifvergleich: ein Vorarlberger Landesversorger darf an einer
NÖ-Adresse NICHT als Bestpreis ausgespielt werden — genau das prüft ``ist_verfuegbar``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.netz.resolve import (
    ist_verfuegbar,
    plz_info,
    resolve_netzbetreiber,
)

_DATA_PACKAGE = "energietools.data.providers"
_RECHTSFORM = (" gmbh", " ag", " kg", " co", " ges", " mbh", " & co", " vertrieb")

# anbieter.json nutzt Abkürzungen, plz_info volle Bundesland-Namen → angleichen,
# damit der Versorgungsgebiet-Abgleich (ist_verfuegbar) greift.
_BUNDESLAND = {
    "NÖ": "Niederösterreich", "OÖ": "Oberösterreich", "Vbg": "Vorarlberg",
    "Ktn": "Kärnten", "Sbg": "Salzburg", "Stmk": "Steiermark", "Bgld": "Burgenland",
    "W": "Wien",
}


@dataclass(frozen=True)
class Versorger:
    """Ein Stromlieferant mit Versorgungsgebiet (aus ``anbieter.json``)."""

    brand: str
    canonical: str
    region: tuple[str, ...]  # ("AT",) = bundesweit, sonst Bundesländer
    aliases: tuple[str, ...] = ()

    @property
    def bundesweit(self) -> bool:
        return "AT" in self.region


@dataclass(frozen=True)
class VersorgerAbdeckung:
    """Abdeckungs-Sicht für EINE PLZ / ein Netzgebiet."""

    plz: str
    bundeslaender: tuple[str, ...]
    netzbetreiber: str | None
    verfuegbar: list[Versorger] = field(default_factory=list)
    nicht_verfuegbar: list[Versorger] = field(default_factory=list)  # regional ausgeschlossen
    im_katalog: list[str] = field(default_factory=list)  # Brands mit Tarifen im Katalog

    @property
    def anzahl_verfuegbar(self) -> int:
        return len(self.verfuegbar)

    @property
    def anzahl_bundesweit(self) -> int:
        return sum(1 for v in self.verfuegbar if v.bundesweit)

    @property
    def anzahl_regional(self) -> int:
        return sum(1 for v in self.verfuegbar if not v.bundesweit)


def _norm(name: str) -> str:
    s = name.lower().strip()
    for tok in _RECHTSFORM:
        s = s.replace(tok, "")
    return " ".join(s.split())


# Zu generische Tokens würden quer durch alle Anbieter matchen ("energie ag" → "energie").
_GENERISCH = {"energie", "strom", "gas", "ag", "gmbh", "kraft", "kraftwerke", "vertrieb"}


def _versorger_needles(v: Versorger) -> list[str]:
    """Normalisierte, nicht-generische Match-Tokens eines Versorgers (Brand/Canonical/Aliases)."""
    needles = [_norm(v.brand), _norm(v.canonical), *[_norm(a) for a in v.aliases]]
    return [n for n in needles if n and n not in _GENERISCH]


@lru_cache(maxsize=1)
def lade_providers_manifest() -> dict:
    """Lädt das providers-MANIFEST (Stand/Provenance); ``{}`` wenn nicht vorhanden.

    Fail-open: das Manifest ist Zusatzinfo (Result-``meta``, B.6), nie Blocker.
    """
    try:
        raw = json.loads(
            resources.files(_DATA_PACKAGE).joinpath("MANIFEST.json").read_text("utf-8"),
        )
    except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


@lru_cache(maxsize=1)
def lade_anbieter() -> tuple[Versorger, ...]:
    """Lädt ``anbieter.json`` als Versorger-Tupel (nur Strom-fähige)."""
    try:
        raw = json.loads(
            resources.files(_DATA_PACKAGE).joinpath("anbieter.json").read_text("utf-8"),
        )
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise CapabilityError("anbieter.json nicht gefunden") from exc
    rows = raw if isinstance(raw, list) else next(
        (v for v in raw.values() if isinstance(v, list)), None,
    )
    if rows is None:
        raise CapabilityError("anbieter.json: kein Lieferanten-Array gefunden")
    out: list[Versorger] = []
    for a in rows:
        if "strom" not in str(a.get("type", "")):
            continue  # nur Strom-Lieferanten
        region = tuple(_BUNDESLAND.get(r, r) for r in (a.get("region") or ("AT",)))
        out.append(
            Versorger(
                brand=a.get("brand", a.get("canonical", "")),
                canonical=a.get("canonical", ""),
                region=region,
                aliases=tuple(a.get("aliases") or ()),
            ),
        )
    return tuple(out)


def versorger_abdeckung(
    plz: str, *, katalog_lieferanten: list[str] | None = None,
) -> VersorgerAbdeckung:
    """Welche Lieferanten sind an dieser PLZ verfügbar (bundesweit + regional passend)?

    ``katalog_lieferanten``: optional die Lieferanten-Namen des Tarifkatalogs, um
    die eigene Abdeckung zu markieren (``im_katalog``). Ohne Angabe wird der
    gebündelte Open-Data-Katalog geladen.
    """
    plz = str(plz).strip()
    info = plz_info(plz)
    nb = resolve_netzbetreiber(plz)
    laender = tuple(info.bundeslaender) if info else ()

    verfuegbar, ausgeschlossen = [], []
    for v in lade_anbieter():
        # Bundesweite (AT) immer; regionale nur, wenn ihr Bundesland die PLZ deckt.
        verf = v.bundesweit or ist_verfuegbar(list(v.region), plz)
        (verfuegbar if verf else ausgeschlossen).append(v)

    if katalog_lieferanten is None:
        from energietools.capabilities.tariffs.catalog import TariffCatalog

        katalog_lieferanten = [t.lieferant for t in TariffCatalog.load().all()]
    kat_norm = {_norm(name) for name in katalog_lieferanten}

    def _im_katalog(v: Versorger) -> bool:
        # EIN-direktional (Anbieter-Bezeichner IN Katalogname) + generische Tokens raus.
        return any(any(n in k for k in kat_norm) for n in _versorger_needles(v))

    im_katalog = sorted({v.brand for v in verfuegbar if _im_katalog(v)})
    return VersorgerAbdeckung(
        plz=plz,
        bundeslaender=laender,
        netzbetreiber=nb.name if nb else None,
        verfuegbar=verfuegbar,
        nicht_verfuegbar=ausgeschlossen,
        im_katalog=im_katalog,
    )


def ist_lieferant_verfuegbar(lieferant: str, plz: str) -> bool:
    """True, wenn ein Lieferant (per Name) an dieser PLZ beziehbar ist.

    Fail-open: bundesweite Anbieter, unbekannte Namen und lokal passende
    Landesversorger → ``True``. ``False`` NUR, wenn der Name einen Landesversorger/
    Stadtwerke-Anbieter trifft, dessen Bundesland die PLZ NICHT deckt (z.B. TIWAG
    an einer NÖ-Adresse). Damit verschwindet aus dem Tarifvergleich genau das, was
    der Kunde dort nicht abschließen kann — nicht mehr.
    """
    if not lieferant:
        return True
    name = _norm(lieferant)
    for v in versorger_abdeckung(plz, katalog_lieferanten=[]).nicht_verfuegbar:
        if any(n in name for n in _versorger_needles(v)):
            return False
    return True
