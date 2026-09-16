/**
 * FeedDayStrip.jsx — полоска дней под шапкой «сейчас» (§7 SPEC_FEED_VISUAL.md).
 *
 * Горизонтальная прокрутка, колонка 42px на день, диапазон — от
 * `horizon.from` до `horizon.to` целиком (не только дни с событиями, в
 * отличие от потока: §6 «дни без событий не появляются» — это правило
 * ленты, полоска показывает календарь, а не список).
 *
 * ⚠️ НЕ липкая (`position: sticky`) — и с 15.09.2026 по другой причине, чем
 * записана ниже: липкий слой в ленте теперь ровно один, и это компактная
 * полоса «сейчас» (FeedNowCompact.jsx). Прежний довод — про заголовки дней,
 * которые липли на том же
 * `top: 0`, координировать отступы без измерения высоты — отдельная задача.
 *
 * ⚠️ «Полоска следует за видимым днём» при прокрутке ленты (последний абзац
 * §7) — НЕ реализовано в этом заходе: это observer на видимость каждой
 * секции дня (IntersectionObserver) поверх и без того длинного списка,
 * самостоятельная по объёму задача. Сделан только тап «полоска → лента»,
 * обратного направления «лента → полоска» нет.
 *
 * ⚠️ Обрезанные колонки на краях экрана — не то же самое, что отступ у
 * КОНЦОВ всего диапазона. `padding` ниже решает второе (не даёт первой и
 * последней колонке всего списка вставать вплотную к краю), но «сегодня»
 * открывается ПО ЦЕНТРУ экрана (`scrollIntoView({inline:'center'})`), и
 * при любой промежуточной прокрутке по бокам от видимой области почти
 * неизбежно торчит кусок соседней колонки — 358px полезной ширины на
 * колонку 46px (42 + gap 4) не делятся ровно, и подгонять момент под это
 * бессмысленно: сама полоска бесконечно длинная. Решение — не бороться с
 * обрезкой, а спрятать её: `mask-image` гасит содержимое у обеих кромок в
 * прозрачность, и обрезанная колонка тает, а не торчит половиной точки.
 */

import React, { useEffect, useRef } from 'react';
import { shiftDays, weekdayShort } from '../lib/feedTime';

const COLUMN_WIDTH = 42;

function buildRange(from, to) {
  const days = [];
  let d = from;
  // Защита от неверного/перевёрнутого диапазона — без неё while ушёл бы в
  // бесконечный цикл, а не просто отрисовал пустую полоску.
  let guard = 0;
  while (d <= to && guard < 800) {
    days.push(d);
    d = shiftDays(d, 1);
    guard += 1;
  }
  return days;
}

export default function FeedDayStrip({ from, to, today, dotsByDay, onSelectDay }) {
  const todayRef = useRef(null);
  const railRef = useRef(null);

  /**
   * Один раз при монтировании — прокрутка к сегодня, чтобы полоска
   * открывалась не с самого начала окна (эквивалент §10 для ленты).
   *
   * ⚠️ Считается СВОИМ `scrollLeft`, а не `scrollIntoView`, и это не
   * стилистика. `scrollIntoView` прокручивает ВСЕ прокручиваемые предки, а не
   * только тот, который имелся в виду: `inline: 'center'` центрировал колонку
   * в полоске, а `block: 'nearest'` тут же поднимал ВЕРТИКАЛЬНЫЙ скроллер
   * ленты (он один на все вкладки, живёт в TabShell.jsx) так, чтобы полоска
   * попала в кадр. Полоска стоит в самом верху ленты — значит страница
   * уезжала в начало окна, то есть на месяц назад, ровно поверх прокрутки к
   * сегодняшнему дню, которую FeedScreen только что сделал.
   *
   * Это гонка, и выигрывал её кто как: эффекты детей выполняются РАНЬШЕ
   * родительских, поэтому подъём успевал встать между первым прыжком к якорю
   * и повторными. Отсюда и вид дефекта — «полоска показывает сегодня, а лента
   * стоит на месяце назад»: два скролла спорили за один и тот же контейнер.
   *
   * `scrollLeft` трогает ровно эту полоску и ничего кроме неё.
   */
  useEffect(() => {
    const rail = railRef.current;
    const cell = todayRef.current;
    if (!rail || !cell) return;
    rail.scrollLeft = cell.offsetLeft - (rail.clientWidth - cell.offsetWidth) / 2;
  }, []);

  if (!from || !to) return null;
  const days = buildRange(from, to);

  return (
    <div
      ref={railRef}
      style={{
        display: 'flex',
        gap: 4,
        overflowX: 'auto',
        overflowY: 'hidden',
        // Слева и справа — не только сверху/снизу: без него первая и
        // последняя колонки стоят вровень с краем экрана, и на прокрутке
        // видна обрезанная половина точек следующей колонки без всякого
        // отступа перед ней — читается как поломка, а не как «есть ещё».
        padding: '4px 8px 12px',
        // Скроллбар скрыт (§7) — Firefox/стандарт и WebKit разными свойствами.
        scrollbarWidth: 'none',
        // Растушёвка кромок (см. предупреждение выше) — обе формы свойства,
        // WebKit (Android/iOS webview — целевая среда) без префикса не берёт.
        maskImage: 'linear-gradient(to right, transparent, black 24px, black calc(100% - 24px), transparent)',
        WebkitMaskImage: 'linear-gradient(to right, transparent, black 24px, black calc(100% - 24px), transparent)',
      }}
      // WebKit не берёт псевдоэлемент из инлайн-стиля — правило для него
      // лежит в mobile.css (.feed-day-strip::-webkit-scrollbar).
      className="feed-day-strip"
    >
      {days.map((date) => {
        const isToday = date === today;
        const dots = (dotsByDay && dotsByDay.get(date)) || [];
        return (
          <button
            key={date}
            type="button"
            ref={isToday ? todayRef : undefined}
            onClick={() => onSelectDay && onSelectDay(date)}
            style={{
              flexShrink: 0,
              width: COLUMN_WIDTH,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 3,
              padding: '6px 0',
              borderRadius: 'var(--radius-md)',
              border: 'none',
              background: isToday ? 'var(--accent)' : 'transparent',
              color: isToday ? '#fff' : 'var(--text-primary)',
            }}
          >
            <span style={{ fontSize: 10, color: isToday ? '#fff' : 'var(--text-secondary)' }}>
              {weekdayShort(date)}
            </span>
            <span style={{ fontSize: 15, fontWeight: 700, fontFamily: 'var(--font-body)', fontVariantNumeric: 'tabular-nums' }}>
              {Number(date.slice(8, 10))}
            </span>
            <span style={{ display: 'flex', gap: 2, height: 4 }}>
              {dots.map((color, i) => (
                <span key={i} style={{ width: 4, height: 4, borderRadius: '50%', background: isToday ? '#fff' : color }} />
              ))}
            </span>
          </button>
        );
      })}
    </div>
  );
}
