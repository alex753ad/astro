"""Запасной текст — когда модель недоступна, бюджет исчерпан или ответ не
прошёл проверку. Собирается из тех же смыслов, что уходят в промпт, и обязан
проходить ту же проверку (закреплено тестом): «не 503» не должно значить
«текст с терминами».
"""
from __future__ import annotations

from backend.forecast.facts import DayFacts, LunationFacts
from backend.forecast.meanings import (
    HOUSE_FOCUS, MOON_SIGN_MOOD, NATAL_SPHERE, PHASE_RU, SIGN_ACTION, SIGN_MEANING, TONE_PHRASE,
)
from backend.forecast.validate import date_ru


def daily_fallback(f: DayFacts) -> list[str]:
    if f.houses:
        focus, actions = HOUSE_FOCUS[f.houses[0]]
        first = (
            f"В этот день в центре внимания — {focus}. "
            f"Хорошо подойдёт то, что с этим связано: {actions}. "
            "Не нужно охватывать всё сразу — выбери одно дело и доведи его до конца."
        )
    else:
        mood = MOON_SIGN_MOOD.get(f.moon_sign, "день ровный")
        first = (
            f"Настроение дня такое: {mood}. "
            "Прислушайся к этому и не спорь с собой — так силы уйдут туда, где они действительно нужны."
        )

    middle = []
    for a in f.aspects[:2]:
        sphere = NATAL_SPHERE.get(a["natal"])
        if sphere:
            middle.append(TONE_PHRASE[a["tone"]].format(sphere=sphere))
    second = " ".join(middle) if middle else (
        "Острых моментов не видно: день ровный, и это хорошая возможность "
        "заняться тем, на что обычно не хватает спокойствия."
    )
    third = (
        "К вечеру оставь немного времени для себя: прогулка, простая еда, ранний сон. "
        "Если что-то не успелось — это не страшно, впереди будет новый шанс."
    )
    return [first, second, third]


def lunation_fallback(f: LunationFacts) -> dict:
    phase = PHASE_RU[f.phase]
    is_new = f.phase == "new_moon"
    tense = [a for a in f.aspects if a["tone"] == "tense"]
    ease = "легко" if not tense else "с усилием, но уверенно"
    headline = (
        f"Сегодня {phase}, а значит {'начинается новый цикл' if is_new else 'подходит к итогу то, что зрело последние недели'} — "
        f"и идёт он {ease}."
    )
    sign_meaning = f"Знак этой фазы — {f.sign}, а значит в центре внимания {SIGN_MEANING.get(f.sign, 'твои личные дела')}."
    if is_new:
        actions = [
            "Запиши одно главное желание на этот месяц — коротко и конкретно.",
            "Выбери одну область для перемен и не пытайся менять всё сразу.",
            "Составь простой план на ближайшие недели.",
            "Начни то, что давно откладывалось, хотя бы с первого маленького шага.",
            SIGN_ACTION.get(f.sign, "Сделай сегодня что-то приятное для себя."),
        ]
    else:
        actions = [
            "Подведи итог последних недель: что получилось, что нет.",
            "Заверши одно дело, которое давно висит.",
            "Отпусти то, что больше не работает, — привычку, обиду, лишнее обязательство.",
            "Поблагодари тех, кто помог тебе в этом месяце.",
            SIGN_ACTION.get(f.sign, "Сделай сегодня что-то приятное для себя."),
        ]
    if f.house:
        focus, _ = HOUSE_FOCUS[f.house]
        actions.append(f"Удели особое внимание теме «{focus}» — сейчас она откликается сильнее всего.")

    warning = None
    if tense or f.warnings:
        when = f" Особенно {date_ru(f.warnings[0]['date'])}." if f.warnings else ""
        warning = {
            "text": "Возможны напряжение и спешка: легко сорваться или решить сгоряча." + when,
            "tips": [
                "Важные договорённости фиксируй письменно.",
                "Не принимай серьёзных решений на эмоциях — дай себе ночь.",
                "Дели большие задачи на маленькие шаги.",
            ],
        }
    closing = (
        "То, что посажено сейчас, прорастёт не сразу — просто продолжай поливать."
        if is_new else
        "Полная Луна освещает всё до конца — пусть этот свет покажет, что стоит сохранить."
    )
    return {
        "headline": headline, "sign_meaning": sign_meaning, "actions": actions,
        "warning": warning, "closing": closing,
    }
