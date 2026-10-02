"""Вопросы о продукте и контекст P1 чата (решения владельца 02.10.2026)."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.auth.rate_limits import TIER_FLAGS
from backend.interpretation import rag_router
from backend.interpretation.chat_context import CANCEL, NAVIGATION, product_reply
from backend.payments.common import prices_on
from backend.tests.test_rag_chat import auth_headers, make_chart, make_pro_user


@pytest.mark.parametrize("raw,label", [
    ("tariffs", "tariffs"), ("quota", "quota"), ("cancel", "cancel"),
    ("navigation", "navigation"), ("money", "money"), ("astrology", "astrology"),
    ("что-то своё", "astrology"),
])
def test_labels(raw, label):
    assert rag_router._label_from_reply(raw) == label


def test_classifier_prompt_names_tariffs_and_memory():
    p = rag_router._TOPIC_CLASSIFIER_PROMPT
    assert "Вега, Лира и Орион — это тарифы" in p
    assert "что Аристея помнит" in p


def test_tariffs_numbers_from_code():
    text = product_reply("tariffs", "lite")
    price = prices_on()
    for t in ("lite", "pro", "premium"):
        assert f"{price[t]} ₽" in text
    assert f"{TIER_FLAGS['lite']['chat_per_month']} сообщений в чате в месяц" in text
    assert "Сейчас у тебя — Вега." in text


def test_quota_texts():
    assert product_reply("quota", "pro") == "На Лире чат без лимита — пиши сколько нужно."
    lite = product_reply("quota", "lite", 12, "month", {"resets_on": None, "access_until": "2026-10-31"})
    assert lite == f"Осталось 12 из {TIER_FLAGS['lite']['chat_per_month']} — до 31 октября."
    free = product_reply("quota", "free", 2, "trial")
    assert free.startswith("На бесплатном — 3 сообщения на пробу, осталось 2.")


def test_cancel_and_navigation_fixed():
    assert product_reply("cancel", "lite") == CANCEL
    assert product_reply("navigation", "lite") == NAVIGATION
    assert "carearistea@mail.ru" in CANCEL and "10 дней" in CANCEL


def test_money_reply_has_no_periods():
    text = rag_router.OFF_TOPIC_REPLIES["money"]
    assert "второй и восьмой дома" in text and "период" not in text


def test_where_rules_only_with_p1():
    base = rag_router._system_prompt("К", [], "", "Т")
    with_p1 = rag_router._system_prompt("К", [], "", "Т", p1_block="## День\nX\n")
    assert "Чего нет в данных" not in base
    assert "Чего нет в данных" in with_p1 and "## День" in with_p1


def test_empty_memory_rule():
    assert "пока ничего не сохранила" in rag_router._system_prompt("К", [], "", "Т")
    assert "пока ничего не сохранила" not in rag_router._system_prompt("К", [], "факт", "Т")


def test_product_question_gets_code_reply_without_model(client: TestClient, db: Session):
    """Ответ о продукте — из кода, основная модель не зовётся, сообщение не
    списывается (нет background)."""
    user = make_pro_user(db, email="product1@example.com")
    chart = make_chart(db, user.id)
    with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="quota")), \
         patch.object(rag_router, "_sse_generator", side_effect=AssertionError("модель не нужна")):
        resp = client.post(f"/api/v1/chart/{chart.id}/rag-chat",
                           json={"question": "Сколько сообщений осталось?"}, headers=auth_headers(user))
    assert resp.status_code == 200
    assert "На Лире чат без лимита" in resp.text
