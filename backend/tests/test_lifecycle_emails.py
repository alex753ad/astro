"""Письма онбординга и после покупки: один путь, журнал, окна опоздания.

23.09.2026 письмо «Ваши тарифы на Aristea Timeline» пришло ~10 раз разом:
отложенная задача Celery (countdown 14 суток) дольше visibility timeout
Redis-брокера выдавалась воркеру заново каждый час. Вдобавок day2/day7 слали
два пути. Здесь закреплено то, что пришло на смену (backend/lifecycle_emails.py).
"""
from __future__ import annotations

import asyncio
import itertools
import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import lifecycle_emails as le
from backend.models import EmailSentLog, PaymentEvent, User
from backend.time_utils import utcnow

BACKEND = Path(__file__).resolve().parents[1]
_n = itertools.count(1)


@pytest.fixture
def sent(monkeypatch):
    """Все письма вместо Resend — в список (адрес, тема)."""
    out: list[tuple[str, str]] = []

    async def fake_send(to, subject, html):
        out.append((to, subject))
        return True

    monkeypatch.setattr("backend.email_service._send", fake_send)
    return out


@pytest.fixture
def with_chart(monkeypatch):
    """У каждого кандидата есть карта и транзит — эфемериды тут не проверяются."""
    event = SimpleNamespace(transit_planet="Venus", natal_planet="Sun", aspect_type="trine")
    monkeypatch.setattr(le, "_latest_charts_by_user",
                        lambda db, ids: {i: SimpleNamespace(planets=[]) for i in ids})
    monkeypatch.setattr("backend.transit.engine.calculate_transits", lambda **k: [event])


def _user(db, days_ago: float, tier="free") -> User:
    u = User(email=f"u{next(_n)}@example.com", tier=tier,
             created_at=utcnow() - timedelta(days=days_ago))
    db.add(u)
    db.commit()
    return u


def _purchase(db, user, tier, days_ago: float, starts_chain=True) -> PaymentEvent:
    pe = PaymentEvent(provider="yookassa", inv_id=f"p-{next(_n)}", user_id=user.id, tier=tier,
                      period="monthly", amount=100.0, starts_chain=starts_chain,
                      created_at=utcnow() - timedelta(days=days_ago))
    db.add(pe)
    db.commit()
    return pe


def _kinds(db, user) -> list[str]:
    return sorted(k for (k,) in db.query(EmailSentLog.kind).filter(EmailSentLog.user_id == user.id))


# ── Двойной запуск, догон, окно ─────────────────────────────

def test_double_beat_run_sends_once(db, sent):
    u = _user(db, 14.5)
    le.run_lifecycle_emails(db)
    le.run_lifecycle_emails(db)
    assert sent == [(u.email, "Ваши тарифы на Aristea Timeline")]
    assert _kinds(db, u) == ["retention_day14"]


def test_missed_days_are_caught_up(db, sent):
    """Beat пропустил двое суток (деплой, простой) — письмо всё равно уходит."""
    u = _user(db, 16)
    le.run_lifecycle_emails(db)
    assert [to for to, _ in sent] == [u.email]


def test_old_user_outside_window_gets_nothing(db, sent, with_chart):
    """Зарегистрирован полгода назад: ни day2, ни day7, ни day14."""
    u = _user(db, 180)
    le.run_lifecycle_emails(db)
    assert sent == []
    assert _kinds(db, u) == []


@pytest.mark.parametrize("days_ago, kind", [
    (2.1, "retention_day2"), (4.9, "retention_day2"),
    (7.1, "retention_day7"), (10.9, "retention_day7"),
    (14.1, "retention_day14"), (20.9, "retention_day14"),
])
def test_inside_window_sends_exactly_that_letter(db, sent, with_chart, days_ago, kind):
    u = _user(db, days_ago)
    le.run_lifecycle_emails(db)
    assert _kinds(db, u) == [kind]
    assert len(sent) == 1


@pytest.mark.parametrize("days_ago", [1.9, 5.1, 6.9, 11.1, 13.9, 21.1])
def test_between_windows_sends_nothing(db, sent, with_chart, days_ago):
    """Окна не пересекаются: после простоя два письма в один день не придут."""
    _user(db, days_ago)
    le.run_lifecycle_emails(db)
    assert sent == []


def test_day2_waits_for_chart_without_burning_the_slot(db, sent, monkeypatch):
    """Нет карты — письма нет, но и строки в журнале нет: построит карту
    внутри окна — письмо придёт."""
    monkeypatch.setattr(le, "_latest_charts_by_user", lambda db, ids: {})
    u = _user(db, 2.5)
    le.run_lifecycle_emails(db)
    assert sent == [] and _kinds(db, u) == []


def test_paid_user_gets_no_free_nudges(db, sent, with_chart):
    _user(db, 7.5, tier="lite")
    _user(db, 14.5, tier="pro")
    le.run_lifecycle_emails(db)
    assert sent == []


# ── Письма после покупки ────────────────────────────────────

def test_repeat_purchase_sends_again(db, sent):
    """Раз на покупку, а не раз в жизни: ref = id платежа."""
    u = _user(db, 200, tier="lite")
    first = _purchase(db, u, "lite", days_ago=15)
    le.run_lifecycle_emails(db)
    le.run_lifecycle_emails(db)
    assert len(sent) == 1

    # Та же покупка «через полгода» — вторая оплата начала тариф заново.
    first.created_at = utcnow() - timedelta(days=200)
    db.commit()
    _purchase(db, u, "lite", days_ago=15)
    le.run_lifecycle_emails(db)
    assert len(sent) == 2
    refs = {r for (r,) in db.query(EmailSentLog.ref).filter(EmailSentLog.kind == "lite_day14")}
    assert len(refs) == 2


def test_renewal_payment_starts_no_letter(db, sent):
    u = _user(db, 200, tier="lite")
    _purchase(db, u, "lite", days_ago=15, starts_chain=False)
    le.run_lifecycle_emails(db)
    assert sent == []


def test_left_the_tier_gets_no_tier_letter(db, sent):
    u = _user(db, 200, tier="free")
    _purchase(db, u, "pro", days_ago=31)
    le.run_lifecycle_emails(db)
    assert sent == []


def test_welcome_once_per_purchase(db, sent):
    u = _user(db, 200, tier="pro")
    pe = _purchase(db, u, "pro", days_ago=0)
    assert le.send_purchase_welcome(db, pe.id) is True
    assert le.send_purchase_welcome(db, pe.id) is False
    pe2 = _purchase(db, u, "pro", days_ago=0)
    assert le.send_purchase_welcome(db, pe2.id) is True
    assert len(sent) == 2


def test_welcome_not_for_renewal(db, sent):
    u = _user(db, 200, tier="lite")
    pe = _purchase(db, u, "lite", days_ago=0, starts_chain=False)
    assert le.send_purchase_welcome(db, pe.id) is False
    assert sent == []


# ── Журнал: запись до отправки, откат при ошибке ────────────

def test_failed_send_leaves_no_row_and_is_retried(db, monkeypatch):
    calls = []

    async def failing(to, subject, html):
        calls.append(to)
        return False

    monkeypatch.setattr("backend.email_service._send", failing)
    u = _user(db, 14.5)
    le.run_lifecycle_emails(db)
    assert _kinds(db, u) == []

    async def ok(to, subject, html):
        calls.append(to)
        return True

    monkeypatch.setattr("backend.email_service._send", ok)
    le.run_lifecycle_emails(db)
    assert _kinds(db, u) == ["retention_day14"]
    assert len(calls) == 2


def test_existing_row_blocks_send(db, sent):
    """Строка уже есть (прогон-соперник закоммитил) — уникальный индекс, не SELECT."""
    u = _user(db, 14.5)
    db.add(EmailSentLog(user_id=u.id, kind="retention_day14", ref="", sent_at=None))
    db.commit()

    async def must_not_run():
        raise AssertionError("письмо не должно уходить")

    assert le.send_once(db, u.id, "retention_day14", "", must_not_run) is False


# ── Один путь ───────────────────────────────────────────────

_SENDERS = (
    "send_retention_day2", "send_retention_day7", "send_retention_day14",
    "send_lite_day14", "send_pro_day30",
    "send_lite_welcome", "send_pro_welcome", "send_premium_welcome",
)


def test_letters_have_exactly_one_caller():
    """Второго пути к этим письмам в коде нет: вызывает их только lifecycle_emails.

    Ищутся вызовы и ссылки на функцию (`send_x(`, `email_service.send_x`,
    `import send_x`), а не любое вхождение: имена снятых задач в tasks.py —
    строки вида "tasks.send_retention_day2", это не путь к письму."""
    callers: dict[str, set[str]] = {s: set() for s in _SENDERS}
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name == "email_service.py":
            continue
        src = path.read_text(encoding="utf-8")
        for s in _SENDERS:
            if re.search(rf"(?<![\w\"'.]){s}\s*\(|email_service\.{s}\b|import[^\n]*\b{s}\b", src):
                callers[s].add(path.name)
    assert all(callers.values()), f"регулярка ничего не нашла: {callers}"
    assert {c for cs in callers.values() for c in cs} == {"lifecycle_emails.py"}, callers


def test_onboarding_endpoint_is_gone():
    from backend.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/internal/weekly-digest" in paths  # роутер подключён — проверка не пустая
    assert "/api/v1/internal/onboarding-emails" not in paths


# ── Нет отложенных запусков дольше часа ─────────────────────

MAX_DELAY_SEC = 3600  # умолчание visibility timeout Redis-брокера


def _long_delays(src: str) -> list[str]:
    """countdown=<выражение> дольше часа и любой eta= — отложенный запуск,
    который Redis-брокер выдаст повторно."""
    bad = []
    for expr in re.findall(r"countdown\s*=\s*([^,)\n]+)", src):
        try:
            value = eval(expr, {"__builtins__": {}})  # только литералы и *,+
        except Exception:
            bad.append(f"countdown={expr.strip()} (не литерал — не проверить)")
            continue
        if value >= MAX_DELAY_SEC:
            bad.append(f"countdown={expr.strip()}")
    bad += [f"eta={m}" for m in re.findall(r"\beta\s*=\s*([^,)\n]+)", src)]
    return bad


def test_scanner_catches_the_23_09_bug():
    """Против пустой проверки: на коде, который был до правки, сканер обязан сработать."""
    old = "send_retention_day14_task.apply_async(args=[user_id], countdown=14 * 24 * 3600)"
    assert _long_delays(old) == ["countdown=14 * 24 * 3600"]
    assert _long_delays("x.apply_async(args=[1], countdown=60)") == []
    assert _long_delays("x.apply_async(eta=when)") == ["eta=when"]


def test_no_long_countdown_in_backend():
    bad = {}
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts:
            continue
        found = _long_delays(path.read_text(encoding="utf-8"))
        if found:
            bad[str(path.relative_to(BACKEND))] = found
    assert bad == {}, bad


# ── Миграция 054: заполнение журнала по датам ───────────────

def _run_054(db):
    """upgrade() на уже созданных таблицах (create_all): DDL пропускается по
    guard'ам, выполняется ровно заполнение. CI гоняет миграцию только на
    пустой базе — эта логика иначе не проверялась бы нигде."""
    import importlib.util

    path = BACKEND.parent / "alembic" / "versions" / "054_email_sent_log.py"
    spec = importlib.util.spec_from_file_location("m054", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    conn = db.connection()
    mod.op = SimpleNamespace(get_bind=lambda: conn)
    mod.upgrade()
    db.commit()


def test_migration_backfills_due_letters_only(db):
    fresh, mid, old = _user(db, 1), _user(db, 8), _user(db, 40)
    _run_054(db)
    assert _kinds(db, fresh) == []
    assert _kinds(db, mid) == ["retention_day2", "retention_day7"]
    assert _kinds(db, old) == ["retention_day14", "retention_day2", "retention_day7"]
    assert {s for (s,) in db.query(EmailSentLog.sent_at)} == {None}


def test_migration_starts_chain_only_first_successful_payment(db):
    u = _user(db, 100, tier="lite")
    refund = PaymentEvent(provider="yookassa", inv_id="refund:r1", user_id=u.id, tier="lite",
                          period="monthly", amount=-790.0, created_at=utcnow() - timedelta(days=60))
    unusable = PaymentEvent(provider="yookassa", inv_id="bad-1", user_id=u.id, tier="lite",
                            period=None, amount=790.0, created_at=utcnow() - timedelta(days=59))
    db.add_all([refund, unusable])
    db.commit()
    first = _purchase(db, u, "lite", days_ago=50, starts_chain=False)
    renewal = _purchase(db, u, "lite", days_ago=20, starts_chain=False)
    upgrade = _purchase(db, u, "pro", days_ago=10, starts_chain=False)
    _run_054(db)
    for pe in (refund, unusable, first, renewal, upgrade):
        db.refresh(pe)
    assert (refund.starts_chain, unusable.starts_chain) == (False, False)
    assert (first.starts_chain, renewal.starts_chain, upgrade.starts_chain) == (True, False, True)

    logged = {(k, r) for k, r in db.query(EmailSentLog.kind, EmailSentLog.ref)
              .filter(EmailSentLog.ref != "")}
    # lite: 50 дней — и приветствие, и day14 уже «пора»; pro: 10 дней — только
    # приветствие, pro_day30 ещё впереди и придёт через Beat.
    assert logged == {("lite_welcome", str(first.id)), ("lite_day14", str(first.id)),
                      ("pro_welcome", str(upgrade.id))}


# ── Таймаут Resend ──────────────────────────────────────────

def test_hanging_resend_is_cut_off(monkeypatch):
    """Отправка идёт внутри транзакции со строкой журнала: зависший запрос не
    должен держать блокировку дольше общего потолка."""
    import httpx

    from backend import email_service

    async def hang(self, *a, **k):
        await asyncio.sleep(30)

    monkeypatch.setattr(email_service, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email_service, "RESEND_TOTAL_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(httpx.AsyncClient, "post", hang)
    assert asyncio.run(email_service._send("a@example.com", "s", "h")) is False
