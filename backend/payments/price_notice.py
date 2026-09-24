"""Уведомление о смене цен — оферта п. 10.1: за 14 дней, письмом и публикацией.

Механизм минимальный и запускается ТОЛЬКО вручную владельцем
(`POST /api/v1/admin/price-notice`, сначала с `dry_run: true`). Сам ничего не
планирует и цену не меняет — цена меняется строкой в
`common.PRICE_SCHEDULE` с датой вступления, и эта строка обязана уже быть на
проде: текст письма собирается из неё, поэтому письмо не может пообещать
одну цену, а чекаут брать другую.

* **Письмо** — всем с подтверждённым email, ВКЛЮЧАЯ отписавшихся от рассылок
  (решение владельца 24.09.2026): это уведомление об изменении условий
  договора, а не реклама. Через журнал `email_sent_log` (kind `price_notice`,
  ref — дата вступления): повторный запуск не шлёт второе письмо.
* **Публикация** — объявление (`announcements`), которое показывают баннером
  веб и приложение до даты вступления и неделю после.

⚠️ Дата вступления — не раньше чем через NOTICE_DAYS дней от запуска, иначе
отказ: уведомление позже срока оферта не засчитывает.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from backend.models import Announcement, User
from backend.payments.common import PRICE_SCHEDULE, _msk_date, prices_on

logger = logging.getLogger("astro.payments.price_notice")

NOTICE_DAYS = 14
KIND = "price_notice"
BANNER_AFTER_DAYS = 7
# Пауза между письмами: у Resend ограничение по частоте запросов.
SEND_PAUSE_SEC = 0.6

_MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
               "августа", "сентября", "октября", "ноября", "декабря"]


class NoticeError(ValueError):
    """Запуск невозможен — причина в тексте, для владельца."""


def _date_ru(d: date) -> str:
    return f"{d.day} {_MONTHS_GEN[d.month - 1]} {d.year}"


def build_notice(effective: date, today: date | None = None) -> dict:
    """Тема, текст и строки цен. NoticeError — если запускать нельзя."""
    from backend.email_service import TIER_NAMES
    from backend.payments.yookassa_router import CHECKOUT_TIERS

    today = today or _msk_date(None)
    if effective < today + timedelta(days=NOTICE_DAYS):
        raise NoticeError(
            f"дата вступления {effective} раньше, чем через {NOTICE_DAYS} дней "
            f"({today + timedelta(days=NOTICE_DAYS)}) — оферта п. 10.1"
        )
    new = dict(PRICE_SCHEDULE).get(effective)
    if new is None:
        raise NoticeError(
            f"в common.PRICE_SCHEDULE нет строки с датой {effective} — сначала "
            "выкати новую цену с датой вступления, потом уведомляй"
        )
    old = prices_on(datetime.combine(effective - timedelta(days=1), datetime.min.time()))
    changes = [
        (TIER_NAMES.get(t, t), old.get(t), new.get(t))
        for t in CHECKOUT_TIERS if old.get(t) != new.get(t)
    ]
    if not changes:
        raise NoticeError(f"цены на {effective} не отличаются от действующих — уведомлять не о чем")

    lines = [f"{name}: {o} ₽ → {n} ₽ в месяц" for name, o, n in changes]
    when = _date_ru(effective)
    text = (
        f"С {when} меняются цены на тарифы Aristea Timeline.\n\n"
        + "\n".join(lines)
        + "\n\nЕсли тариф уже оплачен, до конца оплаченного срока ничего не меняется. "
        f"Оплата до {when} проходит по нынешней цене.\n\n"
        "Условия — в оферте, п. 10.1: aristeatime.ru/terms"
    )
    return {
        "effective_date": effective.isoformat(),
        "subject": f"Цены на тарифы меняются с {when}",
        "title": f"С {when} меняются цены",
        "lines": lines,
        "text": text,
    }


def recipients(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.is_email_confirmed.is_(True), User.email.isnot(None))
        .all()
    )


def publish(db: Session, notice: dict) -> Announcement:
    """Баннер до даты вступления и неделю после. Повтор не плодит строк."""
    effective = date.fromisoformat(notice["effective_date"])
    ref = f"{KIND}:{notice['effective_date']}"
    row = db.query(Announcement).filter(Announcement.ref == ref).first()
    if row is None:
        row = Announcement(ref=ref)
        db.add(row)
    row.title = notice["title"]
    row.body = "\n".join(notice["lines"])
    row.link = "/pricing"
    row.ends_at = datetime.combine(effective + timedelta(days=BANNER_AFTER_DAYS), datetime.min.time())
    db.commit()
    return row


def send_all(db: Session, notice: dict) -> dict:
    """Разослать письмо всем адресатам через журнал. Синхронно — из Celery."""
    from backend.email_service import _base, _p, _send
    from backend.lifecycle_emails import send_once

    html = _base(
        notice["title"], notice["subject"],
        "".join(_p(part.replace("\n", "<br>")) for part in notice["text"].split("\n\n")),
    )
    sent = skipped = failed = 0
    for user in recipients(db):
        async def _one(to=user.email):
            return await _send(to, notice["subject"], html)
        ok = send_once(db, user.id, KIND, notice["effective_date"], _one)
        if ok:
            sent += 1
        else:
            # send_once возвращает False и на «уже в журнале», и на неудачу;
            # различаем по журналу — нужна честная цифра владельцу.
            from backend.models import EmailSentLog
            logged = db.query(EmailSentLog.id).filter(
                EmailSentLog.user_id == user.id, EmailSentLog.kind == KIND,
                EmailSentLog.ref == notice["effective_date"],
            ).first()
            if logged:
                skipped += 1
            else:
                failed += 1
        if SEND_PAUSE_SEC:
            import time
            time.sleep(SEND_PAUSE_SEC)
    logger.info("price_notice %s: sent=%d skipped=%d failed=%d",
                notice["effective_date"], sent, skipped, failed)
    return {"sent": sent, "skipped": skipped, "failed": failed}
