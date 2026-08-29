"""POST /chart/{id}/pdf — тарифный гейт и лимит интерпретаций.

До 30.08.2026 в теле хендлера не было ни pdf_export, ни pdf_per_month, ни
любого обращения к TierRateLimiter — проверялся только доступ к карте. Плюс
при отсутствии строки в Interpretation хендлер сам звал ai_router.generate
мимо check_interpretation_limit. Бесплатный пользователь получал два платных
пункта сетки — PDF и AI-разбор — не потратив ни одной квоты.

Уже сохранённые строки с engine="pdf" при этом не трогались: они получены
бесплатно, но отбирать выданное хуже, чем оставить.
"""

import pytest

from backend.auth.rate_limits import get_monthly_usage, increment_monthly_usage
from backend.tests.test_chart_access import _make_chart


@pytest.fixture
def user_lite(db, user_free):
    """Вега: PDF разрешён (pdf_per_month=5), интерпретаций 5 в месяц."""
    user_free.tier = "lite"
    db.commit()
    return user_free


@pytest.fixture
def no_pdf_render(monkeypatch):
    """ReportLab здесь ни при чём — проверяются гейты, а не вёрстка файла."""
    monkeypatch.setattr("backend.natal_pdf.generate_pdf_bytes", lambda *a, **kw: b"%PDF-1.4 test")


@pytest.fixture
def fake_interpretation(monkeypatch):
    """AI не зовём: интересует расход квоты, а не текст."""
    class _Result:
        content = "Разбор карты для теста."
        engine = "deepseek"
        sections = None

    async def _generate(self, request):
        return _Result()

    monkeypatch.setattr(
        "backend.interpretation.router.InterpretationRouter.generate", _generate
    )


class TestFreeIsRefused:
    def test_free_gets_refusal_not_a_file(
        self, client, db, user_free, auth_headers_free, no_pdf_render, fake_interpretation
    ):
        chart = _make_chart(db, user_id=user_free.id)

        resp = client.post(f"/api/v1/chart/{chart.id}/pdf", headers=auth_headers_free)

        assert resp.status_code == 403
        assert not resp.content.startswith(b"%PDF")

    def test_refusal_names_the_tier(
        self, client, db, user_free, auth_headers_free, no_pdf_render
    ):
        """Читаемый текст с названием тарифа, а не голый 403."""
        chart = _make_chart(db, user_id=user_free.id)

        detail = client.post(
            f"/api/v1/chart/{chart.id}/pdf", headers=auth_headers_free
        ).json()["detail"]

        assert isinstance(detail, str)
        assert len(detail) > 20
        assert "PDF" in detail

    def test_free_does_not_spend_interpretation(
        self, client, db, user_free, auth_headers_free, no_pdf_render, fake_interpretation
    ):
        """Гейт PDF стоит раньше — до генерации разбора дело не доходит."""
        chart = _make_chart(db, user_id=user_free.id)

        client.post(f"/api/v1/chart/{chart.id}/pdf", headers=auth_headers_free)

        db.refresh(chart)
        assert not chart.free_interpretation_used, "право на бесплатный разбор сгорело"


class TestPaidWithExhaustedInterpretations:
    def test_no_free_interpretation_through_pdf(
        self, client, db, user_lite, auth_headers_free, no_pdf_render, fake_interpretation
    ):
        """Квота интерпретаций исчерпана — PDF не должен стать обходным путём."""
        chart = _make_chart(db, user_id=user_lite.id)
        for _ in range(5):
            increment_monthly_usage(db, str(user_lite.id), "interpretation")

        resp = client.post(f"/api/v1/chart/{chart.id}/pdf", headers=auth_headers_free)

        assert resp.status_code == 429
        assert not resp.content.startswith(b"%PDF")

    def test_pdf_quota_not_spent_on_interpretation_refusal(
        self, client, db, user_lite, auth_headers_free, no_pdf_render, fake_interpretation
    ):
        """Отказ по интерпретациям не должен сжигать ещё и PDF-квоту."""
        chart = _make_chart(db, user_id=user_lite.id)
        for _ in range(5):
            increment_monthly_usage(db, str(user_lite.id), "interpretation")

        client.post(f"/api/v1/chart/{chart.id}/pdf", headers=auth_headers_free)

        db.expire_all()
        assert get_monthly_usage(db, str(user_lite.id), "pdf") == 0


class TestPaidWithQuota:
    def test_gets_pdf_and_spends_one_interpretation(
        self, client, db, user_lite, auth_headers_free, no_pdf_render, fake_interpretation
    ):
        chart = _make_chart(db, user_id=user_lite.id)
        before = get_monthly_usage(db, str(user_lite.id), "interpretation")

        resp = client.post(f"/api/v1/chart/{chart.id}/pdf", headers=auth_headers_free)

        assert resp.status_code == 200, resp.text
        assert resp.content.startswith(b"%PDF")

        db.expire_all()
        after = get_monthly_usage(db, str(user_lite.id), "interpretation")
        assert after == before + 1, "расход интерпретации не списан"

    def test_pdf_counter_increments(
        self, client, db, user_lite, auth_headers_free, no_pdf_render, fake_interpretation
    ):
        chart = _make_chart(db, user_id=user_lite.id)

        client.post(f"/api/v1/chart/{chart.id}/pdf", headers=auth_headers_free)

        db.expire_all()
        assert get_monthly_usage(db, str(user_lite.id), "pdf") == 1

    def test_existing_interpretation_costs_no_quota(
        self, client, db, user_lite, auth_headers_free, no_pdf_render, fake_interpretation
    ):
        """Разбор уже есть — генерации нет, значит и списывать нечего."""
        from backend.models import Interpretation

        chart = _make_chart(db, user_id=user_lite.id)
        db.add(Interpretation(
            chart_id=chart.id,
            profile_hash="testhash",
            engine="deepseek",
            content="Готовый разбор.",
            sections=None,
        ))
        db.commit()
        before = get_monthly_usage(db, str(user_lite.id), "interpretation")

        resp = client.post(f"/api/v1/chart/{chart.id}/pdf", headers=auth_headers_free)

        assert resp.status_code == 200
        db.expire_all()
        assert get_monthly_usage(db, str(user_lite.id), "interpretation") == before

    def test_exhausted_pdf_quota_is_refused(
        self, client, db, user_lite, auth_headers_free, no_pdf_render, fake_interpretation
    ):
        chart = _make_chart(db, user_id=user_lite.id)
        for _ in range(5):
            increment_monthly_usage(db, str(user_lite.id), "pdf")

        resp = client.post(f"/api/v1/chart/{chart.id}/pdf", headers=auth_headers_free)

        assert resp.status_code == 429
        assert not resp.content.startswith(b"%PDF")
