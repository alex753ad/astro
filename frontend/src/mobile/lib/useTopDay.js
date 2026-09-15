/**
 * useTopDay.js — какой день сейчас у верхней кромки ленты.
 *
 * Нужен компактной полосе «сейчас» (FeedNowCompact.jsx): после того как
 * заголовки дней перестали быть липкими (решение владельца 15.09.2026,
 * разбор — в шапке FeedDayHeader.jsx), вопрос «какой день я смотрю» при
 * длинной прокрутке отвечает она.
 *
 * ⚠️ Результат отдаётся ФУНКЦИЕЙ, а не состоянием React, и это главное
 * решение этого файла. День у кромки меняется на каждой границе суток — при
 * быстрой прокрутке это десятки раз в секунду. `setState` на каждую смену
 * перерисовывал бы весь список: 148 секций, больше сотни карточек. Поэтому
 * потребитель пишет строку прямо в DOM (одна текстовая нода), а React об этом
 * не знает вовсе.
 *
 * ⚠️ Положения дней измеряются ОДИН раз и кэшируются. Во время прокрутки
 * читается только `scrollTop` — это не чтение раскладки, в отличие от
 * `getBoundingClientRect`, который на каждом кадре заставлял бы браузер
 * пересчитывать всю страницу.
 *
 * ⚠️ Пересчёт по `document.fonts.ready` обязателен. Ровно по этой причине
 * лента трижды прокручивается к сегодняшнему дню при открытии (FeedScreen.jsx):
 * подмена запасного шрифта локальным меняет высоты сотен карточек, и кэш,
 * снятый до неё, указывал бы на чужие дни. Промах здесь тихий — полоса просто
 * показывает соседнюю дату.
 */

import { useEffect } from 'react';

export default function useTopDay(scrollRef, dayRefs, enabled, onChange) {
  useEffect(() => {
    const scroller = scrollRef?.current;
    if (!enabled || !scroller || !dayRefs?.current) return undefined;

    // [{ date, top }] по возрастанию top — положение начала каждого дня в
    // координатах прокрутки.
    let offsets = [];
    let current = null;

    const measure = () => {
      const base = scroller.getBoundingClientRect().top - scroller.scrollTop;
      offsets = [...dayRefs.current.entries()]
        .map(([date, el]) => ({ date, top: el.getBoundingClientRect().top - base }))
        .sort((a, b) => a.top - b.top);
    };

    const apply = () => {
      if (offsets.length === 0) return;
      // Последний день, начало которого уже выше кромки. Двоичный поиск, а не
      // перебор: дней в окне 148, и это происходит на каждом событии прокрутки.
      const y = scroller.scrollTop;
      let lo = 0;
      let hi = offsets.length - 1;
      let found = offsets[0];
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (offsets[mid].top <= y) { found = offsets[mid]; lo = mid + 1; } else { hi = mid - 1; }
      }
      if (found.date !== current) {
        current = found.date;
        onChange(current);
      }
    };

    const remeasure = () => { measure(); apply(); };

    measure();
    apply();
    scroller.addEventListener('scroll', apply, { passive: true });
    window.addEventListener('resize', remeasure);
    document.fonts?.ready?.then(remeasure);
    return () => {
      scroller.removeEventListener('scroll', apply);
      window.removeEventListener('resize', remeasure);
    };
  }, [scrollRef, dayRefs, enabled, onChange]);
}
