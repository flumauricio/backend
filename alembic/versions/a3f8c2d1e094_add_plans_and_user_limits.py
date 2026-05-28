"""add plans and user_limits tables

Revision ID: a3f8c2d1e094
Revises: 1ff3049ecef4
Create Date: 2026-05-28 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a3f8c2d1e094"
down_revision: Union[str, None] = "1ff3049ecef4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── plans ──────────────────────────────────────────────────────────────────
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cloud_storage_mb", sa.Integer(), nullable=False),
        sa.Column("max_bots", sa.Integer(), nullable=False),
        sa.Column("max_ram_per_bot_mb", sa.Integer(), nullable=False),
        sa.Column("max_storage_per_bot_mb", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_plans_id", "plans", ["id"])
    op.create_index("ix_plans_name", "plans", ["name"], unique=True)

    # ── user_limits ────────────────────────────────────────────────────────────
    op.create_table(
        "user_limits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cloud_storage_mb", sa.Integer(), nullable=True),
        sa.Column("max_bots", sa.Integer(), nullable=True),
        sa.Column("max_ram_per_bot_mb", sa.Integer(), nullable=True),
        sa.Column("max_storage_per_bot_mb", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_user_limits_id", "user_limits", ["id"])
    op.create_index("ix_user_limits_user_id", "user_limits", ["user_id"])
    op.create_index("ix_user_limits_plan_id", "user_limits", ["plan_id"])
    op.create_unique_constraint(
        "uq_user_limits_user_id", "user_limits", ["user_id"]
    )


def downgrade() -> None:
    op.drop_table("user_limits")
    op.drop_table("plans")
