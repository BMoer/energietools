# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Gemeinsame Bundesland-Auflösung für die Förder-/Beratungs-/EEG-Capabilities.

``bundesland`` ist der fachliche Pflicht-Input dieser drei Capabilities, kann
aber wahlweise aus einer ``plz`` über die bestehende netz-PLZ-Logik
(:mod:`energietools.capabilities.netz.resolve`) abgeleitet werden. Ein
unbekanntes/nicht auflösbares Bundesland führt zu einer strukturierten
:class:`CapabilityRejection` mit einer klaren Rückfrage statt eines stillen
Leer-Ergebnisses oder einer rohen Exception.
"""

from __future__ import annotations

from energietools.capabilities.base import CapabilityRejection
from energietools.capabilities.netz.resolve import plz_info

BEKANNTE_BUNDESLAENDER = (
    "Burgenland",
    "Kärnten",
    "Niederösterreich",
    "Oberösterreich",
    "Salzburg",
    "Steiermark",
    "Tirol",
    "Vorarlberg",
    "Wien",
)


def bundesland_aus_plz(plz: str) -> str | None:
    """Leitet das Bundesland aus einer PLZ ab (bestehende netz-PLZ-Logik).

    Liefert ``None``, wenn die PLZ unbekannt ist oder mehr als ein Bundesland
    umfasst (geteilte Grenz-PLZ) — dann muss ``bundesland`` explizit kommen.
    """
    info = plz_info(plz)
    if info is None or len(info.bundeslaender) != 1:
        return None
    return info.bundeslaender[0]


def resolve_bundesland(bundesland: str | None, plz: str | None) -> str:
    """Löst das Ziel-Bundesland auf oder wirft eine klare :class:`CapabilityRejection`."""
    kandidat = (bundesland or "").strip()
    if not kandidat and plz:
        aus_plz = bundesland_aus_plz(str(plz).strip())
        if aus_plz is None:
            raise CapabilityRejection(
                f"PLZ '{plz}' lässt sich keinem eindeutigen Bundesland zuordnen — "
                "bitte bundesland angeben.",
                [
                    {
                        "feld": "plz",
                        "regel": "bundesland_nicht_eindeutig",
                        "wert": plz,
                        "rueckfrage": (
                            "In welchem Bundesland liegt die PLZ (bzw. welches "
                            "Bundesland meinst du)?"
                        ),
                    }
                ],
            )
        kandidat = aus_plz
    if not kandidat:
        raise CapabilityRejection(
            "bundesland oder plz ist erforderlich.",
            [
                {
                    "feld": "bundesland",
                    "regel": "erforderlich",
                    "wert": None,
                    "rueckfrage": "In welchem Bundesland (oder mit welcher PLZ) soll ich suchen?",
                }
            ],
        )
    treffer = next(
        (b for b in BEKANNTE_BUNDESLAENDER if b.casefold() == kandidat.casefold()), None
    )
    if treffer is None:
        raise CapabilityRejection(
            f"Unbekanntes Bundesland '{kandidat}'.",
            [
                {
                    "feld": "bundesland",
                    "regel": "unbekannt",
                    "wert": kandidat,
                    "rueckfrage": f"Meinst du eines von: {', '.join(BEKANNTE_BUNDESLAENDER)}?",
                }
            ],
        )
    return treffer
