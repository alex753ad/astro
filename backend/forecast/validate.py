"""Проверка текста прогноза: без терминов, на «ты», без выдуманных дат.

⚠️ Всё — по ЦЕЛЫМ словам и конкретным оборотам, не по подстрокам (поправка
владельца 23.09.2026). Слова, у которых есть обычный смысл, запрещать нельзя:
«побудь дома», «домашние дела», «рабочая среда», «выбор», «вывод», «солнце
вышло», «знак внимания», «рак» и «весы» как предметы. Ловится только
астрологический оборот: номер рядом с «домом», планета «в Деве», «знак
Скорпиона». Иначе проверка отбраковывала бы нормальные тексты, и человек
получал бы запасной текст там, где модель ответила хорошо, — ошибка, которую
никто не заметит. Набор нормальных фраз закреплён тестом.
"""
from __future__ import annotations

import json
import re

_F = re.IGNORECASE | re.UNICODE

_SIGN_STEMS = r"(?:овн|тельц|близнец|рак[аеу]?|льв|дев[еыу]|вес(?:ах|ы)|скорпион|стрельц|козерог|водоле|рыб)"
_PLANET_STEMS = r"(?:меркури|венер|марс|юпитер|сатурн|уран|нептун|плутон)"
_ORDINAL = (
    r"(?:\d{1,2}(?:-?(?:м|й|ом))?|перв|втор|трет|четв[её]рт|пят|шест|седьм|восьм|девят|"
    r"десят|одиннадцат|двенадцат)\w*"
)
_MONTHS = r"(?:январ|феврал|марта?\b|апрел|ма[яе]\b|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*"

# Для обоих видов текста.
_COMMON = [
    ("название аспекта", re.compile(r"\b(?:трин\w*|секстил\w*|оппозици\w*|квадрат(?:а|е|ом|у|ы|ов|ами|ах)?)\b", _F)),
    ("слово «аспект»", re.compile(r"\bаспект\w*", _F)),
    ("соединение как аспект", re.compile(r"\bсоединени\w*\s+с\s+(?:солнц|лун|" + _PLANET_STEMS + r")", _F)),
    ("транзит", re.compile(r"\bтранзит\w*", _F)),
    ("натальный", re.compile(r"\bнатальн\w*", _F)),
    ("асцендент/MC", re.compile(r"\b(?:асцендент\w*|десцендент\w*|mc|asc)\b", _F)),
    ("градусы", re.compile(r"\bградус\w*|°", _F)),
    ("куспид", re.compile(r"\bкуспид\w*", _F)),
    ("номер дома", re.compile(r"\b(?:в|во)\s+" + _ORDINAL + r"\s+дом\w*", _F)),
    ("номер дома", re.compile(r"\b" + _ORDINAL + r"\s+дом\w*", _F)),
    ("номер дома", re.compile(r"\bдом\w*\s+(?:№\s*)?\d{1,2}\b", _F)),
    ("слово «AI»/«ИИ»", re.compile(r"\b(?:ai|ии)\b", _F)),
    ("обращение на «вы»", re.compile(
        r"\b(?:вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашего|вашей|вашему|вашим|вашими|ваших|вашу)\b", _F)),
]

# Только для дневного: ни планет, ни знаков в астрологическом смысле, ни дат.
_DAILY = [
    ("планета", re.compile(r"\b" + _PLANET_STEMS + r"\w*", _F)),
    ("светило в знаке", re.compile(r"\b(?:солнц|лун)\w*\s+(?:в|во)\s+" + _SIGN_STEMS, _F)),
    ("знак зодиака", re.compile(r"\bзнак\w*\s+(?:зодиака|" + _SIGN_STEMS + r")", _F)),
    ("дата", re.compile(r"\b\d{1,2}\s+" + _MONTHS, _F)),
    ("дата", re.compile(r"\b\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\b", _F)),
    ("год", re.compile(r"\b20\d{2}\b", _F)),
    ("время", re.compile(r"\b\d{1,2}:\d{2}\b", _F)),
    # Текст дня кэшируется по дате и служит «завтра» и «сегодня» сразу
    # (forecast/router.py) — привязка к одному из них где-то будет неправдой.
    # «Вчера» в списке остаётся: слово неправда в обеих ролях.
    ("сегодня/завтра/вчера", re.compile(
        r"\b(?:сегодня\w*|сегодняшн\w*|завтра\w*|завтрашн\w*|вчера\w*|вчерашн\w*)\b", _F)),
    ("день недели", re.compile(
        r"\b(?:в|во|к|до|с|со|по)\s+(?:понедельник\w*|вторник\w*|среду|четверг\w*|пятниц\w*|субботу|субботы|воскресенье|воскресенья)\b", _F)),
]

# Тон: без запугивания и фатализма (решение владельца 24.09.2026 — в отзывах
# хвалят «без фатализма и запугиваний»). Для обоих видов текста.
# ⚠️ Каждое слово — корнем с \b в начале или перечнем форм, и выбор между ними
# не стилистика: \bопасн не задевает «безопасно», перечень форм «измена»
# не задевает «изменение», а «умер» корнем задел бы «умеренно».
# Не запрещены намеренно: «не страшно» (его говорит запасной текст),
# «береги себя» (так CLAUDE.md и предлагает писать без рода), «кризис»,
# «потеря», «нельзя», «здоровье» — у них обычный, не пугающий смысл.
# Предупреждение остаётся возможным — мягко и с советом, это правило промпта.
# Все имена начинаются с TONE_PREFIX: по нему router считает отбраковки по тону.
TONE_PREFIX = "тон: "
_TONE = [
    (TONE_PREFIX + "болезнь", re.compile(r"\b(?:болезн|заболе)\w*", _F)),
    (TONE_PREFIX + "смерть", re.compile(
        r"\b(?:смерт\w*|умереть|умрешь|умрёшь|умер|умерла|умерли|умира\w*|гибел\w*|гибн\w*|погиб\w*)\b", _F)),
    (TONE_PREFIX + "авария", re.compile(r"\b(?:авари\w*|несчастн\w*\s+случа\w*|травм\w*)", _F)),
    (TONE_PREFIX + "катастрофа", re.compile(
        r"\b(?:катастроф\w*|трагеди\w*|трагич\w*|бедстви\w*|крах(?:а|у|ом|е)?\b|бед(?:а|ы|е|у|ой|ам|ами|ах)?\b)", _F)),
    (TONE_PREFIX + "опасность", re.compile(r"\b(?:опасн\w*|угроз\w*|угрожа\w*)", _F)),
    (TONE_PREFIX + "фатализм", re.compile(
        r"\b(?:роков\w*|фатальн\w*|неизбеж\w*|обреч\w*|порч(?:а|и|у|е|ей)\b|сглаз\w*|"
        r"измен(?:а|ы|е|у|ой|ам|ами|ах)\b|предательств\w*)", _F)),
    (TONE_PREFIX + "запрет-приказ", re.compile(
        r"\bни\s+в\s+коем\s+случае\b|\bкатегорическ\w*|\bберегись\b", _F)),
]
_COMMON += _TONE


def is_tone_problem(problem: str) -> bool:
    return problem.startswith(TONE_PREFIX)


_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿️]")
_DATE_MENTION = re.compile(r"\b\d{1,2}\s+" + _MONTHS, _F)
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
_NUMERIC_DATE = re.compile(r"\b\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\b")

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]


def date_ru(d) -> str:
    """«12 сентября» — единственный формат даты, который код отдаёт модели."""
    return f"{d.day} {MONTHS_GEN[d.month - 1]}"


def _hits(text: str, rules) -> list[str]:
    return [name for name, rx in rules if rx.search(text)]


def problems_common(text: str) -> list[str]:
    return _hits(text, _COMMON)


def problems_daily(text: str) -> list[str]:
    out = _hits(text, _COMMON) + _hits(text, _DAILY)
    if _EMOJI.search(text):
        out.append("эмодзи")
    return out


def split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(parts) == 1:
        parts = [p.strip() for p in text.strip().split("\n") if p.strip()]
    return parts


# Образец — 120–180 слов. Допуск шире, чтобы не бросать хороший ответ в
# запасной из-за десятка слов; грубый промах (абзац или простыня) — брак.
DAILY_MIN_WORDS, DAILY_MAX_WORDS = 90, 230


def check_daily(text: str) -> tuple[list[str], list[str]]:
    """(абзацы, проблемы). Пустой список проблем — текст годен."""
    paragraphs = split_paragraphs(text or "")
    problems = problems_daily(text or "")
    words = len(re.findall(r"\w+", text or ""))
    if not 2 <= len(paragraphs) <= 3:
        problems.append(f"абзацев {len(paragraphs)}, нужно 2–3")
    if not DAILY_MIN_WORDS <= words <= DAILY_MAX_WORDS:
        problems.append(f"слов {words}")
    return paragraphs, problems


def parse_json_reply(raw: str) -> dict | None:
    """Устойчивый разбор: ```json-обёртка, текст до и после объекта.
    Неразобранное — None, то есть непрошедший ответ."""
    if not raw:
        return None
    s = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE)
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(s[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# Только маркеры и нумерация вида «1.»/«2)». ⚠️ Не голые цифры: строка,
# начинающаяся с даты («31 декабря…»), иначе теряла число, и выдуманная
# дата проходила сверку с разрешёнными — поймано тестом.
_LEAD = re.compile(r"^(?:[\s•·\-–—*]+|\d{1,2}[.)]\s+)+")


def _clean_item(s) -> str:
    """Маркеры списка и эмодзи ставит интерфейс, не модель: снимаем их."""
    s = _EMOJI.sub("", str(s or ""))
    return _LEAD.sub("", s).strip()


def check_lunation(
    data: dict | None, allowed_dates: set[str], allowed_times: set[str], need_warning: bool,
) -> tuple[dict | None, list[str]]:
    """(нормализованный блок, проблемы). Даты и время в тексте — только
    посчитанные кодом (allowed_dates, allowed_times)."""
    if not data:
        return None, ["ответ не разобран как JSON"]
    out = {
        "headline": _clean_item(data.get("headline")),
        "sign_meaning": _clean_item(data.get("sign_meaning")),
        "actions": [a for a in (_clean_item(x) for x in data.get("actions") or []) if a],
        "warning": None,
        "closing": _clean_item(data.get("closing")),
    }
    w = data.get("warning")
    if isinstance(w, dict) and (w.get("text") or w.get("tips")):
        out["warning"] = {
            "text": _clean_item(w.get("text")),
            "tips": [t for t in (_clean_item(x) for x in w.get("tips") or []) if t],
        }

    problems = []
    for key in ("headline", "sign_meaning", "closing"):
        if not out[key]:
            problems.append(f"пусто: {key}")
    if not 5 <= len(out["actions"]) <= 7:
        problems.append(f"действий {len(out['actions'])}, нужно 5–7")
    if need_warning:
        if not out["warning"] or not out["warning"]["text"] or not 3 <= len(out["warning"]["tips"]) <= 5:
            problems.append("нет блока предупреждения (3–5 советов)")
    elif out["warning"] and not 3 <= len(out["warning"]["tips"]) <= 5:
        problems.append("блок предупреждения без 3–5 советов")

    full = lunation_text(out)
    problems += problems_common(full)
    allowed = {d.lower() for d in allowed_dates}
    for m in _DATE_MENTION.finditer(full):
        if m.group(0).lower() not in allowed:
            problems.append(f"дата не из расчёта: {m.group(0)}")
    for m in _TIME.finditer(full):
        if m.group(0) not in allowed_times:
            problems.append(f"время не из расчёта: {m.group(0)}")
    for m in _NUMERIC_DATE.finditer(full):
        problems.append(f"дата цифрами: {m.group(0)}")
    return out, problems


def lunation_text(block: dict) -> str:
    parts = [block.get("headline", ""), block.get("sign_meaning", ""), *block.get("actions", [])]
    if block.get("warning"):
        parts += [block["warning"].get("text", ""), *block["warning"].get("tips", [])]
    parts.append(block.get("closing", ""))
    return "\n".join(p for p in parts if p)
