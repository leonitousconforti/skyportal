"""Which model a summary request uses, and what it does with a cut-off answer."""

from types import SimpleNamespace

import pytest

from skyportal.utils.summarize import SYSTEM_PROMPT, summarize, user_summarizer


def _connection(**fields):
    return SimpleNamespace(
        **{
            "provider": "openai_compatible",
            "base_url": None,
            "model": None,
            "api_key": "sk-abc",
            **fields,
        }
    )


def _preferences(**openai):
    return {"summary": {"OpenAI": openai}}


def test_no_settings_without_a_connection_key():
    assert user_summarizer(None, _preferences(model="gpt-4o-mini")) is None
    assert user_summarizer(_connection(api_key=None), None) is None
    assert user_summarizer(_connection(provider="another_protocol"), None) is None


def test_a_personal_key_defaults_to_openai():
    settings = user_summarizer(_connection(), None)
    assert settings["api_key"] == "sk-abc"
    assert settings["base_url"] is None


def test_a_personal_key_goes_to_its_own_url(monkeypatch):
    # No DNS here; test_user_url.py covers the check itself.
    monkeypatch.setattr(
        "skyportal.utils.summarize.check_user_base_url", lambda url: url
    )
    settings = user_summarizer(
        _connection(api_key="key", base_url="https://api.anthropic.com/v1"), {}
    )
    assert settings["base_url"] == "https://api.anthropic.com/v1"
    assert settings["api_key"] == "key"


def test_a_personal_key_is_not_sent_to_a_private_url():
    with pytest.raises(ValueError):
        user_summarizer(_connection(base_url="https://127.0.0.1/v1"), {})


def test_only_summary_tuning_comes_from_preferences():
    # Leftover key fields in preferences must not redirect the connection's key.
    settings = user_summarizer(
        _connection(),
        _preferences(
            temperature=0.5,
            prompt="Summarize briefly.",
            apikey="sk-stale",
            base_url="https://elsewhere.example/v1",
            active=True,
        ),
    )
    assert settings["temperature"] == 0.5
    assert settings["prompt"] == "Summarize briefly."
    assert settings["api_key"] == "sk-abc"
    assert settings["base_url"] is None
    assert "apikey" not in settings and "active" not in settings


def test_the_connection_model_wins_then_the_summary_then_the_instance(monkeypatch):
    monkeypatch.setattr(
        "skyportal.utils.summarize._config", lambda: {"model": "instance-model"}
    )
    summary = _preferences(model="summary-model")
    connection = _connection(model="connection-model")
    assert user_summarizer(connection, summary)["model"] == "connection-model"
    assert user_summarizer(_connection(), summary)["model"] == "summary-model"
    assert user_summarizer(_connection(), {})["model"] == "instance-model"


def test_an_anthropic_connection_needs_its_own_model(monkeypatch):
    # The summary settings and the instance default name OpenAI models.
    monkeypatch.setattr(
        "skyportal.utils.summarize._config", lambda: {"model": "instance-model"}
    )
    summary = _preferences(model="summary-model", temperature=0.5)
    with pytest.raises(ValueError, match="Set a model"):
        user_summarizer(_connection(provider="anthropic"), summary)
    settings = user_summarizer(
        _connection(provider="anthropic", model="claude-opus-5-5"), summary
    )
    assert settings["provider"] == "anthropic"
    assert settings["model"] == "claude-opus-5-5"
    assert settings["base_url"] is None


def _stub_openai(monkeypatch, content, finish_reason):
    """Stand in for the OpenAI client, returning one prepared choice."""
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ]
    )

    class _Client:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kw: response)
            )

    import openai

    monkeypatch.setattr(openai, "OpenAI", _Client)


@pytest.mark.parametrize("finish_reason", ["stop", None])
def test_a_finished_answer_is_kept(monkeypatch, finish_reason):
    _stub_openai(monkeypatch, "A tidy one-paragraph summary.", finish_reason)
    assert summarize("p", "c", settings={"api_key": "k"}) == (
        "A tidy one-paragraph summary."
    )


def test_an_answer_cut_off_at_max_tokens_is_refused(monkeypatch):
    # A reasoning model can spend the budget before the answer starts, leaving
    # a stub that reads like a summary. Better none than half a sentence.
    _stub_openai(monkeypatch, "SVOM\u2019s ECLAIRs instrument (", "length")
    assert summarize("p", "c", settings={"api_key": "k"}) is None


def test_no_key_asks_nothing():
    assert summarize("p", "c", settings={}) is None


def _stub_anthropic(monkeypatch, outcome):
    """Stand in for Claude's stream, ending in `outcome`: a stop reason or an error."""
    from skyportal.utils import anthropic_chat

    sent = {}

    def streamed(client, deadline, **params):
        sent.update(params, client=client)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            stop_reason=outcome,
            content=[SimpleNamespace(type="text", text="A tidy summary.")],
        )

    monkeypatch.setattr(anthropic_chat, "streamed", streamed)
    return sent


ANTHROPIC = {"provider": "anthropic", "api_key": "k", "model": "claude-opus-5-5"}


def test_an_anthropic_summary_is_asked_of_claude(monkeypatch):
    sent = _stub_anthropic(monkeypatch, "end_turn")
    settings = {**ANTHROPIC, "temperature": 0.3, "max_tokens": 350}
    assert summarize("p", "c", settings=settings) == "A tidy summary."
    assert sent["model"] == "claude-opus-5-5"
    assert sent["system"] == SYSTEM_PROMPT
    assert sent["client"].api_key == "k"
    assert str(sent["client"].base_url).startswith("https://api.anthropic.com")
    # The OpenAI tuning does not apply; the prompt sets the length.
    assert "temperature" not in sent and "max_tokens" not in sent


@pytest.mark.parametrize(
    "stop_reason", ["max_tokens", "model_context_window_exceeded", "refusal"]
)
def test_an_anthropic_summary_cut_short_or_declined_is_refused(
    monkeypatch, stop_reason
):
    _stub_anthropic(monkeypatch, stop_reason)
    assert summarize("p", "c", settings=ANTHROPIC) is None


def test_an_anthropic_failure_is_reported_without_the_providers_words(monkeypatch):
    import anthropic
    import httpx2

    from skyportal.utils.anthropic_chat import summary

    response = httpx2.Response(
        401, request=httpx2.Request("POST", "https://llm.example/v1/messages")
    )
    body = {"error": {"message": "invalid key sk-secret-key"}}
    _stub_anthropic(
        monkeypatch, anthropic.AuthenticationError("401", response=response, body=body)
    )
    with pytest.raises(ValueError) as failure:
        summary("sk-secret-key", None, "m", "s", "c")
    assert str(failure.value) == "the provider answered with HTTP 401"
