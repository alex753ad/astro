/**
 * FeedHorizonCard.jsx — край горизонта, последний элемент ленты (§9).
 *
 * Дата края и название следующего тарифа приходят С БЭКЕНДА
 * (`horizon.next_tier.to` и `.name`) и здесь только подставляются в текст.
 * Тарифную таблицу на клиенте держать нельзя — она разъедется с серверной
 * при первой же правке сетки, а тут её и не нужно: сервер уже посчитал,
 * до какой даты лента откроется на следующем тарифе.
 *
 * `next_tier === null` — значит следующего тарифа нет (Орион, дальше
 * открывать нечего). Карточки в этом случае нет вовсе: обещать
 * несуществующее продолжение хуже, чем закончить ленту молча.
 *
 * За `horizon.to` не показывается ничего, включая лунные события, — но это
 * решает не эта карточка, а бэкенд: он обрезает окно горизонтом до того,
 * как отдать события. Иначе за краем оставались бы одинокие лунные значки,
 * и граница тарифа читалась бы как поломка ленты.
 */

import React from 'react';
import { dayMonth } from '../lib/feedTime';

/**
 * Предложный падеж названия тарифа: «на Веге», «на Лире», «на Орионе».
 *
 * Названия приходят с бэкенда в именительном (Вега, Лира, Орион), а фраза
 * §9 требует предложного. Правило покрывает всю сетку: женские на «а»
 * меняют её на «е», мужские получают «е» в конец. Без склонения выходило
 * «на Вегае» — приписать окончание к неизменённой форме мало.
 */
function inTier(name) {
  return name.endsWith('а') ? `${name.slice(0, -1)}е` : `${name}е`;
}

export default function FeedHorizonCard({ horizon }) {
  const next = horizon?.next_tier;
  if (!next || !next.to || !next.name) return null;

  return (
    <div
      style={{
        marginTop: 8,
        padding: 16,
        borderRadius: 20,
        border: '1px dashed var(--border)',
        background: 'var(--bg-deeper)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        textAlign: 'center',
      }}
    >
      <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
        Дальше — транзиты и периоды до {dayMonth(next.to)}.
      </p>
      <p
        style={{
          margin: 0,
          fontSize: 15,
          fontWeight: 600,
          fontFamily: 'var(--font-display)',
          color: 'var(--text-primary)',
        }}
      >
        Открывается на {inTier(next.name)}
      </p>
    </div>
  );
}
