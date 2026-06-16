"""phone/OTP auth: owner_phone on businesses + users, otp_codes, auth_sessions

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("owner_phone", sqlmodel.AutoString(), nullable=True),
    )
    op.create_index("ix_businesses_owner_phone", "businesses", ["owner_phone"])

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone", sqlmodel.AutoString(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone", name="uq_users_phone"),
    )
    op.create_index("ix_users_phone", "users", ["phone"])
    op.create_index("ix_users_business_id", "users", ["business_id"])

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone", sqlmodel.AutoString(), nullable=False),
        sa.Column("code_hash", sqlmodel.AutoString(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_otp_codes_phone", "otp_codes", ["phone"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token", sqlmodel.AutoString(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_auth_sessions_token"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_token", "auth_sessions", ["token"])


def downgrade() -> None:
    op.drop_table("auth_sessions")
    op.drop_table("otp_codes")
    op.drop_index("ix_users_business_id", "users")
    op.drop_index("ix_users_phone", "users")
    op.drop_table("users")
    op.drop_index("ix_businesses_owner_phone", "businesses")
    op.drop_column("businesses", "owner_phone")
