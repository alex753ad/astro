"""Password hashing with bcrypt via passlib + единая политика паролей."""

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt использует только первые 72 байта и молча отбрасывает остаток:
# без явной проверки два разных длинных пароля оказывались эквивалентны.
# Ограничение в байтах, а не символах — кириллица занимает по 2 байта.
BCRYPT_MAX_BYTES = 72

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


def hash_password(plain: str) -> str:
    """Hash a plain-text password."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a hash."""
    return pwd_context.verify(plain, hashed)
