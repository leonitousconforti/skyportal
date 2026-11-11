"""Drop AI API keys stored on analyses

Revision ID: 4c7e2a9b1d30
Revises: e7a41c9d2b58
Create Date: 2026-11-11 00:00:00.000000

"""

from alembic import op

revision = "4c7e2a9b1d30"
down_revision = "e7a41c9d2b58"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("obj_analyses", "gcnevent_analyses"):
        op.execute(
            f"""
            UPDATE {table}
            SET analysis_parameters =
                (analysis_parameters::jsonb - 'openai_api_key')::json
            WHERE analysis_parameters -> 'openai_api_key' IS NOT NULL
            """
        )


def downgrade():
    pass
