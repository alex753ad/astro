"""users.consent_* — согласие на обработку ПДн при регистрации (152-ФЗ)

Раньше AuthModal.jsx не показывал ни чекбокса, ни ссылок на оферту/политику —
пользователь ничего не подтверждал явно, хотя оферта §2 объявляет регистрацию
акцептом. Три колонки: сам факт+момент согласия и версии документов (оферта
и политика могут обновляться независимо, нужно доказуемо знать, с какой
редакцией согласился конкретный пользователь).

На проде пользователей нет (подтверждено владельцем 19.08.2026) — обратная
совместимость не требуется, но на случай непустой таблицы (локальная БД
разработчика) колонки сперва nullable + бэкфилл, потом NOT NULL — не падает
независимо от состояния данных.

Revision ID: 047_consent_tracking
Revises: 046_partner_visits
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "047_consent_tracking"
down_revision = "046_partner_visits"
branch_labels = None
depends_on = None

# Версия документов на момент введения обязательного согласия — для бэкфилла
# существующих строк (если такие найдутся). Источник истины на будущее —
# CURRENT_TERMS_VERSION / CURRENT_PRIVACY_VERSION в backend/auth/consent.py,
# эта константа здесь не обновляется вместе с ними.
_LEGACY_VERSION = "2026-08-19"


def _column_exists(conn, table, column):
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "users", "consent_given_at"):
        op.add_column("users", sa.Column("consent_given_at", sa.DateTime(), nullable=True))
    if not _column_exists(conn, "users", "consent_terms_version"):
        op.add_column("users", sa.Column("consent_terms_version", sa.String(20), nullable=True))
    if not _column_exists(conn, "users", "consent_privacy_version"):
        op.add_column("users", sa.Column("consent_privacy_version", sa.String(20), nullable=True))

    # Бэкфилл на случай непустой таблицы: created_at как момент согласия
    # (регистрация = акцепт оферты, см. TermsPage.jsx §2), версия — «legacy».
    op.execute(
        f"""
        UPDATE users
        SET consent_given_at = created_at,
            consent_terms_version = '{_LEGACY_VERSION}',
            consent_privacy_version = '{_LEGACY_VERSION}'
        WHERE consent_given_at IS NULL
        """
    )

    op.alter_column("users", "consent_given_at", existing_type=sa.DateTime(), nullable=False)
    op.alter_column("users", "consent_terms_version", existing_type=sa.String(20), nullable=False)
    op.alter_column("users", "consent_privacy_version", existing_type=sa.String(20), nullable=False)


def downgrade() -> None:
    conn = op.get_bind()
    for col in ("consent_given_at", "consent_terms_version", "consent_privacy_version"):
        if _column_exists(conn, "users", col):
            op.drop_column("users", col)
