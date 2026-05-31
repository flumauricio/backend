"""storage_v2_health — add health monitoring fields to storage_volumes

Revision ID: f4a7c8d9e102
Revises: e3f6a9b2c017
Create Date: 2026-05-31 00:00:00.000000

Adds V2 health monitoring columns to storage_volumes.
No new tables. No new PG ENUM types (health_status is String(30)).
No new indexes to avoid duplicate-index errors.
All columns are nullable or have server defaults — safe for existing rows.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a7c8d9e102"
down_revision: Union[str, None] = "e3f6a9b2c017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # All ADD COLUMN operations use IF NOT EXISTS via try/except per column
    # so re-running the migration is safe (idempotent).
    conn = op.get_bind()

    _safe_add_columns(conn)

    # Backfill existing rows: set health_status = 'unknown' where it's NULL
    conn.execute(
        sa.text(
            "UPDATE storage_volumes "
            "SET health_status = 'unknown' "
            "WHERE health_status IS NULL OR health_status = ''"
        )
    )


def _safe_add_columns(conn) -> None:
    """Add each column only if it doesn't already exist."""

    columns = [
        # (column_name, DDL_type_string, server_default_or_None)
        ("detected_total_mb",    "INTEGER",                  None),
        ("detected_free_mb",     "INTEGER",                  None),
        ("reserved_system_mb",   "INTEGER",                  "1024"),
        ("reserve_percent",      "INTEGER",                  "10"),
        ("health_status",        "VARCHAR(30)",              "'unknown'"),
        ("health_message",       "TEXT",                     None),
        ("last_health_check_at", "TIMESTAMP WITH TIME ZONE", None),
        ("auto_detected",        "BOOLEAN",                  "FALSE"),
    ]

    # Query which columns already exist
    existing = set()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'storage_volumes'"
        )
    )
    for row in result:
        existing.add(row[0])

    for col_name, col_type, default in columns:
        if col_name in existing:
            continue  # Already present — skip

        if default is not None:
            ddl = (
                f"ALTER TABLE storage_volumes "
                f"ADD COLUMN {col_name} {col_type} NOT NULL DEFAULT {default}"
            )
        else:
            ddl = (
                f"ALTER TABLE storage_volumes "
                f"ADD COLUMN {col_name} {col_type}"
            )
        conn.execute(sa.text(ddl))


def downgrade() -> None:
    columns = [
        "detected_total_mb",
        "detected_free_mb",
        "reserved_system_mb",
        "reserve_percent",
        "health_status",
        "health_message",
        "last_health_check_at",
        "auto_detected",
    ]
    conn = op.get_bind()
    existing = set()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'storage_volumes'"
        )
    )
    for row in result:
        existing.add(row[0])

    for col_name in columns:
        if col_name in existing:
            conn.execute(
                sa.text(f"ALTER TABLE storage_volumes DROP COLUMN IF EXISTS {col_name}")
            )
