"""Whose key a summary search may send to OpenAI's embeddings."""

from types import SimpleNamespace

from skyportal.handlers.api.summary_query import requester_embedding_key


def _connection(**fields):
    return SimpleNamespace(
        **{
            "provider": "openai_compatible",
            "base_url": None,
            "api_key": "sk-mine",
            **fields,
        }
    )


def test_a_key_for_openai_itself_backs_the_search():
    assert requester_embedding_key(_connection()) == "sk-mine"


def test_another_providers_key_is_never_sent_to_openai():
    assert (
        requester_embedding_key(_connection(base_url="https://openrouter.ai/api/v1"))
        is None
    )
    assert requester_embedding_key(_connection(provider="another_protocol")) is None
    assert requester_embedding_key(None) is None
