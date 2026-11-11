__all__ = ["AIConnection"]

import json

import sqlalchemy as sa
from sqlalchemy.orm import relationship
from sqlalchemy_utils.types import JSONType
from sqlalchemy_utils.types.encrypted.encrypted_type import (
    AesEngine,
    StringEncryptedType,
)

from baselayer.app.env import load_env
from baselayer.app.models import AccessibleIfUserMatches, Base

_, cfg = load_env()

# Kept as a plain string column so adding a provider needs no migration.
PROVIDERS = ("openai_compatible",)


class AIConnection(Base):
    """One user's own connection to an AI provider. The key is stored
    encrypted and never handed back to a client."""

    __tablename__ = "ai_connections"

    create = read = update = delete = AccessibleIfUserMatches("user")

    user_id = sa.Column(
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        doc="The user the connection belongs to.",
    )

    provider = sa.Column(
        sa.String,
        nullable=False,
        doc="The API the connection speaks, such as openai_compatible.",
    )

    base_url = sa.Column(
        sa.String,
        nullable=True,
        doc="Where requests and the key are sent. Null means the provider's "
        "default endpoint (api.openai.com for openai_compatible).",
    )

    model = sa.Column(
        sa.String,
        nullable=True,
        doc="The model to request. Null leaves it to the feature using the "
        "connection.",
    )

    _secrets = sa.Column(
        StringEncryptedType(JSONType, cfg["app.secret_key"], AesEngine, "pkcs5"),
        doc="The API key. Never serialized back to a client.",
    )

    user = relationship("User", doc="The owner of this connection.")

    @property
    def api_key(self):
        secrets = self._secrets
        if isinstance(secrets, str):
            secrets = json.loads(secrets)
        return (secrets or {}).get("api_key")

    @api_key.setter
    def api_key(self, value):
        self._secrets = json.dumps({"api_key": value}) if value is not None else None
