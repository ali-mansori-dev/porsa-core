"""faq_entries + escalations (owner knowledge base & human handoff)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

escalation_status_enum = postgresql.ENUM(
    "pending", "answered", "closed", name="escalationstatus"
)


def upgrade() -> None:
    op.create_table(
        "faq_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_faq_entries_business_id", "faq_entries", ["business_id"])

    # add_column-style enum: create the PG type explicitly before using it.
    escalation_status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "escalations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "answered", "closed", name="escalationstatus", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_escalations_business_id", "escalations", ["business_id"])
    op.create_index("ix_escalations_conversation_id", "escalations", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("escalations")
    op.execute("DROP TYPE IF EXISTS escalationstatus")
    op.drop_index("ix_faq_entries_business_id", "faq_entries")
    op.drop_table("faq_entries")
