"""How the assistant's OpenAI-shaped conversation is put to Claude, and back."""

import contextlib
import copy
import json
import socket
import threading
import time

import anthropic
import pytest

from skyportal.utils import anthropic_chat
from skyportal.utils.anthropic_chat import RAW_CONTENT, reply, request

TOOL = {
    "type": "function",
    "function": {
        "name": "get_source",
        "description": "Look up a source.",
        "parameters": {"type": "object", "properties": {"obj_id": {"type": "string"}}},
    },
}


def _message(content, stop_reason="end_turn"):
    return anthropic.types.Message.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )


THINKING = {"type": "thinking", "thinking": "", "signature": "SIG"}
TOOL_USE = {
    "type": "tool_use",
    "id": "toolu_1",
    "name": "get_source",
    "input": {"obj_id": "ZTF1"},
}


def test_tools_and_system_take_the_messages_api_shape():
    params = request(
        [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "What is ZTF1?"},
        ],
        [TOOL],
    )
    assert params["system"] == "Be brief."
    assert params["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "What is ZTF1?"}]}
    ]
    assert params["tools"] == [
        {
            "name": "get_source",
            "description": "Look up a source.",
            "input_schema": TOOL["function"]["parameters"],
        }
    ]
    assert "tools" not in request([{"role": "user", "content": "hi"}], [])


def test_a_tool_call_becomes_a_tool_use_and_its_results_one_user_turn():
    call = {
        "id": "toolu_1",
        "type": "function",
        "function": {"name": "get_source", "arguments": '{"obj_id": "ZTF1"}'},
    }
    other = {**call, "id": "toolu_2"}
    params = request(
        [
            {"role": "user", "content": "What is ZTF1?"},
            {"role": "assistant", "content": "Looking.", "tool_calls": [call, other]},
            {"role": "tool", "tool_call_id": "toolu_1", "content": "{}"},
            {
                "role": "tool",
                "tool_call_id": "toolu_2",
                "content": "tool get_source failed",
                "is_error": True,
            },
            {"role": "user", "content": "Answer now."},
        ],
        [TOOL],
    )
    user, assistant, results = params["messages"]
    assert user["role"] == "user"
    assert assistant == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Looking."},
            {**TOOL_USE},
            {**TOOL_USE, "id": "toolu_2"},
        ],
    }
    # Results first, then any text, all in the one user turn that follows.
    assert results == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": "{}"},
            {
                "type": "tool_result",
                "tool_use_id": "toolu_2",
                "content": "tool get_source failed",
                "is_error": True,
            },
            {"type": "text", "text": "Answer now."},
        ],
    }


def test_turns_alternate_and_open_with_the_user():
    params = request(
        [
            {"role": "system", "content": "s"},
            {"role": "assistant", "content": "An earlier answer."},
            {"role": "user", "content": "one"},
            {"role": "user", "content": "two"},
        ],
        [],
    )
    assert params["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "one"},
                {"type": "text", "text": "two"},
            ],
        }
    ]


def test_claudes_own_content_is_replayed_unchanged():
    content = [THINKING, {"type": "text", "text": "Looking."}, TOOL_USE]
    turn = reply(_message(content, stop_reason="tool_use"))
    assert turn["content"] == "Looking."
    assert turn["tool_calls"] == [
        {
            "id": "toolu_1",
            "type": "function",
            "function": {"name": "get_source", "arguments": '{"obj_id": "ZTF1"}'},
        }
    ]
    kept = copy.deepcopy(turn[RAW_CONTENT])
    tool = {"role": "tool", "tool_call_id": "toolu_1", "content": "{}"}
    params = request([{"role": "user", "content": "q"}, turn, tool], [TOOL])
    # The thinking block is sent back exactly as it came.
    assert params["messages"][1] == {"role": "assistant", "content": kept}
    assert params["messages"][1]["content"][0] == THINKING
    assert turn[RAW_CONTENT] == kept


def test_claudes_own_content_never_reaches_an_openai_compatible_server():
    from skyportal.utils.assistant import chat_payload

    turn = reply(_message([THINKING, TOOL_USE], stop_reason="tool_use"))
    tool = {"role": "tool", "tool_call_id": "toolu_1", "content": "x", "is_error": True}
    payload = chat_payload("m", [turn, tool], [TOOL], user_key=True)
    assert RAW_CONTENT not in json.dumps(payload)
    assert "is_error" not in json.dumps(payload)
    assert payload["messages"][0]["tool_calls"] == turn["tool_calls"]


def test_a_refusal_is_not_read_as_an_answer():
    turn = reply(_message([{"type": "text", "text": "Sure, "}, TOOL_USE], "refusal"))
    assert turn == {"role": "assistant", "content": anthropic_chat.DECLINED}


@pytest.mark.parametrize(
    "stop_reason", ["max_tokens", "model_context_window_exceeded", None]
)
def test_a_tool_call_cut_short_is_not_run(stop_reason):
    turn = reply(_message([TOOL_USE], stop_reason=stop_reason))
    assert "tool_calls" not in turn


def test_the_client_never_falls_back_on_the_servers_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-operator")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "operator-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://operator.example")

    for key in ("", None):
        with pytest.raises(ValueError):
            anthropic_chat.client(key)

    client = anthropic_chat.client("sk-ant-user")
    assert client.api_key == "sk-ant-user"
    assert client.auth_token is None
    assert "operator" not in json.dumps(client.auth_headers)
    assert str(client.base_url).startswith("https://api.anthropic.com")
    assert client.max_retries == 0

    client = anthropic_chat.client("sk-ant-user", "https://llm.example/anthropic")
    assert str(client.base_url).startswith("https://llm.example/anthropic")


def _serve(respond):
    """A local server answering one request with `respond(connection)`."""
    server = socket.create_server(("127.0.0.1", 0))

    def run():
        connection, _ = server.accept()
        with connection, contextlib.suppress(OSError):
            connection.recv(65536)
            respond(connection)

    threading.Thread(target=run, daemon=True).start()
    return server, f"http://127.0.0.1:{server.getsockname()[1]}"


def _events(*events):
    return b"".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
        for event in events
    )


# A streamed tool call, up to the message_delta that says why Claude stopped.
TOOL_CALL_EVENTS = [
    {
        "type": "message_start",
        "message": {**_message([]).to_dict(mode="json"), "stop_reason": None},
    },
    {"type": "content_block_start", "index": 0, "content_block": THINKING},
    {"type": "content_block_stop", "index": 0},
    {
        "type": "content_block_start",
        "index": 1,
        "content_block": {**TOOL_USE, "input": {}},
    },
    {
        "type": "content_block_delta",
        "index": 1,
        "delta": {"type": "input_json_delta", "partial_json": '{"obj_id": "ZTF1"}'},
    },
    {"type": "content_block_stop", "index": 1},
]


def _stream(*events):
    """The message streamed from a local server sending `events`, then closing."""
    body = _events(*events)
    server, url = _serve(
        lambda connection: connection.sendall(
            b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\n"
            + f"content-length: {len(body)}\r\n\r\n".encode()
            + body
        )
    )
    try:
        return anthropic_chat.streamed(
            anthropic_chat.client("k", url, timeout=5),
            time.monotonic() + 5,
            model="m",
            messages=[{"role": "user", "content": [{"type": "text", "text": "q"}]}],
        )
    finally:
        server.close()


def test_a_streamed_tool_call_is_put_back_together():
    message = _stream(
        *TOOL_CALL_EVENTS,
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use", "stop_sequence": None},
            "usage": {"output_tokens": 5},
        },
        {"type": "message_stop"},
    )
    turn = reply(message)
    assert turn[RAW_CONTENT] == [THINKING, TOOL_USE]
    assert json.loads(turn["tool_calls"][0]["function"]["arguments"]) == {
        "obj_id": "ZTF1"
    }


def test_a_stream_that_ends_before_claude_stops_is_a_lost_connection():
    # Its tool input would otherwise be read, partially, as complete.
    with pytest.raises(anthropic.APIConnectionError):
        _stream(*TOOL_CALL_EVENTS[:-1])


def test_a_stream_that_drips_is_cut_off_at_the_deadline():
    def drip(connection):
        connection.sendall(
            b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\n"
            b"content-length: 100000\r\n\r\n"
        )
        # Each byte comes well within the read timeout.
        for _ in range(1000):
            connection.sendall(b":\n")
            time.sleep(0.1)

    server, url = _serve(drip)
    started = time.monotonic()
    with pytest.raises(anthropic.APITimeoutError):
        anthropic_chat.streamed(
            anthropic_chat.client("k", url, timeout=5),
            time.monotonic() + 0.5,
            model="m",
            messages=[{"role": "user", "content": [{"type": "text", "text": "q"}]}],
        )
    assert time.monotonic() - started < 3
    server.close()
