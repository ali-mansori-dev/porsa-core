"""business enhancements: api_key, welcome_message, max_tokens, response_style

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15

"""
import secrets
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

response_style_enum = postgresql.ENUM(
    "friendly", "formal", "brief", name="responsestyle"
)


def upgrade() -> None:
    # add_column does not auto-create the enum type, so create it explicitly first.
    response_style_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "businesses",
        sa.Column("api_key", sqlmodel.AutoString(), nullable=True),
    )
    op.add_column(
        "businesses",
        sa.Column("welcome_message", sqlmodel.AutoString(), nullable=True),
    )
    op.add_column(
        "businesses",
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="1000"),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "response_style",
            sa.Enum("friendly", "formal", "brief", name="responsestyle", create_type=False),
            nullable=False,
            server_default="friendly",
        ),
    )

    # Backfill api_key for existing rows
    connection = op.get_bind()
    businesses = connection.execute(sa.text("SELECT id FROM businesses")).fetchall()
    for row in businesses:
        key = secrets.token_urlsafe(32)
        connection.execute(
            sa.text("UPDATE businesses SET api_key = :key WHERE id = :id"),
            {"key": key, "id": str(row[0])},
        )

    op.alter_column("businesses", "api_key", nullable=False)
    op.create_unique_constraint("uq_businesses_api_key", "businesses", ["api_key"])
    op.create_index("ix_businesses_api_key", "businesses", ["api_key"])


def downgrade() -> None:
    op.drop_index("ix_businesses_api_key", "businesses")
    op.drop_constraint("uq_businesses_api_key", "businesses", type_="unique")
    op.drop_column("businesses", "response_style")
    op.drop_column("businesses", "max_tokens")
    op.drop_column("businesses", "welcome_message")
    op.drop_column("businesses", "api_key")
    op.execute("DROP TYPE IF EXISTS responsestyle")
