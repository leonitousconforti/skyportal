import sqlalchemy as sa

from skyportal.models import DBSession
from skyportal.tests import api

KEY = "sk-test-abcdefgh1234"


def put(token, **fields):
    return api(
        "PUT",
        "internal/ai_connection",
        data={"provider": "openai_compatible", **fields},
        token=token,
    )


def get(token):
    status, data = api("GET", "internal/ai_connection", token=token)
    assert status == 200, data
    return data["data"]


def test_ai_connection_round_trip(view_only_token):
    assert get(view_only_token) is None

    status, data = put(view_only_token, base_url="https://8.8.8.8/v1")
    assert status == 400
    assert "API key is required" in data["message"]

    status, data = put(
        view_only_token,
        base_url="https://8.8.8.8/v1",
        model="gpt-4o-mini",
        api_key=f"  {KEY} ",
    )
    assert status == 200, data

    connection = get(view_only_token)
    assert connection == {
        "provider": "openai_compatible",
        "base_url": "https://8.8.8.8/v1",
        "model": "gpt-4o-mini",
        "api_key_set": True,
        "api_key_last4": "1234",
    }

    # A blank key keeps the stored one while the address stays the same.
    status, data = put(
        view_only_token, base_url="https://8.8.8.8/v1", model="gpt-4o", api_key=""
    )
    assert status == 200, data
    connection = get(view_only_token)
    assert connection["model"] == "gpt-4o"
    assert connection["api_key_last4"] == "1234"

    # The stored key is never sent to a new address.
    for base_url in ("https://8.8.4.4/v1", None):
        status, data = put(view_only_token, base_url=base_url, model="gpt-4o")
        assert status == 400
        assert "Enter the API key again" in data["message"]
    assert get(view_only_token)["base_url"] == "https://8.8.8.8/v1"

    status, data = put(view_only_token, base_url="", api_key="sk-test-other-5678")
    assert status == 200, data
    connection = get(view_only_token)
    assert connection["base_url"] is None
    assert connection["model"] is None
    assert connection["api_key_last4"] == "5678"

    status, data = api("DELETE", "internal/ai_connection", token=view_only_token)
    assert status == 200, data
    assert get(view_only_token) is None
    status, data = api("DELETE", "internal/ai_connection", token=view_only_token)
    assert status == 200, data


def test_ai_connection_refuses_bad_input(view_only_token):
    status, data = put(view_only_token, base_url="https://10.0.0.1/v1", api_key=KEY)
    assert status == 400
    assert "not a public address" in data["message"]

    status, data = api(
        "PUT",
        "internal/ai_connection",
        data={"provider": "mystery", "api_key": KEY},
        token=view_only_token,
    )
    assert status == 400
    assert "Unknown provider" in data["message"]

    status, data = put(view_only_token, api_key="sk-test\r\nX-Injected: 1")
    assert status == 400
    assert "printable ASCII" in data["message"]

    assert get(view_only_token) is None


def test_anthropic_is_a_provider(view_only_token):
    status, data = put(
        view_only_token, provider="anthropic", model="claude-opus-5-5", api_key=KEY
    )
    assert status == 200, data
    try:
        connection = get(view_only_token)
        assert connection["provider"] == "anthropic"
        # Left blank, the key goes to api.anthropic.com.
        assert connection["base_url"] is None
        assert connection["model"] == "claude-opus-5-5"

        # A saved key is not carried over to another provider.
        status, data = put(view_only_token, model="gpt-4o")
        assert status == 400
        assert "Enter the API key again" in data["message"]
    finally:
        api("DELETE", "internal/ai_connection", token=view_only_token)


def test_each_user_only_sees_their_own_ai_connection(
    view_only_token, view_only_token_group2, super_admin_token
):
    status, data = put(view_only_token, api_key=KEY)
    assert status == 200, data
    try:
        assert get(view_only_token_group2) is None
        assert get(super_admin_token) is None

        # Another user's blank-key save cannot reach this connection.
        status, data = put(view_only_token_group2, base_url="https://8.8.4.4/v1")
        assert status == 400
        status, data = api(
            "DELETE", "internal/ai_connection", token=view_only_token_group2
        )
        assert status == 200, data

        status, data = put(view_only_token_group2, api_key="sk-test-their-9999")
        assert status == 200, data
        assert get(view_only_token_group2)["api_key_last4"] == "9999"

        connection = get(view_only_token)
        assert connection["base_url"] is None
        assert connection["api_key_last4"] == "1234"
    finally:
        api("DELETE", "internal/ai_connection", token=view_only_token)
        api("DELETE", "internal/ai_connection", token=view_only_token_group2)


def test_ai_connection_key_is_encrypted_and_never_serialized(user_ai_connection):
    assert "not-a-real-key" not in str(user_ai_connection.to_dict())
    stored = (
        DBSession()
        .execute(
            sa.text("SELECT _secrets FROM ai_connections WHERE id = :id"),
            {"id": user_ai_connection.id},
        )
        .scalar_one()
    )
    assert "not-a-real-key" not in stored


def test_testing_is_refused_unless_the_assistant_uses_the_connection(
    view_only_token,
):
    # test_config.yaml leaves app.assistant.allow_user_keys off, so nothing is
    # sent; test_assistant.py covers what a provider answers.
    status, data = put(view_only_token, model="gpt-4o-mini", api_key=KEY)
    assert status == 200, data
    try:
        status, data = api("POST", "internal/ai_connection/test", token=view_only_token)
        assert status == 400
        assert "does not use your AI connection" in data["message"]
    finally:
        api("DELETE", "internal/ai_connection", token=view_only_token)
