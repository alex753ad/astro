"""Сборка PDF-отчёта в фоне и хранение файла.

Порядок (решение владельца 29.09.2026):

* Старт (`start`) — в ручке: идущая сборка человека возвращается как есть
  (одна на человека одновременно, повторное нажатие не плодит задачи);
  готовый отчёт с тем же отпечатком (`sections.fingerprint`) отдаётся
  заново — без сборки и без списания лимита; иначе проверка лимита PDF и
  задача `tasks.build_pdf_report`.
* Сборка (`run`) — в Celery: разбор под тариф (новый — без квоты разборов),
  аспекты, транзиты, долгосрочные периоды, рендер, файл на диск, списание
  PDF, пуш «PDF готов».
* Сбой — status failed, человеку FAIL_TEXT, лимит не списан (commit_pdf —
  последним шагом), исключение уходит дальше: сигнал в канал шлёт общий
  обработчик падений Celery (celery_app._on_task_failure).
* Таймаут — soft 300 с / hard 330 с у задачи: срок стрима разбора Лиры —
  до 220 с (router._stream_deadline_seconds). Жёстко убитая задача строку не
  закроет — её гасит `_expire_stale` через STALE_AFTER: без этого «одна
  сборка на человека» заперла бы его навсегда.

Файлы — settings.pdf_dir, в docker-compose это том pdf_reports. В бэкап он
НЕ входит (07-backup-cron.sh снимает только pg_dump) — намеренно: отчёт
пересобирается из разбора и кеша.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date, timedelta
from pathlib import Path

from backend.time_utils import local_today, user_tz, utcnow

logger = logging.getLogger(__name__)

TTL_DAYS = 30
STALE_AFTER = timedelta(minutes=7)   # дольше hard-лимита задачи (330 с)
FAIL_TEXT = "Не получилось собрать PDF, попробуй ещё раз"
ACTIVE = ("queued", "running")


def pdf_dir() -> Path:
    from backend.config import get_settings
    return Path(get_settings().pdf_dir)


def today_for(user, chart) -> date:
    """«Сегодня» отчёта — местное (user_tz). До 04.10.2026 — всегда по Москве."""
    return local_today(user_tz(None, user, chart))


def _expire_stale(db, user_id: str) -> None:
    from backend.models import PdfReport
    cutoff = utcnow() - STALE_AFTER
    stale = (db.query(PdfReport)
             .filter(PdfReport.user_id == user_id, PdfReport.status.in_(ACTIVE), PdfReport.created_at < cutoff)
             .all())
    for r in stale:
        r.status, r.error = "failed", "таймаут"
    if stale:
        db.commit()


def start(db, user, chart, wheel_png: str | None):
    """→ (отчёт, новая_задача). Отказ по лимиту — HTTPException из check_pdf_limit."""
    from backend.auth.rate_limits import tier_limiter
    from backend.models import PdfReport
    from backend.pdf_reports import sections

    _expire_stale(db, user.id)
    active = (db.query(PdfReport)
              .filter(PdfReport.user_id == user.id, PdfReport.status.in_(ACTIVE))
              .order_by(PdfReport.created_at.desc()).first())
    if active:
        return active, False

    tier = user.tier or "free"
    interp = sections.pick_interpretation(db, chart.id, tier)
    fp = sections.fingerprint(interp.id if interp else None, tier, today_for(user, chart))
    if fp:
        same = (db.query(PdfReport)
                .filter(PdfReport.user_id == user.id, PdfReport.chart_id == chart.id,
                        PdfReport.status == "ready", PdfReport.fingerprint == fp,
                        PdfReport.expires_at > utcnow())
                .order_by(PdfReport.created_at.desc()).first())
        if same and same.file_path and os.path.exists(same.file_path):
            return same, False

    tier_limiter.check_pdf_limit(user, db)
    now = utcnow()
    report = PdfReport(user_id=user.id, chart_id=chart.id, tier=tier, status="queued",
                       progress=0, step="В очереди", created_at=now,
                       expires_at=now + timedelta(days=TTL_DAYS))
    db.add(report)
    db.commit()
    from backend.tasks import build_pdf_report
    build_pdf_report.delay(report.id, wheel_png)
    return report, True


def _step(db, report, progress: int, step: str) -> None:
    report.status, report.progress, report.step = "running", progress, step
    db.commit()


async def _build(db, report, wheel_png: str | None) -> None:
    from backend.auth.rate_limits import tier_limiter
    from backend.models import AstrologerProfile, NatalChart, User
    from backend.natal_pdf import generate_pdf_bytes
    from backend.pdf_reports import sections

    chart = db.get(NatalChart, report.chart_id)
    user = db.get(User, report.user_id)
    tier = report.tier
    plan = sections.plan_for(tier)
    today = today_for(user, chart)
    cost = 0.0

    # Тексты пишутся одновременно: разбор Лиры один идёт 1,5–2 минуты, и
    # аспекты с транзитами за ним в очереди растянули бы сборку ещё на минуту.
    # Сессия БД общая — это безопасно: запросы к ней синхронные, корутины
    # переключаются только на ожидании модели.
    interp = sections.pick_interpretation(db, chart.id, tier)
    jobs = {}
    if interp is None:
        jobs["interp"] = sections.new_interpretation(db, chart, tier)
    if plan.aspects:
        jobs["aspects"] = sections.aspect_section(db, chart, tier)
    if plan.transits:
        jobs["transits"] = sections.transit_section(db, chart, tier, today)
    done = [0]

    async def tick(coro):
        out = await coro
        done[0] += 1
        _step(db, report, 10 + 70 * done[0] // len(jobs), "Пишем тексты")
        return out

    _step(db, report, 10, "Пишем тексты")
    results = dict(zip(jobs, await asyncio.gather(*(tick(c) for c in jobs.values()))))
    if "interp" in results:
        interp, c = results["interp"]
        cost += c
    rep = sections.Report(tier=tier, interpretation=interp.content, transit_months=plan.transit_months)
    if "aspects" in results:
        rep.aspects, c = results["aspects"]
        cost += c
    if "transits" in results:
        rep.transits, c = results["transits"]
        cost += c
    if plan.longterm:
        _step(db, report, 85, "Долгосрочные периоды")
        rep.longterm = await asyncio.to_thread(sections.longterm_section, chart, today, user_tz(None, user, chart))

    _step(db, report, 90, "Собираем файл")
    astrologer = None
    if tier == "premium":
        prof = db.query(AstrologerProfile).filter(AstrologerProfile.user_id == user.id).first()
        astrologer = prof.display_name if prof and prof.display_name else None
    pdf = await asyncio.to_thread(generate_pdf_bytes, chart, interp.content, astrologer, wheel_png, rep)

    folder = pdf_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{report.id}.pdf"
    path.write_bytes(pdf)

    report.file_path = str(path)
    report.pages = len(re.findall(rb"/Type /Page[^s]", pdf))
    report.fingerprint = sections.fingerprint(interp.id, tier, today)
    report.cost_usd = round(cost, 4)
    report.status, report.progress, report.step = "ready", 100, None
    report.ready_at = utcnow()
    db.commit()

    # Списание — последним: всё, что упало выше, лимит не трогает.
    tier_limiter.commit_pdf(user, db)
    report.charged = True
    db.commit()
    logger.info("pdf_report %s ready: tier=%s pages=%s cost=$%.4f", report.id, tier, report.pages, cost)


def _notify_ready(db, report) -> None:
    """Пуш «PDF готов» — во все каналы человека. Нет каналов — список отчётов
    покажет отметку «Новый» при следующем заходе (seen_at пуст)."""
    try:
        from backend.push.sender import send_to_user
        send_to_user(db, report.user_id, {
            "title": "PDF готов",
            "body": "Отчёт по карте собран. Файл хранится 30 дней.",
            "url": f"/chart/{report.chart_id}?pdf={report.id}",
        })
    except Exception as e:  # пуш не должен ронять готовый отчёт
        logger.warning("pdf_report %s: пуш не отправлен: %s", report.id, e)


def run(report_id: str, wheel_png: str | None) -> None:
    from backend.database import SessionLocal
    from backend.models import PdfReport

    db = SessionLocal()
    try:
        report = db.get(PdfReport, report_id)
        if report is None or report.status not in ACTIVE:
            return
        try:
            asyncio.run(_build(db, report, wheel_png))
        except BaseException as e:
            db.rollback()
            report = db.get(PdfReport, report_id)
            if report is not None and report.status != "ready":
                report.status, report.step = "failed", None
                report.error = f"{type(e).__name__}: {e}"[:255]
                db.commit()
            raise
        _notify_ready(db, report)
    finally:
        db.close()


def purge_expired(db) -> int:
    """Удалить отчёты старше 30 дней: и файл, и строку."""
    from backend.models import PdfReport
    rows = db.query(PdfReport).filter(PdfReport.expires_at <= utcnow()).all()
    for r in rows:
        if r.file_path:
            try:
                os.remove(r.file_path)
            except FileNotFoundError:
                pass
        db.delete(r)
    db.commit()
    # Файлы без строки: карту удалили — строки ушли каскадом, файлы остались.
    folder, cutoff = pdf_dir(), (utcnow() - timedelta(days=TTL_DAYS + 1)).timestamp()
    if folder.is_dir():
        for f in folder.glob("*.pdf"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    return len(rows)
