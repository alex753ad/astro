"""Имя карты доезжает до записи и читается обратно.

До 07.09.2026 `NatalChart.name`/`.label` существовали в модели, а
`BirthDataInput.name` принимался клиентом, но ни `POST /chart/calculate`,
ни `POST /chart/save-anonymous` его не передавали при создании записи —
значение было всегда NULL (CLAUDE.md, «Открытые задачи», п. 1).

Разведка 07.09.2026: `label` и `name` — один и тот же концепт (пользовательское
имя карты), `label` с самого начала не имеет ни одного писателя и ни одного
читателя, кроме одной строки в `/profile/export`, которая отдаёт его как есть
(то есть всегда NULL). Поэтому заполняется только `name` — заполнять оба
значило бы завести второй источник истины для одного и того же поля без
всякой причины. Разбор — models.py, комментарий у `NatalChart.label`.

Мок ставится на всех уровнях, где закреплён `_GEOCODE_PATCH_TARGETS`
(conftest.py) — реальный Nominatim не вызывается.
"""

from backend.models import NatalChart


class TestChartNameCalculate:
    def test_name_is_persisted(self, client, db, mock_calculator, mock_geo, auth_headers_free):
        resp = client.post(
            "/api/v1/chart/calculate",
            json={
                "name": "Мама",
                "birth_date": "1990-01-10",
                "birth_time": "12:00",
                "birth_place": "Moscow",
                "house_system": "placidus",
            },
            headers=auth_headers_free,
        )
        assert resp.status_code == 200, resp.text
        chart_id = resp.json()["id"]

        row = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
        assert row.name == "Мама"
        # Разведённое поле остаётся NULL — заполняется только name.
        assert row.label is None

    def test_name_reads_back_in_response(self, client, mock_calculator, mock_geo, auth_headers_free):
        # Требование задачи: не только запись в БД, но и то, что клиент
        # реально получает это значение обратно — раньше NatalChartResponse
        # не включал name вовсе, и даже заполненное в БД имя было неоткуда
        # взять фронтенду без второго запроса.
        resp = client.post(
            "/api/v1/chart/calculate",
            json={
                "name": "Мама",
                "birth_date": "1990-01-10",
                "birth_time": "12:00",
                "birth_place": "Moscow",
                "house_system": "placidus",
            },
            headers=auth_headers_free,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Мама"

    def test_name_omitted_stays_null(self, client, db, mock_calculator, mock_geo, auth_headers_free):
        # Имя необязательно (BirthDataInput.name: Optional) — его отсутствие
        # не должно превращаться в пустую строку или падать.
        resp = client.post(
            "/api/v1/chart/calculate",
            json={
                "birth_date": "1990-01-10",
                "birth_time": "12:00",
                "birth_place": "Moscow",
                "house_system": "placidus",
            },
            headers=auth_headers_free,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] is None

        row = db.query(NatalChart).filter(NatalChart.id == resp.json()["id"]).first()
        assert row.name is None

    def test_name_persisted_for_anonymous_too(self, client, db, mock_calculator, mock_geo):
        # Ручка обслуживает и анонимов (user=None) — писатель не должен
        # зависеть от аутентификации.
        resp = client.post(
            "/api/v1/chart/calculate",
            json={
                "name": "Гостевая карта",
                "birth_date": "1990-01-10",
                "birth_time": "12:00",
                "birth_place": "Moscow",
                "house_system": "placidus",
            },
        )
        assert resp.status_code == 200, resp.text
        row = db.query(NatalChart).filter(NatalChart.id == resp.json()["id"]).first()
        assert row.name == "Гостевая карта"


class TestChartNameSaveAnonymous:
    def test_name_is_persisted_and_reads_back(self, client, db, mock_calculator, mock_geo, auth_headers_free):
        resp = client.post(
            "/api/v1/chart/save-anonymous",
            json={
                "name": "Ребёнок",
                "birth_date": "2015-06-01",
                "birth_time": "08:00",
                "birth_place": "Moscow",
                "house_system": "placidus",
            },
            headers=auth_headers_free,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["name"] == "Ребёнок"

        row = db.query(NatalChart).filter(NatalChart.id == data["id"]).first()
        assert row.name == "Ребёнок"
        assert row.label is None


class TestChartNameGet:
    def test_name_returned_by_get_chart(self, client, mock_calculator, mock_geo, auth_headers_free):
        # Полный круг: создали с именем — прочитали ОТДЕЛЬНЫМ запросом
        # GET /chart/{id} (тем же путём, каким мобильный экран «Карта»
        # получает данные при открытии) — имя на месте.
        created = client.post(
            "/api/v1/chart/calculate",
            json={
                "name": "Партнёр",
                "birth_date": "1990-01-10",
                "birth_time": "12:00",
                "birth_place": "Moscow",
                "house_system": "placidus",
            },
            headers=auth_headers_free,
        )
        chart_id = created.json()["id"]

        got = client.get(f"/api/v1/chart/{chart_id}", headers=auth_headers_free)
        assert got.status_code == 200, got.text
        assert got.json()["name"] == "Партнёр"


class TestChartNameInList:
    def test_name_returned_by_profile_charts(self, client, mock_calculator, mock_geo, auth_headers_free):
        # /profile/charts кормит список карт на экране «Ещё» мобильного
        # приложения (MoreCardsList.jsx) — исходная жалоба в CLAUDE.md была
        # именно про то, что этот список не может подписать карту именем.
        client.post(
            "/api/v1/chart/calculate",
            json={
                "name": "Мама",
                "birth_date": "1990-01-10",
                "birth_time": "12:00",
                "birth_place": "Moscow",
                "house_system": "placidus",
            },
            headers=auth_headers_free,
        )

        resp = client.get("/api/v1/profile/charts", headers=auth_headers_free)
        assert resp.status_code == 200, resp.text
        charts = resp.json()["charts"]
        assert len(charts) == 1
        assert charts[0]["name"] == "Мама"
