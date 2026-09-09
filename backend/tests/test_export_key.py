"""Ключ часового лимита /profile/export считается по user_id, а не по строке токена.

Тот же дефект, что был у rag_chat_key, и та же правка: `_base_id` брал первые 60
символов JWT, из которых на пользователя приходились 8 hex-символов UUID
(заголовок занимает 36 символов, точка ещё один, на payload остаётся кусок,
декодирующийся как `{"sub":"0f8c1a2b-`). Два аккаунта с совпадающим НАЧАЛОМ
идентификатора делили одно ведро.

Здесь ведро — 3 запроса в час против 20 у чата, поэтому склейка ощутимее:
выгрузка своих ПДн по 152-ФЗ отбивалась бы 429 из-за чужой выгрузки.
"""

from __future__ import annotations

from starlette.requests import Request

from backend.auth.jwt import create_access_token, create_token_pair
from backend.auth.rate_limits import export_key


def _request(token: str | None) -> Request:
    """Минимальный ASGI-scope: ключу нужны только заголовки и адрес клиента."""
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/profile/export",
        "headers": headers,
        "client": ("203.0.113.7", 51234),
        "query_string": b"",
    })


class TestExportKeySeparatesUsers:
    def test_ids_sharing_a_prefix_do_not_share_a_bucket(self):
        """Главный кейс: два UUID, различающиеся ПОСЛЕ восьмого символа."""
        a = "0f8c1a2b-1111-4444-8888-aaaaaaaaaaaa"
        b = "0f8c1a2b-2222-4444-8888-bbbbbbbbbbbb"

        key_a = export_key(_request(create_access_token(a, "a@example.com")))
        key_b = export_key(_request(create_access_token(b, "b@example.com")))

        assert key_a != key_b

    def test_does_not_collide_with_the_chat_bucket(self):
        """Два лимита у одного человека независимы: выгрузка не должна
        расходовать часовое ведро чата и наоборот."""
        from backend.auth.rate_limits import rag_chat_key

        req = _request(create_access_token("0f8c1a2b-1111-4444-8888-aaaaaaaaaaaa", "a@example.com"))
        assert export_key(req) != rag_chat_key(req)


class TestExportKeySurvivesRefresh:
    """Обновление токена НЕ обнуляет лимит.

    Выгрузка тяжёлая (все карты, интерпретации, платежи), и лимит, который
    сбрасывается каждым refresh, не ограничивал бы ничего. Свойство было и до
    правки, но держалось на том, что claim `sub` стоит в payload первым.
    """

    def test_two_tokens_of_one_user_give_one_key(self):
        user_id = "0f8c1a2b-1111-4444-8888-aaaaaaaaaaaa"
        first = create_token_pair(user_id, "a@example.com", "free").access_token
        second = create_token_pair(user_id, "a@example.com", "free").access_token

        assert first != second, "токены обязаны различаться, иначе тест ничего не проверяет"
        assert export_key(_request(first)) == export_key(_request(second))


class TestExportKeyDegradesSafely:
    """Ключ считается до обработчика и падать не имеет права: исключение здесь
    превратило бы протухший токен в 500 вместо честного 401."""

    def test_no_token_falls_back_to_ip(self):
        assert "203.0.113.7" in export_key(_request(None))

    def test_garbage_token_does_not_raise(self):
        assert export_key(_request("не-настоящий-токен"))
