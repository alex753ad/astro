"""ЮKassa: чекаут, вебхук, истечение подписки.

Провайдер-независимая часть (идемпотентность в БД, комиссия, активация) уже
покрыта test_payment_idempotency.py и бьёт по process_payment напрямую. Здесь —
то, что появилось вместе с роутером ЮKassa и в тех тестах отсутствует:

  • отказ для Орина (premium) в чекауте — цена в TIER_PRICES_RUB есть, но
    продавать тариф нельзя;
  • аутентификация вебхука по IP (ЮKassa уведомления не подписывает);
  • идемпотентность на уровне HTTP: повтор доставки должен получить 200, иначе
    ЮKassa ретраит до истечения суток, и подписка активируется дважды;
  • paid_until = сейчас + 30 дней независимо от остатка;
  • падение до free по истечении срока и поведение слотов (карты остаются, но
    новый слот не выдаётся).

Сеть замокана целиком: настоящий API ЮKassa в тестах не дёргается.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.auth.rate_limits import TIER_FLAGS
from backend.models import NatalChart, PaymentEvent, Subscription, User
from backend.payments import yookassa_router as yk
from backend.payments.common import TIER_PRICES_RUB
from backend.time_utils import utcnow

# Адрес из 185.71.76.0/27 — см. YOOKASSA_NETWORKS.
YOOKASSA_IP = "185.71.76.1"
FOREIGN_IP = "203.0.113.7"

WEBHOOK_URL = "/api/v1/payments/yookassa/notification"
CHECKOUT_URL = "/api/v1/payments/checkout"


# ── Вспомогательное ────────────────────────────────────────

@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """Роутер читает настройки через модульный settings — задаём боевые
    значения, чтобы checkout не отвечал 503."""
    monkeypatch.setattr(yk.settings, "yookassa_shop_id", "1442186", raising=False)
    monkeypatch.setattr(yk.settings, "yookassa_secret_key", "live_test_stub", raising=False)


@pytest.fixture
def from_yookassa(monkeypatch):
    """Заставить проверку IP видеть адрес ЮKassa.

    client_ip() за TestClient вернёт testclient/127.0.0.1 — подменяем его в
    самом роутере, а не подделываем X-Forwarded-For: заголовку роутер и не
    должен верить без TRUSTED_PROXY_IPS.
    """
    monkeypatch.setattr(yk, "client_ip", lambda request: YOOKASSA_IP)


def _payment_body(payment_id="2f0c8a1e-000f-5000-8000-1d0e0c0b0a09", event="payment.succeeded"):
    return {"type": "notification", "event": event, "object": {"id": payment_id}}


def _api_payment(user_id, tier="pro", amount=None, status="succeeded"):
    """Ответ GET /v3/payments/{id} — то, что роутер перечитывает из API."""
    value = TIER_PRICES_RUB[tier] if amount is None else amount
    return {
        "id": "2f0c8a1e-000f-5000-8000-1d0e0c0b0a09",
        "status": status,
        "amount": {"value": f"{value:.2f}", "currency": "RUB"},
        "metadata": {"user_id": str(user_id), "tier": tier, "period": "monthly"},
    }


@pytest.fixture
def api_returns(monkeypatch):
    """Подменяет перечитывание платежа из API ЮKassa."""
    def _set(payment: dict | None):
        async def _fake(payment_id):
            return payment
        monkeypatch.setattr(yk, "_fetch_payment", _fake)
    return _set


# ── Чекаут ─────────────────────────────────────────────────

class TestCheckoutTiers:

    def test_premium_rejected_even_though_price_exists(self, client, auth_headers_free):
        """Орион отключён в интерфейсе, но цена 7990 в TIER_PRICES_RUB есть
        (нужна админке для MRR). Если бы чекаут просто брал цену из словаря,
        отключённый тариф продавался бы запросом мимо интерфейса."""
        assert "premium" in TIER_PRICES_RUB, "тест потерял смысл: цены premium больше нет"

        resp = client.post(
            CHECKOUT_URL,
            json={"tier": "premium", "billing_period": "monthly"},
            headers=auth_headers_free,
        )
        assert resp.status_code == 400, resp.text
        assert "Орион" in resp.json()["detail"]

    @pytest.mark.parametrize("tier", ["free", "orion", "PRO_MAX", ""])
    def test_unknown_tier_rejected(self, client, auth_headers_free, tier):
        resp = client.post(
            CHECKOUT_URL,
            json={"tier": tier, "billing_period": "monthly"},
            headers=auth_headers_free,
        )
        assert resp.status_code == 400, resp.text

    @pytest.mark.parametrize("tier", ["lite", "pro"])
    def test_lite_and_pro_create_payment(self, client, auth_headers_free, monkeypatch, tier):
        """Сумма платежа берётся из TIER_PRICES_RUB, а не из тела запроса."""
        captured = {}

        class _Resp:
            def raise_for_status(self): pass
            def json(self):
                return {
                    "id": "pay-1",
                    "confirmation": {"confirmation_url": "https://yoomoney.ru/checkout/pay-1"},
                }

        class _Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, json=None, auth=None, headers=None):
                captured["url"] = url
                captured["json"] = json
                captured["headers"] = headers
                return _Resp()

        monkeypatch.setattr(yk.httpx, "AsyncClient", _Client)

        resp = client.post(
            CHECKOUT_URL,
            json={"tier": tier, "billing_period": "monthly", "amount": 1},
            headers=auth_headers_free,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["checkout_url"] == "https://yoomoney.ru/checkout/pay-1"
        assert captured["json"]["amount"]["value"] == f"{TIER_PRICES_RUB[tier]:.2f}"
        assert captured["json"]["metadata"]["tier"] == tier
        assert "Idempotence-Key" in captured["headers"]
        # 54-ФЗ: блок чека пока не формируем — ждём ответ поддержки ЮKassa.
        assert "receipt" not in captured["json"]

    def test_unconfigured_returns_503(self, client, auth_headers_free, monkeypatch):
        monkeypatch.setattr(yk.settings, "yookassa_shop_id", "", raising=False)
        monkeypatch.setattr(yk.settings, "yookassa_secret_key", "", raising=False)
        resp = client.post(
            CHECKOUT_URL, json={"tier": "pro", "billing_period": "monthly"},
            headers=auth_headers_free,
        )
        assert resp.status_code == 503, resp.text

    def test_requires_auth(self, client):
        resp = client.post(CHECKOUT_URL, json={"tier": "pro", "billing_period": "monthly"})
        assert resp.status_code in (401, 403), resp.text


# ── Аутентификация вебхука ─────────────────────────────────

class TestWebhookIPCheck:
    """ЮKassa вебхуки не подписывает — IP-проверка это вся аутентификация."""

    def test_foreign_ip_rejected(self, client, db, user_free, monkeypatch, api_returns):
        monkeypatch.setattr(yk, "client_ip", lambda request: FOREIGN_IP)
        api_returns(_api_payment(user_free.id))

        resp = client.post(WEBHOOK_URL, json=_payment_body())

        assert resp.status_code == 403, resp.text
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"

    @pytest.mark.parametrize("ip", ["185.71.76.1", "185.71.77.30", "77.75.153.100",
                                    "77.75.156.11", "77.75.154.200", "2a02:5180::1"])
    def test_documented_subnets_accepted(self, ip):
        assert yk._is_yookassa_ip(ip), f"{ip} должен входить в подсети ЮKassa"

    @pytest.mark.parametrize("ip", ["185.71.76.32", "77.75.156.12", "77.75.154.1",
                                    "127.0.0.1", "not-an-ip", ""])
    def test_outside_addresses_rejected(self, ip):
        assert not yk._is_yookassa_ip(ip)

    def test_reject_notifies_owner_once_per_window(self, client, monkeypatch):
        """Отказ по IP виден только в логе контейнера, а логи не переживают
        деплой: если фильтр сломается (устареет список подсетей, изменится
        docker-сеть), платежи молча перестанут активироваться. Владельцу
        должно прийти сообщение — но ЮKassa ретраит доставку, поэтому ровно
        одно за окно, иначе чат завалит и его перестанут читать."""
        class _FakeRedis:
            """Ровно те операции, что использует _notify_ip_reject."""
            def __init__(self):
                self.store: dict[str, str] = {}

            async def incr(self, key):
                self.store[key] = str(int(self.store.get(key, 0)) + 1)
                return int(self.store[key])

            async def expire(self, key, ttl):
                return True

            async def set(self, key, value, ex=None, nx=False):
                if nx and key in self.store:
                    return None  # окно уже занято
                self.store[key] = value
                return True

            async def delete(self, key):
                self.store.pop(key, None)
                return 1

        sent: list[str] = []

        async def _fake_send(text, photo_path=None):
            sent.append(text)
            return True

        fake_redis = _FakeRedis()
        monkeypatch.setattr(yk, "get_redis", lambda: fake_redis)
        monkeypatch.setattr("backend.notifications.telegram.send_support_message", _fake_send)
        monkeypatch.setattr(yk, "client_ip", lambda request: FOREIGN_IP)

        first = client.post(WEBHOOK_URL, json=_payment_body())

        assert first.status_code == 403, "уведомление не должно менять ответ вебхука"
        assert len(sent) == 1, "первый отказ обязан уведомить владельца"
        assert FOREIGN_IP in sent[0], "в сообщении должен быть адрес отправителя"
        assert yk.YOOKASSA_IP_LIST_CHECKED in sent[0], "нужна дата сверки списка подсетей"
        # Тело запроса не пересылаем: там платёжные данные, а чат служебный.
        assert "2f0c8a1e" not in sent[0], "тело вебхука не должно попадать в чат"

        for _ in range(4):
            repeat = client.post(WEBHOOK_URL, json=_payment_body())
            assert repeat.status_code == 403

        assert len(sent) == 1, "ретраи в пределах часа не должны слать второе сообщение"


# ── payment.succeeded ──────────────────────────────────────

class TestPaymentSucceeded:

    def test_activates_subscription(self, client, db, user_free, from_yookassa, api_returns):
        api_returns(_api_payment(user_free.id, tier="pro"))

        resp = client.post(WEBHOOK_URL, json=_payment_body())

        assert resp.status_code == 200, resp.text
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "pro"
        assert db.query(PaymentEvent).filter(PaymentEvent.provider == "yookassa").count() == 1

    def test_replay_returns_200_and_does_not_activate_twice(
        self, client, db, user_free, from_yookassa, api_returns
    ):
        """ЮKassa повторяет доставку, пока не получит 200. Дубль обязан
        отвечать 200 (иначе ретраи не кончатся) и при этом ничего не менять."""
        api_returns(_api_payment(user_free.id, tier="pro"))
        client.post(WEBHOOK_URL, json=_payment_body())

        db.expire_all()
        first_end = db.query(Subscription).filter(
            Subscription.user_id == user_free.id
        ).first().current_period_end

        for _ in range(3):
            resp = client.post(WEBHOOK_URL, json=_payment_body())
            assert resp.status_code == 200, resp.text

        db.expire_all()
        subs = db.query(Subscription).filter(Subscription.user_id == user_free.id).all()
        assert len(subs) == 1, "повтор создал вторую подписку"
        assert subs[0].current_period_end == first_end, "повтор продлил подписку"
        assert db.query(PaymentEvent).filter(PaymentEvent.inv_id.notlike("refund:%")).count() == 1

    def test_amount_mismatch_does_not_activate(self, client, db, user_free, from_yookassa, api_returns):
        """Заплатили 1 ₽ за Pro — подписки быть не должно."""
        api_returns(_api_payment(user_free.id, tier="pro", amount=1.0))

        resp = client.post(WEBHOOK_URL, json=_payment_body())

        assert resp.status_code == 400, resp.text
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"

    def test_foreign_currency_does_not_activate(self, client, db, user_free, from_yookassa, api_returns):
        """Аудит 23.08.2026, находка 2.3: сверялся только amount.value, и «2490»
        в любой валюте проходило как 2490 ₽ — TIER_PRICES_RUB рублёвые."""
        payment = _api_payment(user_free.id, tier="pro")
        assert payment["amount"]["value"] == "2490.00", "тест потерял смысл: сумма не совпадает с ценой Лиры"
        payment["amount"]["currency"] = "KZT"
        api_returns(payment)

        resp = client.post(WEBHOOK_URL, json=_payment_body())

        assert resp.status_code == 400, resp.text
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"
        assert db.query(PaymentEvent).filter(PaymentEvent.inv_id.notlike("refund:%")).count() == 0, \
            "платёж в чужой валюте не должен оставлять запись об оплате"

    def test_missing_user_keeps_payment_record_and_does_not_retry(
        self, client, db, from_yookassa, api_returns, monkeypatch
    ):
        """Аудит 23.08.2026, находка 2.1: платёж за удалённый аккаунт.

        Раньше activate_subscription писала warning и делала return, это
        считалось успехом — вебхук отвечал 200, ЮKassa прекращала доставку, а
        коммита не было и PaymentEvent откатывался. Деньги списаны, следов нет.

        Теперь: 200 (ретрай не поможет, причина постоянная), запись о платеже
        сохранена, владелец уведомлён.

        ВНИМАНИЕ про проверку «запись уцелела». Наличие строки в БД тут
        показательным НЕ является: conftest отдаёт роутеру ту же сессию, что и
        фикстуре db, и не закрывает её, а в проде запись терялась именно на
        db.close() в get_db — сфлашенное без commit откатывалось. То есть
        `event is not None` проходило бы и на сломанном коде. Поэтому ниже
        считается число commit'ов: ровно оно и было нулём, когда
        activate_subscription молча возвращалась.
        """
        sent: list[str] = []

        async def _fake_send(text, photo_path=None):
            sent.append(text)
            return True

        monkeypatch.setattr("backend.notifications.telegram.send_support_message", _fake_send)

        commits = {"n": 0}
        real_commit = db.commit

        def _counting_commit():
            commits["n"] += 1
            return real_commit()

        monkeypatch.setattr(db, "commit", _counting_commit)

        ghost_id = "00000000-0000-4000-8000-00000000dead"
        assert db.query(User).filter(User.id == ghost_id).first() is None, "фикстура: такого юзера быть не должно"
        api_returns(_api_payment(ghost_id, tier="pro"))

        resp = client.post(WEBHOOK_URL, json=_payment_body())

        assert resp.status_code == 200, "500 заставил бы ЮKassa ретраить сутки без шанса на успех"

        db.expire_all()
        event = db.query(PaymentEvent).filter(
            PaymentEvent.inv_id == "2f0c8a1e-000f-5000-8000-1d0e0c0b0a09"
        ).first()
        assert event is not None, "запись о платеже потеряна — деньги пришли в никуда без следа"
        assert event.amount == float(TIER_PRICES_RUB["pro"])
        assert event.user_id == ghost_id
        assert commits["n"] >= 1, (
            "commit не вызван: в проде сфлашенный PaymentEvent откатится на "
            "db.close(), и платёж исчезнет без следа"
        )

        assert len(sent) == 1, "владелец должен узнать о платеже без владельца"
        assert "НЕКОМУ" in sent[0]
        assert "Мой налог" in sent[0], "доход провести надо в любом случае — это должно быть в сообщении"

    def test_premium_metadata_rejected(self, client, db, user_free, from_yookassa, api_returns):
        """Даже если платёж на 7990 каким-то образом создан — Орион не выдаём."""
        api_returns(_api_payment(user_free.id, tier="premium"))

        resp = client.post(WEBHOOK_URL, json=_payment_body())

        assert resp.status_code == 400, resp.text
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"

    def test_api_unavailable_returns_500_for_retry(self, client, db, user_free, from_yookassa, api_returns):
        """Не смогли перечитать платёж — активировать по неподписанному телу
        нельзя, нужен ретрай, значит 5xx, а не 200."""
        api_returns(None)

        resp = client.post(WEBHOOK_URL, json=_payment_body())

        assert resp.status_code == 500, resp.text
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"

    def test_status_disagrees_with_api(self, client, db, user_free, from_yookassa, api_returns):
        """Тело говорит succeeded, API — pending. Ретрай не поможет: 200."""
        api_returns(_api_payment(user_free.id, status="pending"))

        resp = client.post(WEBHOOK_URL, json=_payment_body())

        assert resp.status_code == 200, resp.text
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"


# ── paid_until ─────────────────────────────────────────────

class TestPaidUntil:

    def test_thirty_days_from_payment(self, client, db, user_free, from_yookassa, api_returns):
        api_returns(_api_payment(user_free.id, tier="pro"))
        before = utcnow()

        client.post(WEBHOOK_URL, json=_payment_body())

        db.expire_all()
        sub = db.query(Subscription).filter(Subscription.user_id == user_free.id).first()
        delta = sub.current_period_end - (before + timedelta(days=30))
        assert abs(delta.total_seconds()) < 60, sub.current_period_end

    def test_upgrade_does_not_carry_over_remainder(
        self, client, db, user_free, from_yookassa, api_returns
    ):
        """Апгрейд Lite → Pro при 20 днях остатка: отсчёт с даты нового
        платежа, остаток не переносится (не 50 дней)."""
        db.add(Subscription(
            user_id=user_free.id,
            stripe_price_id="lite_monthly",
            status="active",
            tier="lite",
            current_period_end=utcnow() + timedelta(days=20),
        ))
        user_free.tier = "lite"
        db.commit()

        api_returns(_api_payment(user_free.id, tier="pro"))
        before = utcnow()
        client.post(WEBHOOK_URL, json=_payment_body())

        db.expire_all()
        sub = db.query(Subscription).filter(Subscription.user_id == user_free.id).first()
        assert sub.tier == "pro"
        delta = sub.current_period_end - (before + timedelta(days=30))
        assert abs(delta.total_seconds()) < 60, "остаток старого тарифа перенёсся"


# ── refund.succeeded ───────────────────────────────────────

class TestRefund:
    """Возврат фиксируем и уведомляем владельца, но доступ НЕ отзываем:
    возврат часто частичный или по договорённости, решение за владельцем."""

    @pytest.fixture(autouse=True)
    def telegram_sent(self, monkeypatch):
        """Перехватывает уведомления владельцу: возврат должен приходить в чат
        ровно один раз, сколько бы раз ЮKassa ни повторила доставку."""
        sent: list[str] = []

        async def _fake(text, photo_path=None):
            sent.append(text)
            return True

        monkeypatch.setattr("backend.notifications.telegram.send_support_message", _fake)
        return sent

    def _refund_body(self, refund_id="ref-1", payment_id="pay-1", amount=2490.0):
        return {
            "type": "notification",
            "event": "refund.succeeded",
            "object": {
                "id": refund_id,
                "payment_id": payment_id,
                "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            },
        }

    def test_records_event_but_keeps_subscription(
        self, client, db, user_pro, from_yookassa, telegram_sent
    ):
        db.add(PaymentEvent(provider="yookassa", inv_id="pay-1", user_id=user_pro.id,
                            tier="pro", period="monthly", amount=2490.0))
        db.commit()

        resp = client.post(WEBHOOK_URL, json=self._refund_body())

        assert resp.status_code == 200, resp.text
        db.expire_all()
        assert db.query(User).filter(User.id == user_pro.id).first().tier == "pro", \
            "возврат не должен отзывать доступ автоматически"
        refund = db.query(PaymentEvent).filter(PaymentEvent.inv_id == "refund:ref-1").first()
        assert refund is not None
        assert refund.amount == -2490.0
        assert refund.user_id == user_pro.id
        assert len(telegram_sent) == 1

    def test_replay_creates_no_duplicate_event_and_no_second_message(
        self, client, db, user_pro, from_yookassa, telegram_sent
    ):
        """ЮKassa ретраит refund.succeeded так же, как остальные события.
        Дедупликация держится на уникальном индексе inv_id (не на SELECT перед
        вставкой — тот два параллельных ретрая прошли бы оба), а уведомление
        уходит только после успешного commit."""
        for _ in range(3):
            resp = client.post(WEBHOOK_URL, json=self._refund_body())
            assert resp.status_code == 200, resp.text

        db.expire_all()
        assert db.query(PaymentEvent).filter(PaymentEvent.inv_id == "refund:ref-1").count() == 1
        assert len(telegram_sent) == 1, "повторная доставка отправила второе сообщение"

    def test_unique_index_is_what_dedupes(self, db):
        """Страховка от «оптимизации»: если уникальность inv_id когда-нибудь
        снимут, идемпотентность возвратов исчезнет молча."""
        assert PaymentEvent.__table__.c.inv_id.unique is True


# ── Прочие события ─────────────────────────────────────────

class TestOtherEvents:

    def test_canceled_is_noop_200(self, client, db, user_free, from_yookassa):
        resp = client.post(WEBHOOK_URL, json=_payment_body(event="payment.canceled"))
        assert resp.status_code == 200, resp.text
        db.expire_all()
        assert db.query(User).filter(User.id == user_free.id).first().tier == "free"

    def test_unknown_event_is_200(self, client, from_yookassa):
        """Неизвестное событие — 200, иначе ЮKassa будет ретраить его сутки."""
        resp = client.post(WEBHOOK_URL, json=_payment_body(event="payout.succeeded"))
        assert resp.status_code == 200, resp.text


# ── Истечение подписки ─────────────────────────────────────

class TestExpireSubscriptions:
    """Оплата разовая, автопродления нет. До появления tasks.expire_subscriptions
    джоба, понижающего tier по истечении срока, не существовало вовсе — один
    платёж давал платный тариф навсегда."""

    def _expire(self, db, monkeypatch):
        """Задача открывает свою сессию через SessionLocal — в тестах
        подменяем её на сессию фикстуры, иначе она смотрит в другую БД."""
        import backend.tasks as tasks

        class _Session:
            def __init__(self): pass
            def __getattr__(self, item): return getattr(db, item)
            def close(self): pass

        monkeypatch.setattr(tasks, "SessionLocal", _Session)
        return tasks.expire_subscriptions()

    def test_expired_falls_to_free(self, db, user_pro, monkeypatch):
        db.add(Subscription(
            user_id=user_pro.id, stripe_price_id="pro_monthly", status="active",
            tier="pro", current_period_end=utcnow() - timedelta(days=1),
        ))
        db.commit()

        result = self._expire(db, monkeypatch)

        assert result["expired"] == 1
        db.expire_all()
        assert db.query(User).filter(User.id == user_pro.id).first().tier == "free"
        assert db.query(Subscription).filter(
            Subscription.user_id == user_pro.id
        ).first().status == "expired"

    def test_active_subscription_untouched(self, db, user_pro, monkeypatch):
        db.add(Subscription(
            user_id=user_pro.id, stripe_price_id="pro_monthly", status="active",
            tier="pro", current_period_end=utcnow() + timedelta(days=5),
        ))
        db.commit()

        assert self._expire(db, monkeypatch)["expired"] == 0
        db.expire_all()
        assert db.query(User).filter(User.id == user_pro.id).first().tier == "pro"

    def test_pilot_user_without_subscription_untouched(self, db, user_pro, monkeypatch):
        """У пилотных участников записи в subscriptions нет — их даунгрейдом
        занимается backend/pilot/cron.py, эта задача их не трогает."""
        assert self._expire(db, monkeypatch)["expired"] == 0
        db.expire_all()
        assert db.query(User).filter(User.id == user_pro.id).first().tier == "pro"


# ── Слоты карт после падения до free ───────────────────────

class TestSlotsAfterDowngrade:
    """Требование: карты сверх лимита free не удаляются и остаются доступны,
    но новый слот не выдаётся, пока карт не станет меньше лимита free.
    Проверка в POST /chart/calculate слотовая (total_charts >= profiles_limit),
    поэтому отдельного кода под этот случай не требуется — тест фиксирует, что
    так оно и есть."""

    FREE_LIMIT = TIER_FLAGS["free"]["profiles_limit"]

    def _make_charts(self, db, user, count):
        past = utcnow() - timedelta(days=40)  # мимо CHART_CREATION_ABUSE_LIMIT
        ids = []
        for _ in range(count):
            chart = NatalChart(
                user_id=user.id, birth_date="1990-01-10", birth_time="12:00",
                birth_place="Moscow",
                latitude=55.75, longitude=37.62, timezone="Europe/Moscow",
                planets=[], houses=[], aspects=[], created_at=past,
            )
            db.add(chart)
            db.flush()
            ids.append(chart.id)
        db.commit()
        return ids

    def _try_create(self, client, headers):
        return client.post(
            "/api/v1/chart/calculate",
            json={
                "birth_date": "1990-01-10", "birth_time": "12:00",
                "birth_place": "Moscow", "house_system": "placidus",
            },
            headers=headers,
        )

    def test_charts_survive_downgrade_but_no_new_slot(
        self, client, db, user_pro, auth_headers_pro, mock_calculator, mock_geo, monkeypatch
    ):
        chart_ids = self._make_charts(db, user_pro, 15)
        db.add(Subscription(
            user_id=user_pro.id, stripe_price_id="pro_monthly", status="active",
            tier="pro", current_period_end=utcnow() - timedelta(days=1),
        ))
        db.commit()

        TestExpireSubscriptions()._expire(db, monkeypatch)
        db.expire_all()
        assert db.query(User).filter(User.id == user_pro.id).first().tier == "free"

        # 1. Карты не удалены.
        assert db.query(NatalChart).filter(NatalChart.user_id == user_pro.id).count() == 15

        # 2. Каждая по-прежнему доступна на чтение.
        headers = self._auth(user_pro)
        for chart_id in chart_ids[:3]:
            resp = client.get(f"/api/v1/chart/{chart_id}", headers=headers)
            assert resp.status_code == 200, resp.text

        # 3. Новый слот не выдаётся.
        resp = self._try_create(client, headers)
        assert resp.status_code == 403, resp.text
        assert "/pricing" in resp.json()["detail"]

        # 4. Удаление одной карты слота не открывает: 14 всё ещё >= 2.
        db.query(NatalChart).filter(NatalChart.id == chart_ids[0]).delete()
        db.commit()
        assert self._try_create(client, headers).status_code == 403

        # 5. Слот появляется только когда карт стало меньше лимита free —
        #    оставляем ровно FREE_LIMIT - 1 штук.
        keep = chart_ids[1:self.FREE_LIMIT]
        db.query(NatalChart).filter(
            NatalChart.user_id == user_pro.id, NatalChart.id.notin_(keep),
        ).delete(synchronize_session=False)
        db.commit()
        assert db.query(NatalChart).filter(
            NatalChart.user_id == user_pro.id
        ).count() == self.FREE_LIMIT - 1
        assert self._try_create(client, headers).status_code == 200

    @staticmethod
    def _auth(user):
        """Токен выпускается заново: в auth_headers_pro зашит tier=pro, а после
        даунгрейда лимиты должны считаться по актуальному тарифу."""
        from backend.auth.jwt import create_access_token
        return {"Authorization": f"Bearer {create_access_token(user_id=user.id, email=user.email, tier='free')}"}
