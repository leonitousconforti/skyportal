import time
import uuid

import pytest
from playwright.sync_api import expect

from skyportal.tests import api, open_preferences_panel


def _poll(read, done):
    """The UI saves asynchronously, so poll the API rather than race it."""
    value = None
    for _ in range(20):
        value = read()
        if done(value):
            break
        time.sleep(0.5)
    return value


def _ai_connection(token):
    status, data = api("GET", "internal/ai_connection", token=token)
    assert status == 200
    return data["data"]


def _summary_preferences(token):
    status, data = api("GET", "internal/profile", token=token)
    assert status == 200
    return data["data"]["preferences"].get("summary", {}).get("OpenAI", {})


@pytest.mark.flaky(reruns=2)
def test_ai_connection_prefs(page, user, upload_data_token):
    page.goto(f"/become_user/{user.id}")
    page.goto("/profile")
    open_preferences_panel(page, "sources")

    api_key = f"sk-{uuid.uuid4()}"
    page.locator('//input[@name="api_key"]').first.fill(api_key)
    page.locator('[data-testid="AIConnection_save"]').first.click()

    connection = _poll(
        lambda: _ai_connection(upload_data_token), lambda c: c is not None
    )
    assert connection == {
        "provider": "openai_compatible",
        "base_url": None,
        "model": None,
        "api_key_set": True,
        "api_key_last4": api_key[-4:],
    }

    # Summary tuning still lives in preferences, next to the connection.
    page.locator('[data-testid="UpdateOpenAI"]').first.click()
    dummy_gpt_model = f"gpt-{uuid.uuid4()}"
    # rjsf's controlled input ignores fill(); select-all + type so React's
    # onChange fires and the form state actually updates. Wait for the form to
    # finish populating its default model first -- typing before that races the
    # async default-set, leaving the field (and saved prefs) wrong.
    model_input = page.locator('//input[@name="root_model"]').first
    expect(model_input).not_to_have_value("")
    model_input.click()
    model_input.press("ControlOrMeta+a")
    model_input.press("Delete")
    model_input.press_sequentially(dummy_gpt_model)
    expect(model_input).to_have_value(dummy_gpt_model)
    page.locator(
        "//form[@class='rjsf']//button[normalize-space()='Submit']"
    ).first.click()
    expect(page.locator("div.MuiDialog-container").first).to_be_hidden()

    openai = _poll(
        lambda: _summary_preferences(upload_data_token),
        lambda prefs: prefs.get("model") == dummy_gpt_model,
    )
    assert openai.get("model") == dummy_gpt_model
    assert not {"apikey", "base_url", "active"} & openai.keys()

    # Once saved, the key is never sent back to the page, only its last four.
    page.reload()
    open_preferences_panel(page, "sources")
    key_input = page.locator('//input[@name="api_key"]').first
    expect(key_input).to_have_attribute(
        "placeholder", f"Saved key ending in {api_key[-4:]}"
    )
    expect(key_input).to_have_value("")
    assert api_key not in page.content()

    page.locator('[data-testid="AIConnection_remove"]').first.click()
    connection = _poll(lambda: _ai_connection(upload_data_token), lambda c: c is None)
    assert connection is None
    expect(page.locator('[data-testid="UpdateOpenAI"]')).to_have_count(0)
