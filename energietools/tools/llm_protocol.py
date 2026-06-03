# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Das LLM-Provider-Protokoll — die Naht zwischen Toolkit und LLM-Client.

energietools bündelt **keinen** konkreten LLM-Client. Fähigkeiten, die ein LLM
brauchen (derzeit nur der Rechnungs-Scan ``invoice_parser``), bekommen einen
Provider von außen *injiziert*. Der konkrete Client (Claude, Mistral, ein
lokales Modell …) lebt in der aufrufenden Anwendung — z.B. in gridbert.

Hier steht nur der minimale, ducktyp-fähige Vertrag, den ein injizierter Provider
erfüllen muss. So bleibt der Open-Source-Kern frei von Provider-SDKs und
API-Schlüsseln, und der Audit-Pfad (welche Zahl kommt woher) wird nicht durch
einen versteckten Netzwerk-Call verwässert.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMResponse(Protocol):
    """Antwort eines LLM-Calls. Nur ``text_parts`` wird konsumiert."""

    text_parts: list[str]


@runtime_checkable
class LLMProvider(Protocol):
    """Minimaler Vertrag eines injizierten LLM-Providers.

    Ein Aufrufer (z.B. gridbert) reicht ein Objekt mit dieser Oberfläche in
    ``invoice_parser.parse_invoice(..., llm_provider=...)`` hinein.
    """

    #: Anzeigename für Logs/Backends (z.B. "Claude", "Mistral").
    provider_name: str

    def build_user_content(self, prompt: str, attachments: list[dict[str, Any]]) -> Any:
        """Baut den ``content`` einer User-Nachricht inkl. Bild-Anhängen.

        Jeder Anhang ist ein Dict ``{"media_type": str, "data": <base64-str>,
        "file_name": str}``. Rückgabe ist, was ``chat`` als Message-``content``
        akzeptiert (Provider-spezifisch).
        """
        ...

    def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[Any],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Führt einen Chat-Completion-Call aus und liefert eine ``LLMResponse``."""
        ...
