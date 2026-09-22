"""Password hashing на bcrypt напрямую + единая политика паролей."""

import bcrypt

# bcrypt использует только первые 72 байта и молча отбрасывает остаток:
# без явной проверки два разных длинных пароля оказывались эквивалентны.
# Ограничение в байтах, а не символах — кириллица занимает по 2 байта.
BCRYPT_MAX_BYTES = 72

# Столько же, сколько ставил passlib по умолчанию (`passlib.hash.bcrypt.
# default_rounds == 12`), — проверено исполнением на passlib 1.7.4 перед
# переходом. Менять нельзя молча: старые хеши останутся на 12, новые уедут
# на другое число, и стоимость входа разойдётся между аккаунтами.
BCRYPT_ROUNDS = 12

MIN_PASSWORD_LENGTH = 8

# Пароли, которые перебираются первыми в любой атаке по словарю.
COMMON_PASSWORDS = frozenset({
    "12345678", "123456789", "1234567890", "password", "password1",
    "password123", "qwerty123", "qwertyui", "11111111", "00000000",
    "abc12345", "iloveyou", "princess", "admin123", "welcome1",
    "monkey123", "dragon123", "sunshine", "football", "baseball",
    "superman", "trustno1", "starwars", "whatever", "zaq12wsx",
    "qazwsxedc", "1q2w3e4r", "1qaz2wsx", "qwerty12", "asdfghjk",
    "passw0rd", "p@ssw0rd", "letmein1", "changeme", "newpassword",
    "parol123", "privet123", "lyubov123", "rossiya1", "spartak1",
})


def validate_password(plain: str) -> str:
    """Единая политика паролей для регистрации и сброса.

    Raises:
        ValueError: с текстом, пригодным для показа пользователю.
    """
    if len(plain) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль минимум {MIN_PASSWORD_LENGTH} символов.")

    byte_length = len(plain.encode("utf-8"))
    if byte_length > BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Пароль слишком длинный: {byte_length} байт при максимуме "
            f"{BCRYPT_MAX_BYTES}. Кириллица занимает по 2 байта на символ."
        )

    if plain.isdigit():
        raise ValueError("Пароль не может состоять только из цифр.")

    if plain.lower() in COMMON_PASSWORDS:
        raise ValueError("Этот пароль слишком распространён. Выберите другой.")

    return plain


def _secret(plain: str) -> bytes:
    """Секрет для bcrypt: utf-8, обрезанный до 72 байт.

    ⚠️ Обрезку удалять нельзя ни здесь, ни у вызывающих. passlib обрезал
    молча, bcrypt 5.x на секрете длиннее 72 байт кидает ValueError. Старые
    хеши длинных паролей посчитаны ОТ ОБРЕЗАННОГО секрета, поэтому обрезка
    обязана стоять в обоих местах — и в hash, и в verify:

    * без неё в verify человек со старым длинным паролем получит 500 вместо
      входа (`/auth/login` пароль не валидирует вовсе — LoginRequest без
      валидаторов, длина долетает до хешера как есть);
    * без неё в hash новый хеш разойдётся с тем, что проверяет verify.

    Срез по байтам может разрубить многобайтный символ — это нормально и
    совпадает с тем, что делал bcrypt под passlib: на вход идут байты, а не
    текст.
    """
    return plain.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    """Hash a plain-text password. Формат — тот же `$2b$12$…`, что у passlib."""
    return bcrypt.hashpw(_secret(plain), bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    """Verify a plain-text password against a hash.

    Возвращает False, а не исключение, на пустом/NULL хеше (аккаунты Google
    заводятся с `hashed_password=None`) и на битой строке: иначе такой
    аккаунт отдавал бы 500 вместо «неверный пароль».
    """
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_secret(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
