"""Полная очистка БД — удаляет все таблицы, индексы, sequences."""
from sqlalchemy import create_engine, text
from backend.config import get_settings

e = create_engine(get_settings().database_url)

with e.connect() as conn:
    conn.execute(text("DROP SCHEMA public CASCADE"))
    conn.execute(text("CREATE SCHEMA public"))
    conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    conn.commit()

print("✓ Schema очищена — можно запускать alembic upgrade head")
