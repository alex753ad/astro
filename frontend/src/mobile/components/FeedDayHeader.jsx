/**
 * FeedDayHeader.jsx — граница суток в ленте.
 *
 * С 15.09.2026 день в ленте — БЛОК, а не строка в потоке (DESIGN_SYSTEM.md §5,
 * решение владельца по образцу `frontend/feed-rhythm-specimen.html`). Заголовок
 * из подписи 13px того же цвета, что строки внутри карточек, стал границей:
 * дата антиквой, день недели капителью гротеска, линия и воздух до и после.
 *
 * ⚠️ Заголовок — ЕДИНСТВЕННЫЙ носитель ритма на большей части ленты, и это
 * измерено, а не предположено: в боевой выдаче 68 дней из 148 не содержат ни
 * одной карточки (50 из них — вообще только лунный фон), самая длинная серия
 * дней подряд без карточки — шесть. То есть экран, целиком состоящий из сжатых
 * строк, — обычное состояние ленты, а не край. Ослабить заголовок «потому что
 * рядом и так есть карточки» нельзя: рядом их нет.
 *
 * ⚠️ Блок обязан быть пропорционален содержанию (`quiet`): у дня, где кроме
 * лунного фона ничего нет, нижнего отступа почти не остаётся. Иначе полсотни
 * одинаковых пустых дней дают ровную гребёнку — ту же массу, из которой
 * уходили, только собранную из заголовков.
 *
 * `position: sticky` сохранён с прежнего захода, и два его условия — тоже:
 *
 *   1. Заголовок обязан быть непрозрачным (`background: var(--bg)`).
 *      Прилипший прозрачный заголовок пропускает под собой карточки, и текст
 *      накладывается на текст.
 *   2. Ни один предок заголовка внутри FeedScreen не должен получить
 *      `overflow` — это создаст новый контекст прокрутки, и sticky начнёт
 *      липнуть к нему, то есть перестанет липнуть к экрану вовсе. Ошибка
 *      тихая: вёрстка цела, просто заголовки уезжают вместе с потоком.
 *
 * ⚠️ Воздух над заголовком задан `marginTop`, а не `paddingTop`, намеренно:
 * margin лежит ВНЕ блока, и прилипшая шапка не тащит его за собой. Заменить
 * на padding — значит прибавить этот воздух к высоте липкого элемента, а он
 * и так подрос против прежних 13px.
 *
 * z-index нужен, потому что карточки идут в потоке ПОСЛЕ заголовка: без него
 * следующая карточка перекрывала бы прилипший заголовок при прокрутке.
 */

import React from 'react';
import { dayDate, dayLabel, isMonthStart, monthTitle, weekdayLong } from '../lib/feedTime';

const LABEL_STYLE = {
  fontFamily: 'var(--font-body)',
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: '0.09em',
  textTransform: 'uppercase',
  color: 'var(--text-secondary)',
};

export default function FeedDayHeader({ date, today, first = false, quiet = false, sticky = true }) {
  const isToday = date === today;
  const monthStep = isMonthStart(date) && !first;
  return (
    <header
      aria-label={dayLabel(date, today)}
      style={sticky ? {
        position: 'sticky',
        top: 0,
        zIndex: 1,
        // Ступень месяца — тот же приём, что и у дня, на порядок крупнее:
        // добавочный воздух. Своих цветов и линий ей не заводили.
        marginTop: first ? 8 : (monthStep ? 44 : 26),
        paddingBottom: quiet ? 4 : 12,
        background: 'var(--bg)',
      } : {
        // Раскрытый день (сегодняшний) живёт ВНУТРИ поднятой поверхности
        // (FeedScreen.jsx), и здесь заголовок не липнет: прилипая, он
        // отрывался бы от своей же карточки и висел над чужими днями. Линии
        // у него тоже нет — границу этого дня рисует сама поверхность,
        // вторая черта внутри неё была бы повтором.
        paddingBottom: 14,
      }}
    >
      {monthStep && (
        <div style={{ ...LABEL_STYLE, letterSpacing: '0.12em', marginBottom: 8 }}>
          {monthTitle(date, today)}
        </div>
      )}
      {sticky && (
        <div
          style={{
            height: isToday ? 2 : 1,
            background: isToday ? 'var(--accent)' : 'var(--border)',
            marginBottom: 10,
          }}
        />
      )}
      {isToday && (
        <div style={{ ...LABEL_STYLE, letterSpacing: '0.12em', color: 'var(--accent)', marginBottom: 2 }}>
          Сегодня
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <h2
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontSize: sticky ? 21 : 24,
            fontWeight: 700,
            lineHeight: 1.15,
            color: 'var(--text-primary)',
          }}
        >
          {dayDate(date)}
        </h2>
        <span style={LABEL_STYLE}>{weekdayLong(date)}</span>
      </div>
    </header>
  );
}
