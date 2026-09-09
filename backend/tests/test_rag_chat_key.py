"""Ключ часового лимита /rag-chat считается по user_id, а не по строке токена.

До 09.09.2026 ключом были первые 60 символов JWT (`_base_id`). На пользователя
из них приходились 8 hex-символов UUID: заголовок занимает 36 символов, точка
ещё один, и на payload остаётся кусок, который декодируется как
`{"sub":"0f8c1a2b-`. Значит два аккаунта с совпадающим НАЧАЛОМ идентификатора
делили одно ведро на 20 запросов в час.

Второе, что здесь проверяется, — свойство, которое нельзя потерять: ключ обязан
переживать обновление токена. Оно было и раньше, но держалось на случайности
(claim `sub` стоит в payload первым).
"""

from __future__ import annotations

from starlette.requests import Request

from backend.auth.jwt import create_access_token, create_token_pair
from backend.auth.rate_limits import rag_chat_key


def _request(token: str | None) -> Request:
    """Минимальный ASGI-scope: ключу нужны только заголовки и адрес клиента."""
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chart/x/rag-chat",
        "headers": headers,
        "client": ("203.0.113.7", 51234),
        "query_string": b"",
    })


class TestRagChatKeySeparatesUsers:
    def test_ids_sharing_a_prefix_do_not_share_a_bucket(self):
        """Главный кейс. Два UUID, различающиеся ПОСЛЕ восьмого символа, —
        ровно тот случай, который старый ключ склеивал в одно ведро."""
        a = "0f8c1a2b-1111-4444-8888-aaaaaaaaaaaa"
        b = "0f8c1a2b-2222-4444-8888-bbbbbbbbbbbb"

        key_a = rag_chat_key(_request(create_access_token(a, "a@example.com")))
        key_b = rag_chat_key(_request(create_access_token(b, "b@example.com")))

        assert key_a != key_b

    def test_key_contains_the_user_id(self):
        user_id = "0f8c1a2b-1111-4444-8888-aaaaaaaaaaaa"
        key = rag_chat_key(_request(create_access_token(user_id, "a@example.com")))
        assert user_id in key


class TestRagChatKeySurvivesRefresh:
    """Обновление токена НЕ обнуляет лимит.

    Свойство было и до правки, но держалось на том, что `sub` стоит в payload
    первым и меняющиеся jti/iat/exp не попадали в первые 60 символов. Перестановка
    claim'ов местами обнуляла бы лимит на каждом refresh — то есть лимита не
    стало бы вовсе, и заметить это можно было бы только по счетам за API.
    """

    def test_two_tokens_of_one_user_give_one_key(self):
        user_id = "0f8c1a2b-1111-4444-8888-aaaaaaaaaaaa"
        first = create_token_pair(user_id, "a@example.com", "pro").access_token
        second = create_token_pair(user_id, "a@example.com", "pro").access_token

        assert first != second, "токены обязаны различаться, иначе тест ничего не проверяет"
        assert rag_chat_key(_request(first)) == rag_chat_key(_request(second))


class TestRagChatKeyDegradesSafely:
    """Ключ считается ДО обработчика и не имеет права падать: исключение здесь
    превратило бы протухший или подделанный токен в 500 вместо честного 401."""

    def test_no_token_falls_back_to_ip(self):
        assert "203.0.113.7" in rag_chat_key(_request(None))

    def test_garbage_token_does_not_raise(self):
        assert rag_chat_key(_request("не-настоящий-токен")) 

    def test_forged_token_gets_its_own_bucket(self):
        """Ключ выводится из ПРОВЕРЕННОЙ подписи, а не из строки токена.

        ⚠️ Дырой в проде это не было, и выдавать за дыру не надо. Проверено
        исполнением 09.09.2026: `key_func` не вызывается вовсе для запросов,
        отбитых зависимостями, — битый токен даёт 401, free даёт 403, и в
        обоих случаях счётчик ключа не трогается ни разу. То есть выбрать
        чужие 20 запросов в час подделкой было нельзя и раньше: до лимитера
        такой запрос не доходит.

        Смысл теста — вперёд: ключ не должен зависеть от байтов, которые
        может выбирать отправитель. Прежний `_base_id` брал первые 60
        символов строки токена как есть, и совпадение ключа у honest и
        tampered токена было прямым следствием.
        """
        victim = "0f8c1a2b-1111-4444-8888-aaaaaaaaaaaa"
        forged = create_access_token(victim, "a@example.com") + "tampered"

        honest_key = rag_chat_key(_request(create_access_token(victim, "a@example.com")))
        forged_key = rag_chat_key(_request(forged))

        assert forged_key != honest_key
