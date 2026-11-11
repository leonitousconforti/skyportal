"""Per-user AI connections

Revision ID: 8d2f6b0e3a51
Revises: 4c7e2a9b1d30
Create Date: 2026-11-11 00:00:00.000000

"""

import sqlalchemy as sa
import sqlalchemy_utils

from alembic import op

revision = "8d2f6b0e3a51"
down_revision = "4c7e2a9b1d30"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_connections",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("modified", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column(
            "_secrets",
            sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(),
            nullable=True,
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_ai_connections_created_at"),
        "ai_connections",
        ["created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_ai_connections_created_at"), table_name="ai_connections")
    op.drop_table("ai_connections")
