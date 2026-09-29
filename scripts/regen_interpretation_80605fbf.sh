#!/usr/bin/env bash
# regen_interpretation_80605fbf.sh — пересоздать разбор ОДНОЙ карты (80605fbf…)
# новым промптом: в старом тексте «видят тебя уверенной и тёплой» — угадан пол.
#
#   cd /opt/astro/app && git pull --ff-only && bash scripts/regen_interpretation_80605fbf.sh
#
# Решение владельца 28.09.2026: сохранённые разборы массово не переписываем,
# только эту карту. Запускать ПОСЛЕ деплоя, где INTERPRETATION_PROMPT_VERSION = 3
# (иначе модель получит прежний промпт).
#
# Что делает: находит карту по началу id (ровно одну — иначе выходит, ничего не
# меняя), генерирует разбор тем же путём, что сайт (тариф владельца карты), и
# ДОБАВЛЯЕТ новую строку в interpretations. Старая не удаляется: сайт и PDF
# берут самую свежую, а откат — удалить новую строку (её id в выводе).
# Квота разборов не списывается — это исправление, а не новый разбор.
# Тариф разбора записывается (interpretations.tier, миграция 067): PDF берёт
# разбор не короче тарифа человека — без тарифа строка ушла бы в вывод по
# числу слов. Поэтому запускать после деплоя с 067.
# Текст разбора в лог не пишется: только длина и найденные родовые обороты.

set -uo pipefail
cd /opt/astro || exit 1
mkdir -p diag
LOG="diag/regen_interpretation_80605fbf-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

docker compose exec -T api python - <<'PY'
import asyncio

from backend.cache import make_profile_hash
from backend.database import SessionLocal
from backend.interpretation.base import InterpretationRequest
from backend.interpretation.gender_check import gendered_you
from backend.interpretation.prompts import INTERPRETATION_PROMPT_VERSION
from backend.interpretation.router import get_router
from backend.models import Interpretation, NatalChart, User

PREFIX = "80605fbf"

if INTERPRETATION_PROMPT_VERSION < 3:
    raise SystemExit(f"версия промпта {INTERPRETATION_PROMPT_VERSION} — сначала деплой с версией 3")
if not hasattr(Interpretation, "tier"):
    raise SystemExit("в interpretations нет tier — сначала деплой с миграцией 067")

db = SessionLocal()
try:
    charts = db.query(NatalChart).filter(NatalChart.id.like(PREFIX + "%")).all()
    if len(charts) != 1:
        raise SystemExit(f"карт с id {PREFIX}…: {len(charts)} — нужна ровно одна, ничего не меняю")
    chart = charts[0]
    user = db.get(User, chart.user_id) if chart.user_id else None
    tier = (user.tier if user else None) or "free"
    old = (db.query(Interpretation).filter(Interpretation.chart_id == chart.id)
           .order_by(Interpretation.created_at.desc()).first())
    print(f"карта {chart.id}, тариф владельца {tier}")
    if old:
        print(f"прежний разбор: {old.id}, {old.created_at:%Y-%m-%d}, {len(old.content)} симв., "
              f"родовых оборотов {len(gendered_you(old.content))}")

    profile = {
        "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
        "ascendant": chart.ascendant, "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }
    result = asyncio.run(get_router().generate(InterpretationRequest(natal_profile=profile, tier=tier)))
    text = result.content or ""
    if not text or result.engine == "template":
        raise SystemExit(f"модель не ответила (движок {result.engine}) — ничего не меняю")

    row = Interpretation(chart_id=chart.id, profile_hash=make_profile_hash(profile),
                         engine=result.engine, content=text, sections=result.sections, tier=tier)
    db.add(row)
    db.commit()
    hits = gendered_you(text)
    print(f"новый разбор: {row.id}, тариф {row.tier}, движок {result.engine}, {len(text)} симв., "
          f"родовых оборотов {len(hits)}{': ' + '; '.join(hits) if hits else ''}")
    print(f"откат: delete from interpretations where id = '{row.id}';")
finally:
    db.close()
PY

echo "== конец. Лог: /opt/astro/$LOG"
