import contextlib
import json
import re
import threading
import time

import anthropic
import requests

from . import anthropic_chat
from .user_url import check_user_base_url

SYSTEM_PROMPT = """You are an assistant inside SkyPortal, a data platform for \
time-domain and multi-messenger astronomy. You are talking with an astronomer \
in a chat panel of the app.

Use the tools to look things up rather than guessing; if the tools do not answer \
the question, say so plainly. Do not work out for yourself where a target sits \
in the sky at a given hour, when it rises or sets, or whether it is observable \
from a telescope tonight: you have no clock and no ephemeris, and the figures \
you produce will be wrong. Convert times with convert_time and report the UTC \
it returns; a Julian Date restated from memory lands on the wrong calendar day, \
because the JD day turns over at noon UTC. When a value came from a circular or another \
record, quote the text it came from so a reader can check it. Be brief: this is a \
chat message, not a report.

You can write a broker filter only from that filter's own page, where the tools \
for it are in front of you. Asked to build one anywhere else, say that a filter \
is built from the filter page and offer to work out the cuts meanwhile; do not \
ask for an endpoint or a payload to call on your own, and do not present a \
pipeline you had no way to preview as though it were ready to save.

A Lasair filter (its broker's filter_kind is query) is SQL over Lasair's \
tables, not a pipeline: take its columns from get_alert_schema, preview it with \
preview_lasair_filter, and leave the saving to the user: what you previewed last is \
offered under your answer with a button that applies it.

When someone asks for high-impact, Nature- or Science-worthy, or otherwise \
"special" or "interesting" objects, they mean scientifically unusual ones, not \
objects that someone else has already labelled that way; do not just search the \
comments for words like "Nature" or "Science". Judge it from the data: rare or \
extreme classes (broad-lined Ic, superluminous supernovae, tidal disruption \
events, kilonovae, fast or very luminous transients), unusual proximity or \
luminosity, peculiar or fast-evolving light curves and spectra, high anomaly \
scores from the ML classifiers, or a multi-messenger or cross-survey association."""

# Reserved, so sweeping the service's own tokens cannot hit a user's.
SERVICE_TOKEN_PREFIX = "assistant-service-"

CONTEXT_DESCRIPTIONS = {
    "source": "source {id}",
    "gcn_event": "GCN event {id}",
    "spectrum": "spectrum {id}",
    "filter": "broker filter {id}, written as broker id / filter id",
    "earthquake": "earthquake {id}",
    "shift": "shift {id}",
}


def describe_context(context_type, context_id):
    if not context_type or context_id in (None, ""):
        return None
    template = CONTEXT_DESCRIPTIONS.get(context_type, "{type} {id}")
    return template.format(type=context_type, id=context_id)


def describe_user(user):
    if not user:
        return None
    name = " ".join(
        part for part in (user.get("first_name"), user.get("last_name")) if part
    ).strip()
    username = user.get("username")
    if name and username:
        return f"{name} (@{username})"
    return name or username or None


def now_line():
    """The current time, in the two forms the tools ask for.

    The prompt tells the model it has no clock, which is right about ephemerides
    and wrong about this: a broker preview is bounded by Julian Date, and a
    model guessing one from memory reaches for a date in its training data. It
    then spends its whole tool budget on a window the broker rejects.
    """
    from astropy.time import Time

    now = Time.now()
    return (
        f"The time is {now.iso[:16]} UTC, which is JD {now.jd:.4f}. "
        "Any window you pass to a tool should be near it."
    )


def system_prompt(context_type=None, context_id=None, user=None):
    lines = [SYSTEM_PROMPT, now_line()]
    person = describe_user(user)
    if person:
        lines.append(f"The person asking is {person}, from their SkyPortal profile.")
    context = describe_context(context_type, context_id)
    if context:
        lines.append(f"They are looking at {context}.")
    return "\n\n".join(lines)


def build_messages(
    messages, max_messages, context_type=None, context_id=None, user=None
):
    turns = [
        {
            "role": "assistant" if message["system"] else "user",
            "content": message["text"],
        }
        for message in messages[-max_messages:]
    ]
    # A model answers a question, so the last turn has to be one. Trailing
    # assistant turns are refused outright by an OpenAI-compatible server.
    while turns and turns[-1]["role"] == "assistant":
        turns.pop()
    return [
        {"role": "system", "content": system_prompt(context_type, context_id, user)},
        *turns,
    ]


def is_enabled(cfg):
    return bool((cfg.get("app.assistant") or {}).get("base_url"))


def user_keys_allowed(cfg):
    """Whether a user's own AI connection may answer their chat questions."""
    return bool((cfg.get("app.assistant") or {}).get("allow_user_keys"))


# Where an openai_compatible connection without a base_url is sent.
OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_BASE_URLS = {
    "openai_compatible": OPENAI_BASE_URL,
    "anthropic": anthropic_chat.DEFAULT_BASE_URL,
}


def user_endpoint(connection):
    """The endpoint a user's own AIConnection answers on, or None if it cannot.

    It still has to pass `check_user_endpoint` right before use.
    """
    if connection is None or connection.provider not in DEFAULT_BASE_URLS:
        return None
    return {
        "base_url": connection.base_url or DEFAULT_BASE_URLS[connection.provider],
        "model": connection.model or "",
        "api_key": connection.api_key or "",
        "user_key": True,
        "provider": connection.provider,
    }


def check_user_endpoint(endpoint):
    """`endpoint` with its base URL checked, or ValueError saying what to fix."""
    if not endpoint["model"]:
        raise ValueError(
            "Set a model in the AI connection in your profile for the assistant "
            "to use."
        )
    # Such a header is refused with an error that quotes it, key and all.
    if not (endpoint["api_key"].isascii() and endpoint["api_key"].isprintable()):
        raise ValueError(
            "The key in your AI connection has a line break or a non-ASCII "
            "character; enter it again."
        )
    return {**endpoint, "base_url": check_user_base_url(endpoint["base_url"])}


def post_to_assistant(cfg, message_id):
    url = f"http://{cfg['hosts.assistant']}:{cfg['ports.assistant']}"
    try:
        requests.post(
            url, json={"message_id": message_id}, timeout=2
        ).raise_for_status()
    except requests.exceptions.RequestException:
        return False
    return True


# Below this a per-item share carries nothing worth reading.
MIN_ITEM_SHARE = 300


def _reparsed(text):
    """A condensed result as JSON where it still parses, else as its own text."""
    try:
        return json.loads(text)
    except ValueError:
        return text


def condense(text, budget=6000):
    """Fit a tool result into a context budget without handing back broken JSON."""
    if len(text) <= budget:
        return text

    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return text[:budget] + f"\n... truncated, {len(text)} characters in total"

    if isinstance(payload, list):
        kept = []
        for item in payload:
            kept.append(item)
            if len(json.dumps(kept)) > budget:
                kept.pop()
                break
        # Two events kept whole answer less than every event cut to its date,
        # so take whichever form names more of them.
        room = max(1, min(len(payload), budget // MIN_ITEM_SHARE))
        if len(kept) >= room:
            note = f"{len(payload) - len(kept)} more of {len(payload)} not shown"
            return json.dumps({"items": kept, "note": note})
        shown = payload[:room]
        share = budget // len(shown)
        items = [
            _reparsed(condense(json.dumps(item, default=str), share)) for item in shown
        ]
        left = len(payload) - len(shown)
        note = "each item cut down to fit; asking for more per page will not add to it"
        if left:
            note = f"{len(shown)} of {len(payload)} shown, " + note
        return json.dumps({"items": items, "note": note})

    if not isinstance(payload, dict):
        return text[:budget]

    for key, value in payload.items():
        smaller = _shrunk(value, budget)
        if smaller is not None:
            payload[key] = smaller

    dropped = []
    by_size = sorted(payload, key=lambda k: -len(json.dumps(payload[k], default=str)))
    for key in by_size:
        current = json.dumps(payload, default=str)
        if len(current) <= budget:
            return current
        payload.pop(key)
        dropped.append(key)
        payload["_dropped"] = f"fields too large to show: {', '.join(dropped)}"
    return json.dumps(payload, default=str)


def _shrunk(value, budget):
    """A smaller stand-in for an oversized value, or None if there isn't one.

    A field is worth shrinking before it is worth dropping: a spectrum reduced
    to its date and instrument still answers a question, and a deleted one
    answers nothing.
    """
    if (
        isinstance(value, list)
        and len(value) >= 20
        and all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in value
        )
    ):
        # An answer can use the range a spectrum covers, never its 214 fluxes.
        return {"n": len(value), "min": min(value), "max": max(value)}
    if not isinstance(value, (list, dict)) or not value:
        return None
    if len(json.dumps(value, default=str)) <= budget:
        return None
    return _reparsed(condense(json.dumps(value, default=str), budget))


# How much of one tool's arguments and result the page is shown. The trace is
# there to be read at a glance; the answer carries the detail.
TRACE_ARG_BUDGET = 400
TRACE_SUMMARY_BUDGET = 300


def record_call(name, arguments, result, ok):
    """One entry of the trace shown under the answer."""
    return {
        "name": name,
        "arguments": trim(arguments, TRACE_ARG_BUDGET),
        "ok": ok,
        "summary": condense(str(result), TRACE_SUMMARY_BUDGET),
    }


def trim(arguments, budget):
    """Tool arguments small enough to render, the pipeline left whole.

    A pipeline is the one argument worth reading in full: it is what the user is
    being asked to approve.
    """
    out = {}
    for key, value in (arguments or {}).items():
        if key in ("pipeline", "conditions"):
            out[key] = value
            continue
        rendered = value if isinstance(value, str) else json.dumps(value, default=str)
        out[key] = value if len(rendered) <= budget else rendered[:budget] + "\u2026"
    return out


def proposal(trace):
    """The filter the assistant built, assembled from what it actually ran.

    A pipeline it never previewed is not offered: the preview is the evidence
    that it matches anything, and offering one without it invites saving a
    filter that passes nothing.
    """
    pipeline = preview = target = lasair = None
    for call in trace:
        if not call["ok"]:
            continue
        arguments = call["arguments"]
        if call["name"] == "preview_lasair_filter" and arguments.get("conditions"):
            count = re.search(r'"count":\s*(\d+)', call["summary"])
            lasair = {
                "broker_id": arguments.get("broker_id"),
                "tree": arguments["conditions"],
                "count": int(count.group(1)) if count else None,
            }
        elif call["name"] == "run_broker_filter" and arguments.get("pipeline"):
            pipeline = arguments["pipeline"]
            preview = {
                "summary": call["summary"],
                "start_jd": arguments.get("start_jd"),
                "end_jd": arguments.get("end_jd"),
            }
        elif call["name"] == "post_broker_filter_version" and arguments.get("altdata"):
            # Saved already: what the builder should show is what was saved.
            pipeline = arguments["altdata"]
            target = {
                "broker_id": arguments.get("broker_id"),
                "filter_id": arguments.get("filter_id"),
            }
    if lasair is not None:
        return {"lasair": lasair, "target": target}
    if pipeline is None or preview is None:
        return None
    return {"pipeline": pipeline, "preview": preview, "target": target}


FILTER_WRITE_TOOLS = frozenset(
    {
        "post_broker_filter_version",
        "validate_broker_filter_version",
        "activate_broker_filter_version",
        "attach_filter_to_broker",
    }
)


def targets_page_filter(arguments, context_id):
    """Whether a filter write names the filter whose page it was asked from."""
    return f"{arguments.get('broker_id')}/{arguments.get('filter_id')}" == context_id


def offered_tools(tools, context_type=None):
    """The tools to put in front of the model.

    Read-only ones always. A tool that writes is offered only on the page whose
    subject it writes to, because a model can be talked into a write by the text
    of something it read, and most of what it reads is written by other people.
    """
    writable = FILTER_WRITE_TOOLS if context_type == "filter" else frozenset()
    return [
        tool
        for tool in tools
        if (tool.get("annotations") or {}).get("readOnlyHint")
        or tool.get("name") in writable
    ]


def chat_payload(model, messages, tools, thinking=False, user_key=False):
    """The body of a chat-completions request.

    Here rather than in the service because the service calls init_db at
    import, so a test that reaches into it rebinds the session for everything
    else in the run.

    `tools` is omitted when empty rather than sent as []: the last round asks
    for an answer with no tools left to call, and a server that rejects an
    empty array turns that into a 400 the user reads as "something went wrong".

    `user_key` marks a user's own provider, which gets neither the vLLM-only
    chat_template_kwargs (OpenAI refuses unknown fields) nor a temperature
    (OpenAI's reasoning models and recent Claude models refuse one).
    """
    payload = {
        "model": model,
        "messages": [anthropic_chat.public(message) for message in messages],
    }
    if not user_key:
        payload["temperature"] = 0
    if tools:
        payload["tools"] = tools
    if not (thinking or user_key):
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return payload


PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "confirm_connection",
        "description": "Confirm that this connection works.",
        "parameters": {"type": "object", "properties": {}},
    },
}


def _provider_error(response, api_key):
    """The provider's own short reason for refusing a request, without the key."""
    try:
        body = response.json()
    except ValueError:
        return ""
    # OpenAI nests it under "error", vLLM puts it at the top, Ollama a string.
    error = body.get("error", body) if isinstance(body, dict) else None
    if isinstance(error, dict):
        error = error.get("message")
    if not isinstance(error, str):
        return ""
    return _redacted(error, api_key)


def _redacted(error, api_key):
    if api_key:
        error = error.replace(api_key, "[key]")
    return " ".join(error.split())[:300]


def probe(endpoint, timeout=30):
    """Whether `endpoint` can drive the assistant, which answers by calling tools.

    Sends the streamed request the assistant would, since a provider may refuse
    a stream it would answer whole, and gives up after `timeout` seconds in all.
    Returns {"outcome": "works" | "no_tool_calls" | "failed", "message": str}.
    """

    def result(outcome, message):
        return {"outcome": outcome, "message": message}

    def failed(said, error):
        return result("failed", said + (f": {error}" if error else "."))

    try:
        endpoint = check_user_endpoint(endpoint)
    except ValueError as exc:
        return result("failed", str(exc))
    asked = [{"role": "user", "content": "Call confirm_connection."}]
    deadline = time.monotonic() + timeout
    try:
        if endpoint.get("provider") == "anthropic":
            with anthropic_chat.client(
                endpoint["api_key"], endpoint["base_url"], timeout=timeout
            ) as client:
                message = anthropic_chat.streamed(
                    client,
                    deadline,
                    model=endpoint["model"],
                    **anthropic_chat.request(asked, [PROBE_TOOL]),
                )
            message = anthropic_chat.reply(message)
        else:
            headers = {}
            if endpoint["api_key"]:
                headers["Authorization"] = f"Bearer {endpoint['api_key']}"
            payload = chat_payload(
                endpoint["model"], asked, [PROBE_TOOL], user_key=True
            )
            payload["stream"] = True
            with (
                requests.post(
                    f"{endpoint['base_url'].rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=timeout,
                    # A redirect would take the key past the base_url check.
                    allow_redirects=False,
                ) as response,
                cut_off_at(response, deadline),
            ):
                if response.status_code >= 300:
                    return failed(
                        f"The provider answered with HTTP {response.status_code}",
                        _provider_error(response, endpoint["api_key"]),
                    )
                message = streamed_message(response)
    except anthropic.APIStatusError as exc:
        error = exc.api_message if isinstance(exc.api_message, str) else ""
        error = _redacted(error, endpoint["api_key"])
        if exc.status_code < 300:
            # An error event partway through a stream that opened with 200.
            return failed("The provider reported an error partway through", error)
        return failed(f"The provider answered with HTTP {exc.status_code}", error)
    except (requests.exceptions.Timeout, anthropic.APITimeoutError):
        return result("failed", f"The provider did not answer within {timeout} s.")
    except (requests.exceptions.RequestException, anthropic.APIConnectionError):
        return result("failed", f"Could not reach {endpoint['base_url']}.")
    # AssertionError is the SDK's for a reply that was no Messages API stream.
    except (ValueError, LookupError, TypeError, AttributeError, AssertionError):
        message = {}
    if message.get("tool_calls"):
        return result("works", "The model called a tool, so the assistant can use it.")
    if message.get("content"):
        return result(
            "no_tool_calls",
            "The model replied but did not call the tool it was offered. The "
            "assistant answers by calling tools, so it needs a model that can.",
        )
    return result("failed", "The reply was not a readable stream; check the base URL.")


def merge_deltas(deltas):
    """The message the deltas of a streamed chat completion add up to."""
    content, calls = [], {}
    for delta in deltas:
        content.append(delta.get("content") or "")
        for part in delta.get("tool_calls") or []:
            call = calls.setdefault(
                part.get("index", 0),
                {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                },
            )
            function = part.get("function") or {}
            call["id"] = part.get("id") or call["id"]
            call["function"]["name"] = function.get("name") or call["function"]["name"]
            call["function"]["arguments"] += function.get("arguments") or ""
    message = {"role": "assistant", "content": "".join(content) or None}
    if calls:
        message["tool_calls"] = [calls[index] for index in sorted(calls)]
    return message


def streamed_message(response):
    """The message the server-sent events of a chat completion add up to."""
    deltas = []
    for line in response.iter_lines():
        if not line.startswith(b"data:"):
            continue
        data = line[len(b"data:") :].strip()
        if data == b"[DONE]":
            break
        choices = json.loads(data).get("choices") or []
        if choices:
            deltas.append(choices[0].get("delta") or {})
    return merge_deltas(deltas)


@contextlib.contextmanager
def cut_off_at(response, deadline):
    """Read `response` inside the block, or raise Timeout once `deadline` passes.

    A read timeout bounds each read, not their sum, and a server can send one
    byte at a time just inside it, so the socket is shut at the deadline.
    """
    cut = threading.Event()

    def shut():
        cut.set()
        with contextlib.suppress(Exception):
            response.raw.shutdown()

    timer = threading.Timer(max(deadline - time.monotonic(), 0), shut)
    timer.daemon = True
    timer.start()
    try:
        yield
    except Exception:
        if not cut.is_set():
            raise
    finally:
        timer.cancel()
    if cut.is_set():
        raise requests.exceptions.Timeout("no full answer in time")
