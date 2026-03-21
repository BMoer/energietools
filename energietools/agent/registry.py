# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Generic Tool Registry — reusable, no business-logic dependencies.

This module contains only the ToolRegistry class and ToolDefinition type.
It has no imports from energietools.config, energietools.storage, energietools.prompts,
or any other application-specific module, making it suitable for use as a
standalone library component.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from energietools.agent.types import ToolDefinition

log = logging.getLogger(__name__)


class ToolRegistry:
    """Registry für Agent-Tools.

    Mappt Tool-Namen auf Python-Funktionen und generiert
    Claude API tool definitions.
    """

    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        """Registriere ein Tool mit Claude API Definition und Handler."""
        self._definitions[name] = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
        )
        self._handlers[name] = handler
        log.debug("Tool registriert: %s", name)

    def definitions(self) -> list[dict[str, Any]]:
        """Claude API tool definitions zurückgeben."""
        return [
            {
                "name": defn.name,
                "description": defn.description,
                "input_schema": defn.input_schema,
            }
            for defn in self._definitions.values()
        ]

    def execute(
        self, name: str, input_data: dict[str, Any], *, timeout: int = 120,
    ) -> str:
        """Tool ausführen und Ergebnis als String zurückgeben.

        Validates input against the registered JSON Schema (requires optional
        ``jsonschema`` package) and enforces a per-call execution timeout.
        """
        handler = self._handlers.get(name)
        if handler is None:
            log.warning("Unbekanntes Tool aufgerufen: %s", name)
            return "Fehler: Unbekanntes Tool aufgerufen."

        # Validate input against JSON Schema (if defined)
        defn = self._definitions.get(name)
        if defn and defn.input_schema:
            try:
                import jsonschema
                jsonschema.validate(input_data, defn.input_schema)
            except ImportError:
                log.debug("jsonschema not installed — skipping validation")
            except jsonschema.ValidationError as ve:
                log.warning("Schema-Validierung fehlgeschlagen für %s: %s", name, ve.message)
                return f"Fehler bei {name}: Ungültige Eingabe — {ve.message}"

        log.info("Tool ausführen: %s", name)
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(handler, **input_data)
                result = future.result(timeout=timeout)
            # Pydantic-Models automatisch serialisieren
            if hasattr(result, "model_dump_json"):
                return result.model_dump_json(indent=2)
            return str(result)
        except concurrent.futures.TimeoutError:
            log.error("Tool %s hat Timeout überschritten (%ds)", name, timeout)
            return f"Fehler bei {name}: Zeitüberschreitung nach {timeout}s."
        except Exception as e:
            log.exception("Tool %s fehlgeschlagen: %s", name, e)
            return f"Fehler bei {name}: Das Tool konnte nicht ausgeführt werden."

    def copy_tool(self, name: str, source: ToolRegistry) -> bool:
        """Copy a single tool (definition + handler) from another registry.

        Returns True if the tool was found and copied, False otherwise.
        """
        if name not in source._definitions or name not in source._handlers:
            return False
        self._definitions[name] = source._definitions[name]
        self._handlers[name] = source._handlers[name]
        log.debug("Tool kopiert: %s", name)
        return True

    @property
    def tool_names(self) -> list[str]:
        return list(self._definitions.keys())
