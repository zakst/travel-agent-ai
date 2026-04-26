from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import agent
from agent import SYSTEM_PROMPT, run_agent
from tools import TOOL_SCHEMAS


def make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def make_tool_use_block(name: str, tool_input: dict, tool_id: str = "tu_1"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = tool_input
    block.id = tool_id
    return block


def make_response(content_blocks: list, stop_reason: str):
    response = MagicMock()
    response.content = content_blocks
    response.stop_reason = stop_reason
    return response


def make_anthropic_mock(responses: list):
    client = MagicMock()
    client.messages.create = MagicMock(side_effect=list(responses))
    return client


def test_agent_returns_immediately_on_end_turn():
    client = make_anthropic_mock(
        [make_response([make_text_block("Done.")], "end_turn")]
    )
    result = run_agent("plan a trip", verbose=False, client=client)
    assert result == "Done."
    assert client.messages.create.call_count == 1


def test_agent_dispatches_tool_call_then_returns(monkeypatch):
    captured: dict = {}

    def fake_execute(name, tool_input):
        captured["name"] = name
        captured["input"] = tool_input
        return '{"daily": []}'

    monkeypatch.setattr(agent, "execute_tool", fake_execute)
    client = make_anthropic_mock(
        [
            make_response(
                [
                    make_tool_use_block(
                        "get_weather_forecast",
                        {
                            "city": "Tokyo",
                            "start_date": "2026-06-15",
                            "end_date": "2026-06-21",
                        },
                        "tu_42",
                    )
                ],
                "tool_use",
            ),
            make_response([make_text_block("All set.")], "end_turn"),
        ]
    )
    result = run_agent("test", verbose=False, client=client)
    assert result == "All set."
    assert captured["name"] == "get_weather_forecast"
    assert captured["input"]["city"] == "Tokyo"

    second_call = client.messages.create.call_args_list[1]
    sent_messages = second_call.kwargs["messages"]
    assert sent_messages[-1]["role"] == "user"
    tr_block = sent_messages[-1]["content"][0]
    assert tr_block["type"] == "tool_result"
    assert tr_block["tool_use_id"] == "tu_42"
    assert tr_block["content"] == '{"daily": []}'


def test_agent_handles_multiple_tool_calls_in_one_turn(monkeypatch):
    calls: list[str] = []

    def fake_execute(name, _input):
        calls.append(name)
        return '{"ok": true}'

    monkeypatch.setattr(agent, "execute_tool", fake_execute)
    client = make_anthropic_mock(
        [
            make_response(
                [
                    make_tool_use_block(
                        "search_flights",
                        {
                            "origin": "SFO",
                            "destination": "NRT",
                            "depart_date": "2026-06-15",
                        },
                        "tu_a",
                    ),
                    make_tool_use_block(
                        "search_hotels",
                        {
                            "city": "Tokyo",
                            "check_in": "2026-06-15",
                            "check_out": "2026-06-22",
                        },
                        "tu_b",
                    ),
                ],
                "tool_use",
            ),
            make_response([make_text_block("Picked.")], "end_turn"),
        ]
    )
    result = run_agent("test", verbose=False, client=client)
    assert calls == ["search_flights", "search_hotels"]
    assert result == "Picked."

    last_user = client.messages.create.call_args_list[1].kwargs["messages"][-1]
    assert last_user["role"] == "user"
    assert len(last_user["content"]) == 2
    assert [b["tool_use_id"] for b in last_user["content"]] == ["tu_a", "tu_b"]


def test_agent_raises_on_max_iterations(monkeypatch):
    monkeypatch.setattr(agent, "execute_tool", lambda *a, **k: "{}")

    def loop_response(**_kwargs):
        return make_response(
            [
                make_tool_use_block(
                    "get_weather_forecast",
                    {"city": "X", "start_date": "2026-06-15", "end_date": "2026-06-16"},
                    "tu_loop",
                )
            ],
            "tool_use",
        )

    client = MagicMock()
    client.messages.create = MagicMock(side_effect=loop_response)
    with pytest.raises(RuntimeError, match="max_iterations"):
        run_agent("test", verbose=False, client=client, max_iterations=3)
    assert client.messages.create.call_count == 3


def test_agent_passes_system_prompt_and_tools():
    client = make_anthropic_mock(
        [make_response([make_text_block("hi")], "end_turn")]
    )
    run_agent("test", verbose=False, client=client)
    call = client.messages.create.call_args_list[0]
    assert call.kwargs["system"] == SYSTEM_PROMPT
    assert call.kwargs["tools"] == TOOL_SCHEMAS


def test_agent_verbose_false_silences_output(capsys):
    client = make_anthropic_mock(
        [make_response([make_text_block("done")], "end_turn")]
    )
    run_agent("test", verbose=False, client=client)
    captured = capsys.readouterr()
    assert captured.out == ""
