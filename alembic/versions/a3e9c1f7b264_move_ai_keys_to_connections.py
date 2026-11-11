"""Move personal AI keys from preferences into ai_connections

An active summary.OpenAI key becomes the user's AI connection; a saved but
inactive one is dropped. The downgrade writes the keys back into preferences
and leaves the connections, which the previous revision's downgrade drops.

Revision ID: a3e9c1f7b264
Revises: 8d2f6b0e3a51
Create Date: 2026-11-11 00:00:00.000000

"""

import json
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy_utils.types import JSONType
from sqlalchemy_utils.types.encrypted.encrypted_type import (
    AesEngine,
    StringEncryptedType,
)

from alembic import context, op
from baselayer.app.config import load_config

revision = "a3e9c1f7b264"
down_revision = "8d2f6b0e3a51"
branch_labels = None
depends_on = None

users = sa.table("users", sa.column("id", sa.Integer), sa.column("preferences", JSONB))


def _ai_connections():
    # The config env.py loads from `-x config=`, which is the app's. load_env()
    # does not see that flag, so it could hold another app.secret_key.
    config_arg = context.get_x_argument(as_dictionary=True).get("config")
    cfg = load_config(config_files=config_arg.split(":") if config_arg else [])
    # _secrets typed as on AIConnection, so a key is encrypted as its api_key
    # setter stores it.
    return sa.table(
        "ai_connections",
        sa.column("created_at", sa.DateTime),
        sa.column("modified", sa.DateTime),
        sa.column("user_id", sa.Integer),
        sa.column("provider", sa.String),
        sa.column("base_url", sa.String),
        sa.column("model", sa.String),
        sa.column(
            "_secrets",
            StringEncryptedType(JSONType, cfg["app.secret_key"], AesEngine, "pkcs5"),
        ),
    )


def _text(value):
    return (value.strip() or None) if isinstance(value, str) else None


def upgrade():
    bind = op.get_bind()
    ai_connections = _ai_connections()
    rows = bind.execute(
        sa.text(
            """
            SELECT u.id, u.preferences #> '{summary,OpenAI}'
            FROM users u
            WHERE (u.preferences #> '{summary,OpenAI,active}') = 'true'::jsonb
            AND NOT EXISTS (SELECT 1 FROM ai_connections c WHERE c.user_id = u.id)
            """
        )
    ).all()
    now = datetime.now(UTC).replace(tzinfo=None)
    values = []
    for user_id, openai in rows:
        api_key = _text(openai.get("apikey"))
        if api_key:
            values.append(
                {
                    "created_at": now,
                    "modified": now,
                    "user_id": user_id,
                    "provider": "openai_compatible",
                    "base_url": _text(openai.get("base_url")),
                    "model": _text(openai.get("model")),
                    "_secrets": json.dumps({"api_key": api_key}),
                }
            )
    if values:
        bind.execute(sa.insert(ai_connections), values)

    op.execute(
        """
        UPDATE users
        SET preferences = jsonb_set(
            preferences,
            '{summary,OpenAI}',
            (preferences #> '{summary,OpenAI}') - array['apikey', 'base_url', 'active']
        )
        WHERE jsonb_typeof(preferences #> '{summary,OpenAI}') = 'object'
        AND (preferences #> '{summary,OpenAI}') ?| array['apikey', 'base_url', 'active']
        """
    )


def downgrade():
    bind = op.get_bind()
    ai_connections = _ai_connections()
    rows = bind.execute(
        sa.select(
            users.c.id,
            users.c.preferences,
            ai_connections.c.base_url,
            ai_connections.c.model,
            ai_connections.c._secrets,
        )
        .select_from(ai_connections.join(users, users.c.id == ai_connections.c.user_id))
        .where(ai_connections.c.provider == "openai_compatible")
    ).all()
    for user_id, preferences, base_url, model, secrets in rows:
        if isinstance(secrets, str):
            secrets = json.loads(secrets)
        api_key = (secrets or {}).get("api_key")
        if not api_key:
            continue
        preferences = preferences or {}
        openai = preferences.setdefault("summary", {}).setdefault("OpenAI", {})
        openai.update(apikey=api_key, base_url=base_url, active=True)
        if model and not openai.get("model"):
            openai["model"] = model
        bind.execute(
            sa.update(users)
            .where(users.c.id == user_id)
            .values(preferences=preferences)
        )
