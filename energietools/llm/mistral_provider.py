# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Mistral LLM Provider — uses OpenAI-compatible API."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from energietools.llm.types import LLMContentBlock, LLMResponse, LLMTextBlock, LLMToolUseBlock, LLMUsage

log = logging.getLogger(__name__)

_RETRY_DELAYS = (5, 15, 45)  # seconds — exponential backoff for 429s

_MISTRAL_BASE_URL = "https://api.mistral.ai/v1"

# Models with vision (multimodal) support
_VISION_MODELS = {"pixtral-large-latest", "pixtral-12b-2409", "mistral-small-latest"}


class MistralProvider:
    """Mistral AI provider — OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str) -> None:
        import openai

        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=_MISTRAL_BASE_URL,
        )
        self._api_key = api_key
        self._model = model

    @property
    def provider_name(self) -> str:
        return "mistral"

    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Send request to Mistral Chat Completions API."""
        from energietools.llm.openai_provider import _convert_messages_to_openai

        oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        oai_messages.extend(_convert_messages_to_openai(messages))

        oai_tools = (
            [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ]
            if tools
            else None
        )

        # Auto-detect if messages contain image content → need vision model
        effective_model = self._model
        if self._model not in _VISION_MODELS:
            for msg in oai_messages:
                content = msg.get("content", "")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "image_url":
                            effective_model = "pixtral-large-latest"
                            log.info("Auto-switching to %s for vision request", effective_model)
                            break
                if effective_model != self._model:
                    break

        kwargs: dict[str, Any] = {
            "model": effective_model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if oai_tools:
            kwargs["tools"] = oai_tools
        elif not oai_tools and any(
            kw in system.lower() for kw in ("json", "extrahiere", "extract")
        ):
            # Enable JSON mode for structured extraction tasks (no tools)
            kwargs["response_format"] = {"type": "json_object"}

        response = self._completions_with_retry(**kwargs)
        choice = response.choices[0]

        blocks: list[LLMContentBlock] = []
        if choice.message.content:
            blocks.append(LLMTextBlock(text=choice.message.content))

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                blocks.append(LLMToolUseBlock(
                    id=tc.id,
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                ))

        stop = "tool_use" if choice.finish_reason == "tool_calls" else "end_turn"
        usage = LLMUsage(
            input_tokens=getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            output_tokens=getattr(response.usage, "completion_tokens", 0) if response.usage else 0,
        )
        return LLMResponse(content=tuple(blocks), stop_reason=stop, usage=usage)

    def _completions_with_retry(self, **kwargs: Any) -> Any:
        """Call Mistral API with exponential backoff on 429 rate limit errors."""
        import openai

        for attempt, delay in enumerate((*_RETRY_DELAYS, 0)):
            try:
                return self._client.chat.completions.create(**kwargs)
            except openai.RateLimitError:
                if delay == 0:
                    raise
                log.warning(
                    "Rate limit (429), Versuch %d/%d — warte %ds",
                    attempt + 1,
                    len(_RETRY_DELAYS),
                    delay,
                )
                time.sleep(delay)
        raise RuntimeError("Retry exhausted")  # pragma: no cover

    def build_user_content(
        self,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> str | list[dict[str, Any]]:
        """Build Mistral-specific user content with optional attachments.

        Mistral supports vision (images) on Pixtral models.
        PDFs and tabular files are extracted to text.
        """
        if not attachments:
            return text

        content: list[dict[str, Any]] = []
        for attachment in attachments:
            media_type = attachment.get("media_type", "")
            data = attachment.get("data", "")
            if not data:
                continue

            if media_type == "application/pdf":
                from energietools.llm.openai_provider import _pdf_b64_to_text
                pdf_text = _pdf_b64_to_text(data)
                file_name = attachment.get("file_name", "document.pdf")
                content.append({
                    "type": "text",
                    "text": f"[Inhalt von {file_name}]\n{pdf_text}",
                })
            elif media_type.startswith("image/"):
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{data}",
                    },
                })
            elif _is_tabular(media_type, attachment.get("file_name", "")):
                from energietools.llm.openai_provider import _decode_tabular_file
                file_name = attachment.get("file_name", "datei")
                file_text = _decode_tabular_file(data, media_type, file_name)
                content.append({
                    "type": "text",
                    "text": f"[Inhalt von {file_name}]\n{file_text}",
                })

        has_docs = len(content) > 0
        if has_docs:
            text = (
                f"{text}\n\n[Die angehängten Dateien sind in dieser Nachricht eingebettet. "
                "Verwende das passende Tool (z.B. parse_invoice) um sie strukturiert zu analysieren.]"
            )

        content.append({"type": "text", "text": text})
        return content

    def build_tool_results_message(
        self,
        tool_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Mistral: separate tool-role messages (OpenAI-compatible)."""
        return [
            {
                "role": "tool",
                "tool_call_id": tr["tool_use_id"],
                "content": tr["content"],
            }
            for tr in tool_results
        ]

    def response_to_history(self, response: LLMResponse) -> dict[str, Any]:
        """Convert response to OpenAI-compatible dict for conversation history."""
        result: dict[str, Any] = {"role": "assistant"}
        text_parts = response.text_parts
        result["content"] = "\n".join(text_parts) if text_parts else None

        tool_uses = response.tool_uses
        if tool_uses:
            result["tool_calls"] = [
                {
                    "id": t.id,
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "arguments": json.dumps(t.input),
                    },
                }
                for t in tool_uses
            ]
        return result


def _is_tabular(media_type: str, file_name: str) -> bool:
    """Check if the file is a CSV or Excel file."""
    return (
        media_type in (
            "text/csv",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        or file_name.endswith((".csv", ".xlsx", ".xls"))
    )
