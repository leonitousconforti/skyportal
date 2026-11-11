"""Claude, through Anthropic's SDK, for a user whose AI connection is Anthropic.

The assistant keeps its conversation in OpenAI's chat-completions shape, so this
translates it to the Messages API and back.
"""

import contextlib
import json
import socket
import threading
import time

import anthropic
import httpx2

DEFAULT_BASE_URL = "https://api.anthropic.com"
MAX_TOKENS = 16000
# Claude's own content for an assistant turn, replayed unchanged since an edited
# thinking block is refused.
RAW_CONTENT = "anthropic_content"
# Read only when building a Messages API request.
PRIVATE_KEYS = (RAW_CONTENT, "is_error")
DECLINED = "The model declined to answer that."


def client(api_key, base_url=None, timeout=60, max_retries=0):
    """A client that sends `api_key` to `base_url` and nowhere else.

    Both are always passed: left out, the SDK falls back to this server's own
    ANTHROPIC_* credentials and base URL.
    """
    if not api_key:
        raise ValueError("An Anthropic connection needs an API key")
    return anthropic.Anthropic(
        api_key=api_key,
        base_url=base_url or DEFAULT_BASE_URL,
        timeout=timeout,
        max_retries=max_retries,
        # A redirect would take the key past the base_url check.
        http_client=anthropic.DefaultHttpxClient(follow_redirects=False),
    )


def public(message):
    """`message` without the fields only a Messages API request reads."""
    return {key: value for key, value in message.items() if key not in PRIVATE_KEYS}


def _blocks(message):
    if message["role"] == "tool":
        block = {"type": "tool_result", "tool_use_id": message["tool_call_id"]}
        if message.get("content"):
            block["content"] = message["content"]
        if message.get("is_error"):
            block["is_error"] = True
        return [block]
    if message.get(RAW_CONTENT):
        return message[RAW_CONTENT]
    blocks = []
    if message.get("content"):
        blocks.append({"type": "text", "text": message["content"]})
    for call in message.get("tool_calls") or []:
        blocks.append(
            {
                "type": "tool_use",
                "id": call["id"],
                "name": call["function"]["name"],
                "input": json.loads(call["function"]["arguments"] or "{}"),
            }
        )
    return blocks


def request(messages, tools):
    """The system, messages and tools of a Messages API request for an
    OpenAI-shaped conversation and tool list."""
    system, turns = [], []
    for message in messages:
        if message["role"] == "system":
            system.append(message["content"])
            continue
        role = "assistant" if message["role"] == "assistant" else "user"
        blocks = _blocks(message)
        if not blocks:
            continue
        # Turns must alternate, so a tool's result joins the others and any
        # text after them in one user turn.
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] = [*turns[-1]["content"], *blocks]
        else:
            turns.append({"role": role, "content": blocks})
    # The first turn must be the user's.
    while turns and turns[0]["role"] == "assistant":
        turns.pop(0)

    params = {"messages": turns}
    if system:
        params["system"] = "\n\n".join(system)
    if tools:
        params["tools"] = [
            {
                "name": function["name"],
                "description": function.get("description", ""),
                "input_schema": function.get("parameters") or {"type": "object"},
            }
            for function in (tool["function"] for tool in tools)
        ]
    return params


def reply(message):
    """The OpenAI-shaped assistant turn for a Messages API `message`."""
    if message.stop_reason == "refusal":
        return {"role": "assistant", "content": DECLINED}
    content = [block.to_dict(mode="json") for block in message.content]
    turn = {
        "role": "assistant",
        "content": "".join(b["text"] for b in content if b["type"] == "text") or None,
        RAW_CONTENT: content,
    }
    calls = [
        {
            "id": block["id"],
            "type": "function",
            "function": {
                "name": block["name"],
                "arguments": json.dumps(block["input"]),
            },
        }
        for block in content
        if block["type"] == "tool_use"
    ]
    # Calls run only when their turn finished asking for them: one cut short
    # still parses, from part of its input.
    if calls and message.stop_reason == "tool_use":
        turn["tool_calls"] = calls
    return turn


def streamed(client, deadline, **params):
    """The message `client` streams for `params`, or APITimeoutError once the
    `deadline` (time.monotonic) passes.

    The client's timeout bounds each read, not their sum, and a server can send
    one byte at a time just inside it, so the socket is shut at the deadline.
    """
    cut = threading.Event()
    with client.messages.stream(max_tokens=MAX_TOKENS, **params) as stream:

        def shut():
            cut.set()
            with contextlib.suppress(Exception):
                network = stream.response.extensions["network_stream"]
                network.get_extra_info("socket").shutdown(socket.SHUT_RDWR)

        timer = threading.Timer(max(deadline - time.monotonic(), 0), shut)
        timer.daemon = True
        timer.start()
        try:
            message = stream.get_final_message()
        except httpx2.TransportError as exc:
            # A connection lost partway through, which the SDK leaves unwrapped.
            if not cut.is_set():
                raise anthropic.APIConnectionError(
                    request=stream.response.request
                ) from exc
        except Exception:
            if not cut.is_set():
                raise
        finally:
            timer.cancel()
        if cut.is_set():
            raise anthropic.APITimeoutError(request=stream.response.request)
        if message.stop_reason is None:
            # The stream ended before Claude said why it stopped.
            raise anthropic.APIConnectionError(request=stream.response.request)
    return message


def summary(api_key, base_url, model, system, content, timeout=60):
    """Claude's summary of `content`, given up on once `timeout` passes, or
    ValueError when it stopped short, was declined or the provider failed it.

    How long it is comes from the prompt: recent models refuse sampling settings.
    """
    try:
        with client(api_key, base_url, timeout=timeout) as claude:
            message = streamed(
                claude,
                time.monotonic() + timeout,
                model=model,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
    except anthropic.APIStatusError as exc:
        # Not its words: a provider may echo part of the key.
        raise ValueError(
            f"the provider answered with HTTP {exc.status_code}"
            if exc.status_code >= 300
            else "the provider reported an error partway through"
        ) from None
    if message.stop_reason == "refusal":
        raise ValueError("the model declined to write it")
    if message.stop_reason != "end_turn":
        raise ValueError(f"it stopped short ({message.stop_reason})")
    text = "".join(b.text for b in message.content if b.type == "text").strip()
    if not text:
        raise ValueError("the model returned no text")
    return text
