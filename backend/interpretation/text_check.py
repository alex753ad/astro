"""Проверка текстов модели на голос продукта — только лог и счётчик (шаг 8).

Решение владельца 07.10.2026: на всех генерациях считать нарушения, текст не
менять и не отбраковывать; отбраковку включать отдельно, по замеру. Счётчики —
сразу на проде, без флага: людям они не видны. Род в разборе и транзите не
переписывать (переписывает только чат, `rag_router._fix_gender`).

Виды: «AI/ИИ», обращение на «вы», эзотерика (тот же словарь, что у тестов
статических текстов — `ESOTERIC`) и род на «ты» (`gender_check`, у него свой
счётчик `gendered_you` с 28.09.2026 — он сохранён). «ё» в текстах модели не
считается: без словаря «все/всё», «небо/нёбо» не различить (решение владельца
07.10.2026), обязательна она только в статических текстах — тест.

`report` не бросает никогда: проверка не должна ронять выдачу текста.
Считать только свежую генерацию: кэш-хит — тот же текст второй раз.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("astro.text_check")

# «маги…» — без «магазин» и «магистр»; «мисти» с начала слова — без
# «оптимистичный». «медитац», «духовн», «намерени» не запрещены намеренно
# (решение владельца 03.10.2026). Тесты статических текстов берут его отсюда.
ESOTERIC = (
    r"эзотери|чакр|карм|\bмаги(?:я|и|ю|ей|ческ)|Вселенн|\bгуру\b|мест\w* силы|нумеролог"
    r"|\bмисти|ритуал|аффирмац|\bгадан|\bтаро\b|\bастрал|\bоберег|\bзаговор(?:а|ы|ов)?\b|сакральн"
)
ESOTERIC_EXTRA = r"оккульт|целител|тонки\w* энерги|рейки|энергопрактик|энергетическ\w* практик"

_CHECKS = (
    ("ai", re.compile(r"\b(?:ai|ии)\b", re.I)),
    ("formal_you", re.compile(
        r"\b(?:вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашего|вашей|вашему|вашим|вашими|ваших|вашу)\b", re.I)),
    ("esoteric", re.compile(ESOTERIC + "|" + ESOTERIC_EXTRA, re.I)),
)


def check(text: str) -> dict[str, list[str]]:
    """Найденные нарушения по видам (пусто — чисто). Род — без счётчика."""
    from backend.interpretation.gender_check import gendered_you

    found = {kind: [m.group(0) for m in rx.finditer(text or "")] for kind, rx in _CHECKS}
    found["gendered"] = gendered_you(text)
    return {k: v for k, v in found.items() if v}


def report(text: str, contour: str) -> dict[str, int]:
    """Посчитать и записать: поле `text:<вид>:<раздел>` в счётчиках прогнозов
    (`forecast.stats`, часовые корзины). Род пишет и прежний `gendered_you`."""
    try:
        from backend.forecast import stats
        from backend.interpretation.gender_check import report as gender_report

        gender_report(text, contour)
        found = check(text)
        for kind, hits in found.items():
            stats.incr(f"text:{kind}:{contour}")
            logger.warning("text_check contour=%s kind=%s n=%d hits=%s", contour, kind, len(hits), hits[:5])
        return {k: len(v) for k, v in found.items()}
    except Exception as e:
        logger.warning("text_check: проверка не выполнена (%s): %s", contour, e)
        return {}
