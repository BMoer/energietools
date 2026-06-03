# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Guards the LLM-provider *injection* contract of invoice_parser.

energietools bundles no LLM client. ``parse_invoice`` / ``_extract_via_llm``
require an injected provider (Protocol ``llm_protocol.LLMProvider``) and must
raise a clear error when none is supplied — never reach for env vars or a
bundled client. A minimal fake provider proves the injected path is wired.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from energietools.tools.invoice_parser import _extract_via_llm, parse_invoice
from energietools.tools.llm_protocol import LLMProvider


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text_parts = [text]


class _FakeProvider:
    """Satisfies the LLMProvider Protocol; returns a canned JSON response."""

    provider_name = "Fake"

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[dict] = []

    def build_user_content(self, prompt: str, attachments: list[dict]):  # noqa: D102
        return [{"prompt": prompt, "attachments": attachments}]

    def chat(self, *, system, messages, tools, max_tokens, temperature):  # noqa: D102
        self.calls.append({"system": system, "messages": messages})
        return _FakeResponse(json.dumps(self._payload))


def test_fake_provider_is_recognized_by_protocol() -> None:
    assert isinstance(_FakeProvider({}), LLMProvider)


def test_extract_via_llm_requires_injected_provider() -> None:
    with pytest.raises(ValueError, match="injizierten llm_provider"):
        _extract_via_llm(llm_provider=None, text="irgendein Rechnungstext")


def test_extract_via_llm_uses_injected_provider() -> None:
    payload = {"lieferant": "Testenergie", "arbeitspreis_ct_kwh": 12.5}
    provider = _FakeProvider(payload)

    result = _extract_via_llm(llm_provider=provider, text="<invoice>…</invoice>")

    assert result["lieferant"] == "Testenergie"
    assert result["arbeitspreis_ct_kwh"] == 12.5
    assert len(provider.calls) == 1  # the injected provider was actually called


def test_parse_invoice_without_provider_raises(tmp_path: Path) -> None:
    # File exists (so the provider-None guard is reached, not FileNotFoundError).
    f = tmp_path / "rechnung.txt"
    f.write_text("dummy", encoding="utf-8")
    with pytest.raises(ValueError, match="kein llm_provider injiziert"):
        parse_invoice(f, llm_provider=None)
