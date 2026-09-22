"""Регрессия перехода с passlib на bcrypt напрямую (22.09.2026).

Проверяется ровно то, что могло сломаться молча: старые хеши и граница в
72 байта. Хеши-фикстуры ниже созданы НАСТОЯЩИМ passlib 1.7.4
(`CryptContext(schemes=["bcrypt"], deprecated="auto")`, rounds по умолчанию
12) на bcrypt 4.0.1 и записаны сюда строками — иначе после удаления passlib
из зависимостей их нечем было бы получить, а проверка «старый пароль всё ещё
входит» осталась бы без старого хеша.
"""

import re
from pathlib import Path

import bcrypt
import pytest

from backend.auth.passwords import (
    BCRYPT_MAX_BYTES,
    BCRYPT_ROUNDS,
    hash_password,
    verify_password,
)

# passlib 1.7.4, пароль "Astrea-Legacy-2026"
PASSLIB_HASH_SHORT = "$2b$12$uZTiyhIAw5D.M4NYoWJTUOi15FX8dKeej2gkNPUBb.Tbk.XkficDe"
PASSLIB_PLAIN_SHORT = "Astrea-Legacy-2026"

# passlib 1.7.4, пароль "п" * 50 — это 100 байт, то есть длиннее 72.
# Такие аккаунты существуют: запрет на длинный пароль появился только
# 18.07.2026 (`6d1b4b8`), а заведённые до него хеши посчитаны от обрезанного
# секрета и обязаны продолжать работать.
PASSLIB_HASH_LONG = "$2b$12$oEkFYLsN8hHobGJsjld5Aem5cvthDSM3k2Uy6gchMFH3ZalVK4LvC"
PASSLIB_PLAIN_LONG = "п" * 50


class TestLegacyHashesStillVerify:

    def test_passlib_hash_accepted(self):
        assert verify_password(PASSLIB_PLAIN_SHORT, PASSLIB_HASH_SHORT)

    def test_wrong_password_rejected(self):
        assert not verify_password("не тот пароль", PASSLIB_HASH_SHORT)

    def test_format_unchanged(self):
        """Новые хеши той же формы и той же стоимости, что писал passlib."""
        hashed = hash_password(PASSLIB_PLAIN_SHORT)
        assert hashed.startswith(f"$2b${BCRYPT_ROUNDS:02d}$")
        assert verify_password(PASSLIB_PLAIN_SHORT, hashed)


class TestLongSecretDoesNotRaise:
    """⚠️ Без обрезки до 72 байт bcrypt 5.x кидает ValueError, а не False.

    `/auth/login` пароль не валидирует (LoginRequest без валидаторов), то есть
    человек со старым длинным паролем получил бы 500 вместо входа.
    """

    def test_legacy_long_password_verifies(self):
        assert len(PASSLIB_PLAIN_LONG.encode("utf-8")) > BCRYPT_MAX_BYTES
        assert verify_password(PASSLIB_PLAIN_LONG, PASSLIB_HASH_LONG)

    def test_new_hash_of_long_password_round_trips(self):
        hashed = hash_password(PASSLIB_PLAIN_LONG)
        assert verify_password(PASSLIB_PLAIN_LONG, hashed)

    def test_verify_of_long_password_against_short_hash_is_false(self):
        assert not verify_password("a" * 200, PASSLIB_HASH_SHORT)


class TestBrokenHashIsFalseNotError:
    """Google-аккаунты заводятся с hashed_password=None."""

    @pytest.mark.parametrize("hashed", [None, "", "не хеш вовсе", "$2b$12$слишкомкоротко"])
    def test_no_exception(self, hashed):
        assert verify_password("Abcd1234", hashed) is False


class TestRuntimeIsBcrypt5:

    def test_major_version(self):
        major = int(bcrypt.__version__.split(".")[0])
        assert major >= 5, f"ожидался bcrypt 5.x, установлен {bcrypt.__version__}"

    def test_passlib_is_not_a_dependency(self):
        """Проверяется объявление, а не окружение.

        В окружение passlib может остаться от прошлой установки (у него нет
        зависимых пакетов, `uv pip sync` его не всегда выметает), и проверка
        «не импортируется» была бы красной на исправном коде. Красным обязано
        быть другое: passlib вернулся в зависимости или в исходники.
        """
        root = Path(__file__).resolve().parents[2]

        # Ищется ОБЪЯВЛЕНИЕ, а не слово: в pyproject рядом лежит комментарий,
        # объясняющий, почему passlib убран, — он обязан пережить проверку.
        decl = [
            ln.strip() for ln in (root / "pyproject.toml").read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith('"passlib')
        ]
        assert not decl, decl
        for name in ("requirements.lock", "requirements-dev.lock"):
            pins = [
                ln for ln in (root / name).read_text(encoding="utf-8").splitlines()
                if ln.startswith("passlib==")
            ]
            assert not pins, (name, pins)

        sources = [
            f for f in (root / "backend").rglob("*.py")
            if "tests" not in f.parts
        ]
        assert len(sources) > 50, "разбор исходников ничего не нашёл"
        # Тоже объявление, а не слово: комментарии про passlib в
        # `auth/passwords.py` объясняют, откуда взялись rounds, и обязаны жить.
        imports = re.compile(r"^\s*(import passlib|from passlib)", re.M)
        for f in sources:
            assert not imports.search(f.read_text(encoding="utf-8")), f
