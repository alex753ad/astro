"""backend/feed/horizon.py — где лента начинается и где заканчивается.

Одно место на всю ленту. Ни builder, ни router не считают границы сами:
разъехавшиеся границы — это ровно тот дефект, из-за которого лунные события
могли бы торчать за краем транзитов и выглядеть поломкой.

Решение владельца 04.09.2026:

* НАЗАД — ровно месяц, одинаково для всех тарифов. Глубина прошлого не
  продаётся: коммерческой ценности в нём нет, а ощущение полноты ленты нужно
  всем. Поэтому здесь НЕ используется PAST_WINDOW_ABUSE_MONTHS (24 месяца) —
  тот бэкстоп против скриптов, а не витрина.

* ВПЕРЁД — по тарифу, ЧЕРЕЗ существующий transits_date_window. Своей логики
  горизонта у ленты нет и заводить её нельзя: второй источник тарифных
  горизонтов разошёлся бы с первым при первой же правке сетки.

* Горизонт ленты — самый узкий из источников, то есть транзитный. За его
  границей лента заканчивается ЦЕЛИКОМ, включая лунные события.

  ⚠️ Про лунные события это не формальность. Ручка /calendar/lunar не имеет
  тарифного гейта вообще — она публичная и отдаёт любой месяц любого года без
  авторизации (проверено боем, FEED_API_RECON_2026-09-04.md). Если не
  ограничить её здесь, за краем транзитов останутся редкие лунные значки:
  затмение в марте при ленте, кончающейся в декабре. Это выглядит как
  поломка, а не как граница тарифа. Полный лунный календарь без ограничений
  остаётся отдельным месячным видом — там он и живёт.
"""

from __future__ import annotations

import calendar as _calendar
from dataclasses import dataclass
from datetime import date
from typing import Optional

from backend.auth.rate_limits import transits_date_window

# Порядок сетки. Единственное место, где лента знает, какой тариф за каким —
# нужно, чтобы отдать фронту «что открывается дальше» и не дублировать таблицу
# тарифов на клиенте.
TIER_ORDER = ("free", "lite", "pro", "premium")

# Сколько ленты открыто в прошлое. Одно число на все тарифы — см. шапку.
PAST_MONTHS = 1


def _minus_one_month(d: date) -> date:
    """Та же дата месяцем раньше. 31 марта → 28/29 февраля."""
    year = d.year - 1 if d.month == 1 else d.year
    month = 12 if d.month == 1 else d.month - 1
    return date(year, month, min(d.day, _calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class Horizon:
    start: date
    end: date
    tier: str
    next_tier: Optional[str]
    next_tier_name: Optional[str]
    next_end: Optional[date]

    def clamp(self, from_date: date, to_date: date) -> tuple[date, date]:
        """Запрошенное окно, обрезанное горизонтом.

        Обрезка, а не 403: лента листается, и упереться в край — обычное
        состояние, а не ошибка. Пустой ответ с границей в шапке фронт нарисует
        карточкой «дальше — на Веге», а на 403 ему пришлось бы гадать.
        """
        return max(from_date, self.start), min(to_date, self.end)

    def to_dict(self) -> dict:
        return {
            "from": self.start.isoformat(),
            "to": self.end.isoformat(),
            "tier": self.tier,
            # Что откроется на следующем тарифе. Дату считает бэкенд той же
            # функцией, что и свой горизонт, — иначе клиенту пришлось бы
            # держать у себя копию тарифной сетки и обновлять её вместе с ней.
            "next_tier": (
                None if self.next_tier is None else {
                    "tier": self.next_tier,
                    "name": self.next_tier_name,
                    "to": self.next_end.isoformat() if self.next_end else None,
                }
            ),
        }


def feed_horizon(tier: Optional[str], today: date) -> Horizon:
    """Границы ленты для тарифа на сегодня."""
    from backend.email_service import TIER_NAMES

    current = tier if tier in TIER_ORDER else "free"

    # Вперёд — верхняя граница транзитного окна, как есть. Нижнюю границу
    # transits_date_window не используем: там 24 месяца назад (бэкстоп от
    # скриптов), а лента показывает месяц.
    _, end = transits_date_window(current, today)
    start = _minus_one_month(today)

    idx = TIER_ORDER.index(current)
    next_tier = TIER_ORDER[idx + 1] if idx + 1 < len(TIER_ORDER) else None
    next_end = transits_date_window(next_tier, today)[1] if next_tier else None

    # У Лиры и Ориона горизонт транзитов одинаковый только в одну сторону:
    # premium = 24 месяца против 12 у pro, так что next_end всегда дальше.
    # Если сетка когда-нибудь сравняет соседние тарифы, показывать «дальше —
    # на следующем» будет нечестно: там ничего не прибавится.
    if next_end is not None and next_end <= end:
        next_tier, next_end = None, None

    return Horizon(
        start=start,
        end=end,
        tier=current,
        next_tier=next_tier,
        next_tier_name=TIER_NAMES.get(next_tier) if next_tier else None,
        next_end=next_end,
    )
