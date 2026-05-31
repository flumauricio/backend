"""storage_v1 — add storage_volumes and bot_workspaces tables

Revision ID: e3f6a9b2c017
Revises: d2e5f8a3c906
Create Date: 2026-05-31 00:00:00.000000

Adds two new tables for Storage V1:
  - storage_volumes   (physical mount points)
  - bot_workspaces    (logical workspace reservation per bot)

No existing tables are modified.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "e3f6a9b2c017"
down_revision: Union[str, None] = "d2e5f8a3c906"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VOLUME_PURPOSE_ENUM = postgresql.ENUM(
    "bots",
    "cloud",
    "mixed",
    name="volume_purpose",
)


def upgrade() -> None:
    bind = op.get_bind()

    # Create enum once. Table columns below reuse it with create_type=False,
    # preventing PostgreSQL duplicate type errors on retry.
    VOLUME_PURPOSE_ENUM.create(bind, checkfirst=True)

    volume_purpose_type = postgresql.ENUM(
        "bots",
        "cloud",
        "mixed",
        name="volume_purpose",
        create_type=False,
    )

    op.create_table(
        "storage_volumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("mount_path", sa.String(500), nullable=False),
        sa.Column(
            "purpose",
            volume_purpose_type,
            nullable=False,
            server_default="mixed",
        ),
        sa.Column("total_mb", sa.Integer, nullable=True),
        sa.Column("used_mb", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
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
        sa.UniqueConstraint("mount_path", name="uq_storage_volumes_mount_path"),
    )
    op.create_index("ix_storage_volumes_is_active", "storage_volumes", ["is_active"])
    op.create_index("ix_storage_volumes_priority", "storage_volumes", ["priority"])
    op.create_index("ix_storage_volumes_purpose", "storage_volumes", ["purpose"])

    op.create_table(
        "bot_workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "bot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "storage_volume_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("storage_volumes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relative_path", sa.String(500), nullable=False),
        sa.Column("allocated_mb", sa.Integer, nullable=False),
        sa.Column("used_mb", sa.Integer, nullable=False, server_default="0"),
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
        sa.UniqueConstraint("bot_id", name="uq_bot_workspace_bot_id"),
    )
    op.create_index("ix_bot_workspaces_bot_id", "bot_workspaces", ["bot_id"])
    op.create_index(
        "ix_bot_workspaces_storage_volume_id",
        "bot_workspaces",
        ["storage_volume_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_bot_workspaces_storage_volume_id", table_name="bot_workspaces")
    op.drop_index("ix_bot_workspaces_bot_id", table_name="bot_workspaces")
    op.drop_table("bot_workspaces")

    op.drop_index("ix_storage_volumes_purpose", table_name="storage_volumes")
    op.drop_index("ix_storage_volumes_priority", table_name="storage_volumes")
    op.drop_index("ix_storage_volumes_is_active", table_name="storage_volumes")
    op.drop_table("storage_volumes")

    VOLUME_PURPOSE_ENUM.drop(op.get_bind(), checkfirst=True)
