"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-02-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_service_categories_code", "service_categories", ["code"])

    op.create_table(
        "hospital_services",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("service_categories.id"), nullable=False),
        sa.Column("example_utterances", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("required_slots", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_hospital_services_code", "hospital_services", ["code"])

    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("room_name", sa.String(128), nullable=False, unique=True),
        sa.Column("identity", sa.String(128), nullable=False),
        sa.Column("detected_language", sa.String(16), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_sessions_room_name", "voice_sessions", ["room_name"])

    op.create_table(
        "service_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("voice_sessions.id"), nullable=True),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("hospital_services.id"), nullable=False),
        sa.Column("raw_transcript", sa.Text(), nullable=False),
        sa.Column("normalized_transcript_en", sa.Text(), nullable=False),
        sa.Column("detected_language", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("used_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "unknown_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("voice_sessions.id"), nullable=True),
        sa.Column("raw_transcript", sa.Text(), nullable=False),
        sa.Column("detected_language", sa.String(16), nullable=True),
        sa.Column("top_semantic_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("top_candidate_code", sa.String(64), nullable=True),
        sa.Column("review_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("unknown_requests")
    op.drop_table("service_requests")
    op.drop_index("ix_voice_sessions_room_name", table_name="voice_sessions")
    op.drop_table("voice_sessions")
    op.drop_index("ix_hospital_services_code", table_name="hospital_services")
    op.drop_table("hospital_services")
    op.drop_index("ix_service_categories_code", table_name="service_categories")
    op.drop_table("service_categories")
