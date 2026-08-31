"""client_profiles.astrologer_id — индекс (AUDIT 5.3).

Каждая ручка CRM фильтрует клиентов через
`ClientProfile.astrologer_id == astrologer.id` (crm/router.py,
crm/dashboard_router.py, tasks.py) — граница изоляции между
астрологами, проходимая на каждом запросе, а не редкий отчёт. До этой
правки индекса на колонке не было — каждый такой запрос был полным
сканом таблицы по всем астрологам сразу.
"""

from sqlalchemy import inspect

from backend.models import ClientProfile


def test_astrologer_id_column_is_indexed():
    assert ClientProfile.__table__.c.astrologer_id.index is True


def test_index_is_created_in_db(db):
    inspector = inspect(db.get_bind())
    index_columns = [
        col
        for ix in inspector.get_indexes("client_profiles")
        for col in ix["column_names"]
    ]
    assert "astrologer_id" in index_columns
