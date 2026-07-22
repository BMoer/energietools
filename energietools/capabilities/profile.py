# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Fakt-Index-Fundament (Fakt vor Heuristik, WP „Fakt-vor-Heuristik").

Storage-blind: kein Import aus ``lastgang`` oder einer anderen Capability-
Familie — dieses Modul lebt auf ``capabilities``-Top-Level, weil künftig
mehrere Familien (Lastgang, Rechnung, …) denselben Fakt-Index lesen sollen.

Der Gateway löst ``profil_fakten`` LLM-frei aus der kanonischen Profil-Seite
(``haushalts-profil``) auf und reicht sie als Parameter herein — dieses Modul
kennt weder Engram noch den Gateway, nur das Wire-Format
(:func:`parse_profil_fakten`) und die Kern-Ontologie der 7 bestehenden Felder
(:data:`PROFIL_FELDER`, 1:1 aus ``gridbert/gateway/tools/lastgang_facts.py
FIELD_VALIDATORS`` gespiegelt — SSOT bleibt die gridbert-Ontologie, ein
Paritäts-Drift-Guard läuft im gridbert-e2e-Test).

**Quelle-Vokabular (repo-übergreifend fixiert):** ``profil | rechnung |
messung | prognose``. ``"heuristik"`` wird NIE persistiert oder geparst — ein
Heuristik-Wert ist kein Fakt, sondern die Gegenprobe DAZU (das ist der ganze
Punkt von „Fakt vor Heuristik").
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from energietools.capabilities.base import CapabilityError

FaktQuelle = Literal["profil", "rechnung", "messung", "prognose"]

_GUELTIGE_QUELLEN: frozenset[str] = frozenset({"profil", "rechnung", "messung", "prognose"})


class FaktWert(BaseModel):
    """Ein einzelner Profil-Fakt — Wert + Herkunft (Provenienz-Envelope).

    Frozen (Immutability) + ``extra="forbid"`` (Systemgrenze: ein Fakt-Objekt
    mit unbekannten Zusatzfeldern ist ein Bug, kein Rauschen — anders als das
    ROHE Wire-Objekt in :func:`parse_profil_fakten`, das Forward-Compat-Keys
    bewusst ignoriert, BEVOR es zu einem :class:`FaktWert` wird).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    feld: str
    wert: str | float | int | bool
    quelle: FaktQuelle = "profil"
    stand: datetime | None = None
    anker: str | None = None  # wörtliches Zitat / Seitenverweis (Herkunfts-Beleg)


class ProfileSource(Protocol):
    """Schmaler Lesevertrag auf den Fakt-Index (Muster ``tariff_compare/
    protocols.py`` TariffSource/SpotPriceSource) — storage-agnostisch."""

    def get_fakt(self, feld: str) -> FaktWert | None: ...

    def get_all(self) -> dict[str, FaktWert]: ...


@dataclass(frozen=True)
class ProfilFeld:
    """Ein Eintrag der Kern-Ontologie: welche Werte ein Profil-Feld annehmen darf."""

    feld: str
    art: Literal["enum", "zahl_positiv", "zahl_nichtnegativ", "text", "bool"]
    erlaubte_werte: frozenset[str] | None = None
    beschreibung: str = ""


# Die 7 bestehenden Felder — Enums/Arten 1:1 aus der heutigen
# gridbert-Semantik (FIELD_VALIDATORS) gespiegelt. SSOT bleibt die
# gridbert-Ontologie (ttl); dieser Copy dient dem fail-closed-Parsing hier
# UND dem Drift-Guard gegen ``prozesse/lastganganalyse.yaml`` (s. Tests).
PROFIL_FELDER: dict[str, ProfilFeld] = {
    "asset.heating.type": ProfilFeld(
        feld="asset.heating.type",
        art="enum",
        erlaubte_werte=frozenset(
            {"elektrisch", "waermepumpe", "gas", "fernwaerme", "pellets", "sonstiges", "keine"}
        ),
        beschreibung="Heizungstyp des Haushalts.",
    ),
    "asset.pv.kwp": ProfilFeld(
        feld="asset.pv.kwp",
        art="zahl_positiv",
        beschreibung="PV-Anlagenleistung in kWp.",
    ),
    "asset.battery.kwh": ProfilFeld(
        feld="asset.battery.kwh",
        art="zahl_nichtnegativ",
        beschreibung="Nutzbare Batteriespeicher-Kapazität in kWh.",
    ),
    "asset.continuous_loads": ProfilFeld(
        feld="asset.continuous_loads",
        art="text",
        beschreibung="Benannte Dauerverbraucher (Pool, Aquarium, Server, …).",
    ),
    "behavior.appliance_timing": ProfilFeld(
        feld="behavior.appliance_timing",
        art="text",
        beschreibung="Zeitliche Verschiebbarkeit von Wasch-/Spül-/Trockner-Läufen.",
    ),
    "contract.heiztarif_typ": ProfilFeld(
        feld="contract.heiztarif_typ",
        art="enum",
        erlaubte_werte=frozenset(
            {"heizstromtarif", "waermepumpentarif", "standardtarif", "unbekannt"}
        ),
        beschreibung="Tarif-Typ des Heizungs-/Wärmepumpen-Zählers.",
    ),
    "meter.q15_optin": ProfilFeld(
        feld="meter.q15_optin",
        art="bool",
        beschreibung="Viertelstundenwerte-Opt-in beim Netzbetreiber aktiviert?",
    ),
}


def validiere_fakt_wert(feld: str, wert: Any) -> str | None:
    """Prüft einen rohen Fakt-Wert gegen die Kern-Ontologie.

    ``None`` = ok, sonst eine für den Aufrufer (fail-closed) verwendbare
    Meldung. Bewusst KEINE Exception hier — :func:`parse_profil_fakten` trägt
    die Entscheidung, wann daraus ein ``CapabilityError`` wird.
    """
    definition = PROFIL_FELDER.get(feld)
    if definition is None:
        return f"unbekanntes Profil-Feld {feld!r}"

    if definition.art == "enum":
        erlaubt = definition.erlaubte_werte or frozenset()
        if wert not in erlaubt:
            return f"Wert {wert!r} nicht erlaubt (erwartet einer von {sorted(erlaubt)})"
        return None

    if definition.art == "zahl_positiv":
        if isinstance(wert, bool) or not isinstance(wert, (int, float)) or wert <= 0:
            return f"erwartet eine positive Zahl, erhalten {wert!r}"
        return None

    if definition.art == "zahl_nichtnegativ":
        if isinstance(wert, bool) or not isinstance(wert, (int, float)) or wert < 0:
            return f"erwartet eine nicht-negative Zahl, erhalten {wert!r}"
        return None

    if definition.art == "text":
        if not isinstance(wert, str) or not wert.strip():
            return f"erwartet nicht-leeren Text, erhalten {wert!r}"
        return None

    if definition.art == "bool":
        if not isinstance(wert, bool):
            return f"erwartet einen Bool-Wert, erhalten {wert!r}"
        return None

    return f"unbekannte Feld-Art {definition.art!r} für {feld!r}"  # pragma: no cover


class InMemoryProfileFacts:
    """Dict-backed :class:`ProfileSource` — Default-Implementierung + Fake-Basis
    für Tests (kein Storage-Zugriff, rein In-Memory)."""

    def __init__(self, fakten: Iterable[FaktWert] = ()) -> None:
        self._fakten: dict[str, FaktWert] = {f.feld: f for f in fakten}

    def get_fakt(self, feld: str) -> FaktWert | None:
        return self._fakten.get(feld)

    def get_all(self) -> dict[str, FaktWert]:
        return dict(self._fakten)


def parse_profil_fakten(raw: Any) -> InMemoryProfileFacts:
    """Systemgrenzen-Parser für ``profil_fakten`` (Muster ``_parse_consumption``,
    ``lastgang/capability.py``).

    Akzeptiert ``None``/``{}`` (leere Facts), die Kurzform ``{feld: skalar}``
    (``quelle="profil"``) und die Objektform ``{feld: {wert, quelle?, stand?,
    anker?}}`` — unbekannte Extra-Keys IM Fakt-Objekt werden ignoriert
    (Forward-Compat mit dem Gateway-Wire-Format, das ggf. mehr Felder
    mitschickt als dieses Repo kennt).

    Fail-closed: unbekanntes Feld, ungültiger Wert (gegen
    :data:`PROFIL_FELDER`) oder unbekannte ``quelle`` wirft
    :class:`CapabilityError` — der Gateway schreibt LLM-frei, ein kaputter
    Fakt ist ein Bug, kein Rauschen, das man stillschweigend überspringen darf.
    """
    if raw is None:
        return InMemoryProfileFacts()
    if not isinstance(raw, dict):
        raise CapabilityError(
            "profil_fakten muss ein Objekt {feld: wert} oder "
            "{feld: {wert, quelle?, stand?, anker?}} sein."
        )

    fakten: list[FaktWert] = []
    for feld, roh in raw.items():
        if feld not in PROFIL_FELDER:
            raise CapabilityError(f"profil_fakten: unbekanntes Feld {feld!r}.")

        if isinstance(roh, dict):
            if "wert" not in roh:
                raise CapabilityError(f"profil_fakten[{feld!r}]: Objektform erwartet 'wert'.")
            wert = roh["wert"]
            quelle = roh.get("quelle", "profil")
            stand = roh.get("stand")
            anker = roh.get("anker")
        else:
            wert = roh
            quelle = "profil"
            stand = None
            anker = None

        # E5: Enum-Werte VOR Validierung/FaktWert-Bau kanonisieren (strip +
        # lower) — damit "Gas"/" gas " gleichwertig zu "gas" landen und der
        # gespeicherte FaktWert.wert IMMER kanonisch ist (z.B. für die
        # reconcile.py-Sets {elektrisch, waermepumpe}). Nicht-Strings bleiben
        # unangetastet und damit fail-closed (validiere_fakt_wert lehnt sie
        # unten ab, kein blindes .lower() auf Nicht-Text).
        if PROFIL_FELDER[feld].art == "enum" and isinstance(wert, str):
            wert = wert.strip().lower()

        if quelle not in _GUELTIGE_QUELLEN:
            raise CapabilityError(
                f"profil_fakten[{feld!r}]: unbekannte quelle {quelle!r} "
                f"(erlaubt: {sorted(_GUELTIGE_QUELLEN)})."
            )

        fehler = validiere_fakt_wert(feld, wert)
        if fehler:
            raise CapabilityError(f"profil_fakten[{feld!r}]: {fehler}.")

        try:
            fakten.append(FaktWert(feld=feld, wert=wert, quelle=quelle, stand=stand, anker=anker))
        except ValidationError as exc:
            raise CapabilityError(f"profil_fakten[{feld!r}]: {exc}") from exc

    return InMemoryProfileFacts(fakten)
