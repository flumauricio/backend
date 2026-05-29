"""add bots table

Revision ID: b7e4d2f1a039
Revises: a3f8c2d1e094
Create Date: 2026-05-28 00:00:00.000000

NOTE: If you have NOT applied the plans/user_limits migration (a3f8c2d1e094),
change down_revision below to your last applied revision ID.
Check with: alembic history
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b7e4d2f1a039"
down_revision: Union[str, None] = "a3f8c2d1e094"  # ← adjust if needed
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Native PG ENUM ────────────────────────────────────────────────────────
    bot_status_enum = postgresql.ENUM(
        "draft", "stopped", "running", "error",
        name="bot_status",
        create_type=True,
    )
    bot_status_enum.create(op.get_bind(), checkfirst=True)

    # ── bots table ────────────────────────────────────────────────────────────
    op.create_table(
        "bots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft", "stopped", "running", "error",
                name="bot_status",
                create_type=False,   # already created above
            ),
            nullable=False,
            server_default="draft",
        ),
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

    # ── Indexes ───────────────────────────────────────────────────────────────
    op.create_index("ix_bots_id",       "bots", ["id"])
    op.create_index("ix_bots_owner_id", "bots", ["owner_id"])
    op.create_index("ix_bots_status",   "bots", ["status"])
    # Composite: efficient "list bots for user ordered by date"
    op.create_index(
        "ix_bots_owner_created",
        "bots",
        ["owner_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_bots_owner_created", table_name="bots")
    op.drop_index("ix_bots_status",        table_name="bots")
    op.drop_index("ix_bots_owner_id",      table_name="bots")
    op.drop_index("ix_bots_id",            table_name="bots")
    op.drop_table("bots")

    # Drop ENUM type last (after table that references it is gone)
    postgresql.ENUM(name="bot_status").drop(op.get_bind(), checkfirst=True)
