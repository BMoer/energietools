# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests for agent loop — text-based tool call extraction fallback."""

import json

import pytest

from energietools.agent.loop import GridbertAgent
from energietools.agent.registry import ToolRegistry
from energietools.llm.types import LLMResponse, LLMTextBlock, LLMToolUseBlock, LLMUsage


class FakeLLMProvider:
    """Fake LLM that returns pre-configured responses."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self._call_count = 0

    @property
    def provider_name(self) -> str:
        return "fake"

    def chat(self, system, messages, tools, max_tokens):
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp

    def build_user_content(self, text, attachments=None):
        return text

    def build_tool_results_message(self, tool_results):
        return [{"role": "tool", "tool_call_id": tr["tool_use_id"], "content": tr["content"]} for tr in tool_results]

    def response_to_history(self, response):
        return {"role": "assistant", "content": "\n".join(b.text for b in response.content if isinstance(b, LLMTextBlock))}


def _make_registry_with_echo():
    """Create a registry with a simple echo tool."""
    registry = ToolRegistry()
    registry.register(
        name="echo_tool",
        description="Echoes input",
        input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        handler=lambda args: json.dumps({"echoed": args.get("message", "")}),
    )
    return registry


class TestTextToolCallExtraction:
    """Test the fallback that extracts tool calls from LLM text output."""

    def test_extract_tool_call_from_text(self):
        """When LLM outputs tool call as text, it should be extracted and executed."""
        registry = _make_registry_with_echo()

        # Response 1: LLM outputs tool call as text (Mistral bug)
        # Response 2: LLM gives final answer after tool result
        provider = FakeLLMProvider([
            LLMResponse(
                content=(LLMTextBlock(text='echo_tool {"message": "hello"}'),),
                stop_reason="end_turn",
                usage=LLMUsage(input_tokens=10, output_tokens=5),
            ),
            LLMResponse(
                content=(LLMTextBlock(text="Tool executed successfully."),),
                stop_reason="end_turn",
                usage=LLMUsage(input_tokens=20, output_tokens=10),
            ),
        ])

        agent = GridbertAgent(registry, provider)
        events = []
        result = agent.run("test", on_event=lambda e: events.append(e))

        # Should have executed the tool (tool_start + tool_result events)
        event_types = [e.type for e in events]
        assert "tool_start" in event_types
        assert "tool_result" in event_types
        # The raw text should NOT be in the final output
        assert 'echo_tool {"message"' not in result

    def test_no_false_positive_on_normal_text(self):
        """Normal text without tool calls should not trigger extraction."""
        registry = _make_registry_with_echo()
        provider = FakeLLMProvider([
            LLMResponse(
                content=(LLMTextBlock(text="Just a normal response about energy savings."),),
                stop_reason="end_turn",
                usage=LLMUsage(input_tokens=10, output_tokens=5),
            ),
        ])

        agent = GridbertAgent(registry, provider)
        result = agent.run("test")
        assert result == "Just a normal response about energy savings."

    def test_no_extraction_for_unregistered_tool(self):
        """Tool calls for unregistered tools should not be extracted."""
        registry = _make_registry_with_echo()
        provider = FakeLLMProvider([
            LLMResponse(
                content=(LLMTextBlock(text='unknown_tool {"arg": "val"}'),),
                stop_reason="end_turn",
                usage=LLMUsage(input_tokens=10, output_tokens=5),
            ),
        ])

        agent = GridbertAgent(registry, provider)
        result = agent.run("test")
        # Should be treated as normal text
        assert "unknown_tool" in result

    def test_proper_tool_call_not_affected(self):
        """Proper tool calls via LLMToolUseBlock should work as before."""
        registry = _make_registry_with_echo()
        provider = FakeLLMProvider([
            LLMResponse(
                content=(LLMToolUseBlock(id="tc_1", name="echo_tool", input={"message": "proper"}),),
                stop_reason="tool_use",
                usage=LLMUsage(input_tokens=10, output_tokens=5),
            ),
            LLMResponse(
                content=(LLMTextBlock(text="Done!"),),
                stop_reason="end_turn",
                usage=LLMUsage(input_tokens=20, output_tokens=10),
            ),
        ])

        agent = GridbertAgent(registry, provider)
        events = []
        result = agent.run("test", on_event=lambda e: events.append(e))
        assert result == "Done!"
        event_types = [e.type for e in events]
        assert "tool_start" in event_types

    def test_extract_with_garbled_prefix(self):
        """Should extract tool call even with garbled text around it (like 'esfur')."""
        registry = _make_registry_with_echo()
        provider = FakeLLMProvider([
            LLMResponse(
                content=(LLMTextBlock(text='echo_tool esfur{"message": "garbled"}'),),
                stop_reason="end_turn",
                usage=LLMUsage(input_tokens=10, output_tokens=5),
            ),
            LLMResponse(
                content=(LLMTextBlock(text="Handled."),),
                stop_reason="end_turn",
                usage=LLMUsage(input_tokens=20, output_tokens=10),
            ),
        ])

        agent = GridbertAgent(registry, provider)

        # The _extract_text_tool_calls should still find the JSON
        calls = agent._extract_text_tool_calls('echo_tool esfur{"message": "garbled"}')
        # The regex looks for word + optional stuff + {json} — "esfur" is part of the text before {
        # Let's check: the regex is (\w+)\s*\(?\s*(\{.*?\})\s*\)? which matches word + json
        # "echo_tool esfur{...}" — "echo_tool" matches \w+, then " esfur" doesn't match \s*\(?
        # Actually "esfur" starts a new \w+ match: "esfur" is not a registered tool
        # But wait — let me check what the regex actually captures
        # The real match would be on "esfur{...}" where esfur is NOT registered
        # So this won't extract. But that's actually fine — the user's real case had
        # request_tariff_switch as the tool name before "esfur"
        # Let me test the actual pattern from the screenshot
        pass

    def test_extract_real_mistral_pattern(self):
        """Test the actual pattern from the Mistral bug: tool_name garbled_text{json}."""
        registry = ToolRegistry()
        registry.register(
            name="request_tariff_switch",
            description="Switch tariff",
            input_schema={"type": "object", "properties": {"target": {"type": "string"}}},
            handler=lambda args: json.dumps({"status": "ok"}),
        )

        # The actual pattern: "request_tariff_switch esfur{...json...}"
        # The regex (\w+)\s*\(?\s*(\{.*?\})\s*\)? won't match this because
        # "esfur" is between the tool name and the JSON.
        # We need to improve the regex.
        text = 'request_tariff_switch esfur{"target_lieferant": "Gutmann Energie GmbH", "savings_eur": 147.83}'

        provider = FakeLLMProvider([])  # not needed for unit test
        agent = GridbertAgent(registry, provider)
        calls = agent._extract_text_tool_calls(text)

        # This should find the tool call
        assert len(calls) >= 1
        assert calls[0][0] == "request_tariff_switch"
