# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Capability-Rückgrat — die tragende Struktur des Toolkits.

Eine *Capability* ist eine eigenständige, von außen auditierbare Fähigkeit
(Tarifvergleich, Rechnungs-Scan, Lastprofil-Analyse …). Jede Capability trägt
ihre eigene Metadaten (``name``, ``summary``, ``input_schema``) und liefert ein
einheitliches Ergebnis-Envelope (``CapabilityResult``).

Designziele:
- **Eine Form für alles.** Statt loser Funktionen mit je eigener Signatur hat
  jede Fähigkeit dieselbe Oberfläche ``run(**kwargs) -> CapabilityResult``.
- **Auditierbar.** Das Result-Envelope ist deterministisch, JSON-serialisierbar
  und transportiert bei Erfolg die Daten, bei Fehler eine klare Meldung.
- **Selbst-registrierend.** Eine ``CapabilityRegistry`` sammelt Capabilities und
  erzeugt daraus Agent-Tool-Definitionen und CLI-Einträge — neue Fähigkeit
  hinzufügen heißt: Capability registrieren, sonst nichts.

Das Rückgrat hat bewusst keine Abhängigkeit zu LLM-, Storage- oder Netzwerk-
Code, damit es als schlanke Bibliothekskomponente nutzbar bleibt.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class CapabilityResult(BaseModel):
    """Einheitliches Ergebnis-Envelope jeder Capability.

    ``ok`` trennt Erfolg von Fehler; ``data`` trägt die Nutzlast (bei Fehler
    ``None``); ``error`` die nutzerfreundliche Meldung (bei Erfolg ``None``);
    ``meta`` optionale Zusatzinfos (Quelle, Version, Zeitstempel …).
    """

    capability: str = Field(description="Name der ausführenden Capability")
    ok: bool = Field(description="True bei Erfolg, False bei Fehler")
    data: Any | None = Field(default=None, description="Nutzlast (None bei Fehler)")
    error: str | None = Field(default=None, description="Fehlermeldung (None bei Erfolg)")
    meta: dict[str, Any] = Field(default_factory=dict, description="Zusatz-Metadaten")


class CapabilityError(RuntimeError):
    """Eine Capability konnte ihre Eingabe nicht verarbeiten.

    Bewusst geworfen (statt stiller Default-Werte), damit Fehler im Result-
    Envelope sichtbar als ``ok=False`` landen — nie still falsche Daten.
    """


class Capability(ABC):
    """Basis für eine auditierbare Fähigkeit des Toolkits.

    Subklassen setzen die Klassenattribute ``name``, ``summary`` und
    ``input_schema`` (JSON Schema) und implementieren ``_run``. Die öffentliche
    ``run``-Methode kapselt jede Ausführung in ein ``CapabilityResult`` und
    fängt Fehler ab — Aufrufer bekommen nie eine rohe Exception.
    """

    name: str = ""
    summary: str = ""
    input_schema: dict[str, Any] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Abstrakte Zwischenklassen (``_run`` noch nicht implementiert) überspringen.
        # ``__abstractmethods__`` ist hier noch nicht gesetzt (ABCMeta läuft später),
        # daher direkt am Methoden-Flag prüfen.
        if getattr(cls._run, "__isabstractmethod__", False):
            return
        if not cls.name:
            raise TypeError(f"{cls.__name__}: Klassenattribut 'name' fehlt")
        if not cls.summary:
            raise TypeError(f"{cls.__name__}: Klassenattribut 'summary' fehlt")

    @abstractmethod
    def _run(self, **kwargs: Any) -> Any:
        """Eigentliche Logik. Gibt die Nutzlast zurück oder wirft CapabilityError."""

    def run(self, **kwargs: Any) -> CapabilityResult:
        """Führt die Capability aus und verpackt das Ergebnis ins Envelope."""
        try:
            data = self._run(**kwargs)
        except CapabilityError as exc:
            log.warning("Capability %s: %s", self.name, exc)
            return CapabilityResult(capability=self.name, ok=False, error=str(exc))
        except Exception as exc:  # robustes Envelope: nie rohe Exception nach außen
            log.exception("Capability %s unerwartet fehlgeschlagen", self.name)
            return CapabilityResult(
                capability=self.name,
                ok=False,
                error=f"Interner Fehler in {self.name}: {exc}",
            )
        return CapabilityResult(capability=self.name, ok=True, data=data)

    def tool_definition(self) -> dict[str, Any]:
        """LLM-Tool-Definition (Claude/OpenAI-kompatibel) aus den Metadaten."""
        return {
            "name": self.name,
            "description": self.summary,
            "input_schema": self.input_schema,
        }


class FunctionCapability(Capability):
    """Hängt eine bestehende Funktion als Capability ans Rückgrat.

    Erlaubt, vorhandene ``tools/``-Funktionen ohne Umschreiben einheitlich
    verfügbar zu machen. ``target`` ist ein Callable **oder** ein
    ``"modul:funktion"``-Pfad, der **lazy** (erst beim Aufruf) importiert wird —
    so ziehen optionale Schwer-Abhängigkeiten (numpy, fpdf …) nicht schon beim
    Registrieren. Pydantic-Rückgaben werden zu JSON-fähigen Dicts normalisiert.
    """

    name = "function"
    summary = "Funktions-Wrapper"

    def __init__(
        self,
        *,
        name: str,
        summary: str,
        target: str | Any,
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        if not name or not summary:
            raise ValueError("FunctionCapability braucht name und summary")
        self.name = name
        self.summary = summary
        self.input_schema = input_schema or {"type": "object", "properties": {}}
        self._target = target

    def _resolve(self) -> Any:
        if callable(self._target):
            return self._target
        module_path, _, func_name = str(self._target).partition(":")
        if not module_path or not func_name:
            raise CapabilityError(f"Ungültiges target '{self._target}' (erwartet 'modul:funktion')")
        try:
            import importlib

            module = importlib.import_module(module_path)
            fn = getattr(module, func_name)
        except (ImportError, AttributeError) as exc:
            raise CapabilityError(f"target '{self._target}' nicht ladbar: {exc}") from exc
        if not callable(fn):
            raise CapabilityError(f"target '{self._target}': '{func_name}' ist nicht aufrufbar")
        return fn

    @staticmethod
    def _to_jsonable(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if isinstance(value, (list, tuple)):
            return [FunctionCapability._to_jsonable(v) for v in value]
        if isinstance(value, (str, int, float, bool, dict)) or value is None:
            return value
        # Unbekannter Typ: nicht still verschlucken — sichtbar protokollieren.
        log.warning("FunctionCapability: unbekannter Rückgabetyp %s — str()-Fallback", type(value))
        return str(value)

    def _run(self, **kwargs: Any) -> Any:
        return self._to_jsonable(self._resolve()(**kwargs))


class CapabilityRegistry:
    """Sammelt Capabilities und erzeugt daraus Agent-/CLI-Oberflächen."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> Capability:
        """Registriert eine Capability-Instanz. Doppelte Namen sind ein Fehler."""
        if capability.name in self._capabilities:
            raise ValueError(f"Capability '{capability.name}' bereits registriert")
        self._capabilities[capability.name] = capability
        log.debug("Capability registriert: %s", capability.name)
        return capability

    def get(self, name: str) -> Capability:
        """Capability per Name. Wirft KeyError, wenn unbekannt."""
        if name not in self._capabilities:
            raise KeyError(f"Unbekannte Capability: {name}")
        return self._capabilities[name]

    def all(self) -> list[Capability]:
        """Alle registrierten Capabilities (Registrierungsreihenfolge)."""
        return list(self._capabilities.values())

    @property
    def names(self) -> list[str]:
        return list(self._capabilities)

    def tool_definitions(self) -> list[dict[str, Any]]:
        """LLM-Tool-Definitionen aller Capabilities."""
        return [c.tool_definition() for c in self._capabilities.values()]
