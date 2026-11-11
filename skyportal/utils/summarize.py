"""Ask the model named by `analysis_services.openai_analysis_service.summary`.

Any server speaking the OpenAI chat-completions protocol works, via `base_url`.
Kept apart from the obj analysis service, which cannot carry a GcnEvent.
"""

__all__ = ["summarize", "summarizer_configured", "user_summarizer"]

import copy

from baselayer.app.env import load_env
from baselayer.log import make_log

from .user_url import check_user_base_url

env, cfg = load_env()
log = make_log("summarize")

SYSTEM_PROMPT = "You are an authoritative expert in astronomical time-domain research."


def _config():
    return copy.deepcopy(cfg["analysis_services.openai_analysis_service.summary"]) or {}


def summarizer_configured():
    """Whether a key is set, so callers can hide an action that cannot work."""
    return bool(_config().get("api_key"))


# The non-secret summary settings a user keeps in preferences.summary.OpenAI.
SUMMARY_TUNING = (
    "model",
    "temperature",
    "max_tokens",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "prompt",
)


def user_summarizer(connection, preferences):
    """A user's own model settings: their AIConnection's key, sent only to its
    base_url, with their summary tuning from `preferences`.

    Raises ValueError when that base_url fails `check_user_base_url`, rerun at
    each use since its host can resolve elsewhere than when it was saved.
    """
    if connection is None or connection.provider != "openai_compatible":
        return None
    api_key = connection.api_key
    if not api_key:
        return None
    tuning = ((preferences or {}).get("summary") or {}).get("OpenAI") or {}
    settings = {k: tuning[k] for k in SUMMARY_TUNING if tuning.get(k) is not None}
    # The connection's model is the one entered beside the provider it is for.
    model = connection.model or settings.get("model") or _config().get("model")
    if model:
        settings["model"] = model
    base_url = connection.base_url
    return {
        **settings,
        "api_key": api_key,
        "base_url": check_user_base_url(base_url) if base_url else None,
    }


def summarize(prompt, context, timeout=60, settings=None):
    """The model's summary of `context`, or None. `settings` overrides the instance's."""
    settings = settings or _config()
    api_key = settings.get("api_key")
    if not api_key:
        return None

    try:
        from openai import DefaultHttpxClient, OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=settings.get("base_url") or None,
            timeout=timeout,
            # A redirect would take the key past the base_url check.
            http_client=DefaultHttpxClient(follow_redirects=False),
        )
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{prompt}\n'''\n{context}\n'''"},
            ],
            model=settings.get("model") or "gpt-4o-mini",
            temperature=settings.get("temperature", 0.3),
            max_tokens=settings.get("max_tokens", 350),
            top_p=settings.get("top_p", 1.0),
        )
    except Exception as e:
        log(f"summarization failed: {e}")
        return None

    choice = response.choices[0]
    # A reasoning model spends the same budget on its reasoning, so a small
    # max_tokens can be gone before the answer starts and leave a stub that
    # reads like a summary. Refuse it rather than store half a sentence.
    if choice.finish_reason == "length":
        log(
            "summarization hit max_tokens before finishing; raise "
            "analysis_services.openai_analysis_service.summary.max_tokens "
            f"(currently {settings.get('max_tokens', 350)})"
        )
        return None

    text = (choice.message.content or "").strip()
    return text or None
