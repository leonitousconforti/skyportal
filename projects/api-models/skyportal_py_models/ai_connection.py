"""Request and response models for ``/api/internal/ai_connection``."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AIConnectionPutBody(BaseModel):
    """The calling user's own connection to an AI provider."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(
        description="The API the connection speaks: openai_compatible or anthropic."
    )
    base_url: str | None = Field(
        default=None,
        max_length=2000,
        description="An https URL to send requests to. Blank for the provider's "
        "default endpoint.",
    )
    model: str | None = Field(
        default=None, max_length=200, description="The model to request."
    )
    api_key: str | None = Field(
        default=None,
        max_length=1000,
        description="Required the first time. Blank keeps the stored key, unless "
        "the provider or base URL changes.",
    )


class AIConnectionResponse(BaseModel):
    """The calling user's AI connection, without the key itself."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    base_url: str | None = None
    model: str | None = None
    api_key_set: bool
    api_key_last4: str | None = None
