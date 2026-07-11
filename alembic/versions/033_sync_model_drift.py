"""Sync model drift: engine rename, nullable fixes, constraint/index cleanup, calendar_export_logs.

Revision ID: 033_sync_model_drift
Revises: 032_push_moon_phases
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "033_sync_model_drift"
down_revision = "032_push_moon_phases"
branch_labels = None
depends_on = None


def _table_exists(conn, name):
    return inspect(conn).has_table(name)


def _column_exists(conn, table, column):
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def _index_exists(conn, table, index):
    return index in [i["name"] for i in inspect(conn).get_indexes(table)]


def _constraint_exists(conn, table, constraint):
    return constraint in [c["name"] for c in inspect(conn).get_unique_constraints(table)]


def upgrade() -> None:
    conn = op.get_bind()

    # interpretations: rename engine_used -> engine
    if _column_exists(conn, "interpretations", "engine_used") and not _column_exists(conn, "interpretations", "engine"):
        op.alter_column("interpretations", "engine_used", new_column_name="engine")
    elif _column_exists(conn, "interpretations", "engine_used") and _column_exists(conn, "interpretations", "engine"):
        op.drop_column("interpretations", "engine_used")
    elif not _column_exists(conn, "interpretations", "engine"):
        op.add_column("interpretations", sa.Column("engine", sa.String(50), nullable=False, server_default="openai"))

    # natal_charts.utc_datetime: make nullable
    cols = {c["name"]: c for c in inspect(conn).get_columns("natal_charts")}
    if "utc_datetime" in cols and not cols["utc_datetime"]["nullable"]:
        op.alter_column("natal_charts", "utc_datetime", existing_type=sa.DateTime(), nullable=True)

    # note_templates: make created_at and updated_at nullable
    cols = {c["name"]: c for c in inspect(conn).get_columns("note_templates")}
    if "created_at" in cols and not cols["created_at"]["nullable"]:
        op.alter_column("note_templates", "created_at", existing_type=sa.DateTime(), nullable=True)
    if "updated_at" in cols and not cols["updated_at"]["nullable"]:
        op.alter_column("note_templates", "updated_at", existing_type=sa.DateTime(), nullable=True)

    # client_intake: drop named unique constraint (replaced by unique index on token column)
    if _table_exists(conn, "client_intake"):
        if _constraint_exists(conn, "client_intake", "uq_client_intake_token"):
            op.drop_constraint("uq_client_intake_token", "client_intake", type_="unique")

    # client_portal_access: drop named constraints, recreate client_id index as unique
    if _table_exists(conn, "client_portal_access"):
        if _constraint_exists(conn, "client_portal_access", "uq_portal_client"):
            op.drop_constraint("uq_portal_client", "client_portal_access", type_="unique")
        if _constraint_exists(conn, "client_portal_access", "uq_portal_token"):
            op.drop_constraint("uq_portal_token", "client_portal_access", type_="unique")
        if _index_exists(conn, "client_portal_access", "ix_client_portal_access_client_id"):
            idxs = {i["name"]: i for i in inspect(conn).get_indexes("client_portal_access")}
            if not idxs["ix_client_portal_access_client_id"]["unique"]:
                op.drop_index("ix_client_portal_access_client_id", table_name="client_portal_access")
                op.create_index("ix_client_portal_access_client_id", "client_portal_access", ["client_id"], unique=True)
        else:
            op.create_index("ix_client_portal_access_client_id", "client_portal_access", ["client_id"], unique=True)
        if not _index_exists(conn, "client_portal_access", "ix_client_portal_access_token"):
            op.create_index("ix_client_portal_access_token", "client_portal_access", ["token"], unique=True)

    # users.email: enforce NOT NULL (registration is email-only) and drop the
    # redundant auto-named unique constraint (model uses unique index ix_users_email)
    cols = {c["name"]: c for c in inspect(conn).get_columns("users")}
    if "email" in cols and cols["email"]["nullable"]:
        op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)
    if "users_email_key" in [c["name"] for c in inspect(conn).get_unique_constraints("users")]:
        op.drop_constraint("users_email_key", "users", type_="unique")

    # calendar_export_logs: create if missing
    if not _table_exists(conn, "calendar_export_logs"):
        op.create_table(
            "calendar_export_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("month", sa.String(7), nullable=False),
            sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("event_types", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("error_msg", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_calendar_export_logs_user_id", "calendar_export_logs", ["user_id"])


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "calendar_export_logs"):
        if _index_exists(conn, "calendar_export_logs", "ix_calendar_export_logs_user_id"):
            op.drop_index("ix_calendar_export_logs_user_id", table_name="calendar_export_logs")
        op.drop_table("calendar_export_logs")

    if "users_email_key" not in [c["name"] for c in inspect(conn).get_unique_constraints("users")]:
        op.create_unique_constraint("users_email_key", "users", ["email"])
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)

    if _table_exists(conn, "client_portal_access"):
        if _index_exists(conn, "client_portal_access", "ix_client_portal_access_client_id"):
            op.drop_index("ix_client_portal_access_client_id", table_name="client_portal_access")
        op.create_index("ix_client_portal_access_client_id", "client_portal_access", ["client_id"], unique=False)
        op.create_unique_constraint("uq_portal_token", "client_portal_access", ["token"])
        op.create_unique_constraint("uq_portal_client", "client_portal_access", ["client_id"])

    if _table_exists(conn, "client_intake"):
        op.create_unique_constraint("uq_client_intake_token", "client_intake", ["token"])

    cols = {c["name"]: c for c in inspect(conn).get_columns("note_templates")}
    if "created_at" in cols:
        op.alter_column("note_templates", "created_at", existing_type=sa.DateTime(), nullable=False,
                        existing_server_default=sa.text("now()"))
    if "updated_at" in cols:
        op.alter_column("note_templates", "updated_at", existing_type=sa.DateTime(), nullable=False,
                        existing_server_default=sa.text("now()"))

    cols = {c["name"]: c for c in inspect(conn).get_columns("natal_charts")}
    if "utc_datetime" in cols:
        op.alter_column("natal_charts", "utc_datetime", existing_type=sa.DateTime(), nullable=False)

    if _column_exists(conn, "interpretations", "engine"):
        op.alter_column("interpretations", "engine", new_column_name="engine_used")
