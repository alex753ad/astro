"""Шаг 9.3 (термины, под sky_event): «окно» → «период» в чате — промпт и
ответ на чужую тему «world». Без флага — прежние тексты слово в слово."""
import pytest

from backend import flags
from backend.models import FeatureFlag


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


def _sky_for(db, user):
    db.add(FeatureFlag(key="sky_event", mode="users", user_ids=[user.id]))
    db.commit()
    flags.reset_cache()


def test_chat_prompt_terms():
    from backend.interpretation.rag_router import _system_prompt
    old = _system_prompt("К", [], "", "Т")
    new = _system_prompt("К", [], "", "Т", sky=True)
    assert "«окна»" in old and "свои окна" in old
    assert "окна" not in new and "Сроки и периоды" in new and "свои периоды" in new


@pytest.mark.parametrize("on", [False, True])
def test_chat_world_reply_real_path(client, db, monkeypatch, on):
    """Ручка чата: флаг — по ORM-карте ручки, ответ «world» без модели."""
    from unittest.mock import AsyncMock, patch
    from backend.interpretation import rag_router
    from backend.tests.test_rag_chat import auth_headers, make_chart, make_pro_user
    user = make_pro_user(db, email=f"world{int(on)}@example.com")
    c = make_chart(db, user.id)
    if on:
        _sky_for(db, user)
    with patch.object(rag_router, "_classify_topic", AsyncMock(return_value="world")), \
         patch.object(rag_router, "_sse_generator", side_effect=AssertionError("модель не нужна")):
        resp = client.post(f"/api/v1/chart/{c.id}/rag-chat",
                           json={"question": "Что с выборами?"}, headers=auth_headers(user))
    assert resp.status_code == 200
    if on:
        assert "благоприятный период" in resp.text and "окно" not in resp.text
    else:
        assert "открытое окно" in resp.text
