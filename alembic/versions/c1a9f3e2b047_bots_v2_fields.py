"""bots v2 — add runtime fields and expand status enum

Revision ID: c1a9f3e2b047
Revises: b7e4d2f1a039
Create Date: 2026-05-29 00:00:00.000000

⚠  IMPORTANT — check your last applied revision:
    docker compose exec api alembic current

If your last revision is NOT b7e4d2f1a039 (bots V1), update
down_revision below to match your actual last revision.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c1a9f3e2b047"
down_revision: Union[str, None] = "b7e4d2f1a039"   # ← adjust if needed
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The two new status values being added to the PG enum
_NEW_STATUSES = ("starting", "stopping")


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Expand PG ENUM bot_status with new values ──────────────────────────
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in PG < 12.
    # We use COMMIT trick for safety; op.execute handles this correctly.
    for val in _NEW_STATUSES:
        # IF NOT EXISTS prevents duplicate errors on re-run
        conn.execute(
            sa.text(f"ALTER TYPE bot_status ADD VALUE IF NOT EXISTS '{val}'")
        )

    # ── 2. Add V2 columns to bots ─────────────────────────────────────────────
    op.add_column("bots", sa.Column(
        "language", sa.String(50), nullable=False, server_default="javascript"
    ))
    op.add_column("bots", sa.Column("runtime_version",  sa.String(50),  nullable=True))
    op.add_column("bots", sa.Column("main_file",        sa.String(255), nullable=True))
    op.add_column("bots", sa.Column("repository_url",   sa.String(500), nullable=True))
    op.add_column("bots", sa.Column("discord_token",    sa.String(200), nullable=True))
    op.add_column("bots", sa.Column("env_vars",         sa.JSON(),      nullable=True))
    op.add_column("bots", sa.Column(
        "last_started_at", sa.DateTime(timezone=True), nullable=True
    ))
    op.add_column("bots", sa.Column(
        "last_stopped_at", sa.DateTime(timezone=True), nullable=True
    ))


def downgrade() -> None:
    # ── Remove V2 columns ─────────────────────────────────────────────────────
    for col in (
        "last_stopped_at",
        "last_started_at",
        "env_vars",
        "discord_token",
        "repository_url",
        "main_file",
        "runtime_version",
        "language",
    ):
        op.drop_column("bots", col)

    # ── Note: PG does not support removing values from an ENUM ────────────────
    # To fully revert the enum, you would need to:
    #   1. ALTER TABLE bots ALTER COLUMN status TYPE varchar
    #   2. DROP TYPE bot_status
    #   3. Re-create bot_status with original values
    #   4. ALTER TABLE bots ALTER COLUMN status TYPE bot_status USING status::bot_status
    # This is left as a manual step to avoid data-loss on accidental downgrade.
