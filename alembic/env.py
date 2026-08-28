from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Добавляем корень проекта в путь чтобы backend импортировался
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Base
import backend.models  # noqa: F401 — регистрирует все модели

config = context.config

# Читаем DATABASE_URL из .env если не задан явно
from dotenv import load_dotenv
load_dotenv()

database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# Таблицы, которые есть в БД, но намеренно НЕ описаны моделями в
# backend/models.py. Их создаёт миграция 043_promo_codes.py, а работает с ними
# backend/admin/promo_router.py — сырым SQL через text() (строки 78, 84, 113,
# 144, 185, 205), без ORM. Метаданные Base о них поэтому не знают.
#
# Без этого списка autogenerate видит таблицы в базе, не находит в метаданных и
# считает лишними: сгенерированная миграция начинается с drop_table для обеих.
# Применить такую — потерять промокоды. Проверка check-migrations в CI из-за
# этого падала на каждом запуске.
#
# Список именно перечисляет две таблицы поимённо, а не отключает сравнение для
# всего, чего нет в моделях: иначе проверка перестанет ловить ровно то, ради
# чего включена, — модель, изменённую без миграции.
#
# ⚠️ Когда для promo_codes/promo_usages появятся модели — убрать их отсюда,
# иначе расхождение этих таблиц со схемой перестанет замечаться. Заведение
# моделей — часть отдельной задачи про промокоды целиком (эндпоинта
# /payments/promo-validate не существует, record_promo_usage никто не вызывает;
# полный список — в докстринге record_promo_usage).
TABLES_WITHOUT_MODELS = {"promo_codes", "promo_usages"}


def include_object(object, name, type_, reflected, compare_to):
    """Что autogenerate сравнивает, а что пропускает."""
    if type_ == "table":
        return name not in TABLES_WITHOUT_MODELS
    # Индексы этих таблиц — отдельные объекты сравнения, и в упавшем прогоне
    # они попали в диff своими строками drop_index. Гасим их вместе с таблицей.
    if type_ == "index" and object.table is not None:
        return object.table.name not in TABLES_WITHOUT_MODELS
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # include_object нужен только autogenerate, а он работает в online-режиме
        # (offline его не поддерживает) — поэтому в run_migrations_offline выше
        # параметр не дублируется.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()