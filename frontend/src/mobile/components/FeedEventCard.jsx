/**
 * FeedEventCard.jsx — карточка события в потоке ленты (§8 спецификации).
 *
 * В карточке: время, заголовок, знаки, точность и орб. Всё.
 *
 * ⚠️ Тизера здесь нет намеренно, и это правка спецификации от 05.09.2026.
 * Первый заход показывал intro/outro прямо в карточке — на боевых данных
 * текст оказался ОДИНАКОВЫМ на всех ~700 закрытых карточках (он общий для
 * тарифа, а не для события) и из подсказки превращался в шум, заодно
 * съедая высоту в ленте, где высота значит длительность. Теперь закрытость
 * показывает один компактный значок замка без текста, а полный тизер и
 * кнопка доступа живут в панели по тапу (FeedEventPanel.jsx) — как на вебе,
 * где разбор тоже открывается отдельной панелью, а не лежит в списке.
 *
 * Карточка одна на все семь видов событий, остающихся в потоке. Отдельных
 * вёрсток по kind нет: у не-транзитов просто нет части полей (знаков, орба),
 * и строки не рисуются. Развилка на каждый вид дала бы семь почти
 * одинаковых блоков, которые разойдутся при первой же правке.
 */

import React from 'react';
import { signRu, timePart } from '../lib/feedTime';

// Высота блока пропорциональна длительности (§8). Коэффициент подобран под
// то, что реально остаётся в потоке после изъятия долгосрочных периодов:
// самый длинный — месячный период Солнца, 30 суток, то есть +75px к базовой
// высоте. Потолка нет: нужен ли он — открытый вопрос §12.2, решается на
// макете.
const PX_PER_DAY = 2.5;

// Замок 14×14, stroke=currentColor — правило B5 DESIGN_SYSTEM.md §8: иначе
// в тёмной теме значок останется тёмным на тёмном.
const LOCK_ICON = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
    <rect x="2.6" y="6" width="8.8" height="6.2" rx="1.6" stroke="currentColor" strokeWidth="1.4" />
    <path d="M4.8 6V4.4a2.2 2.2 0 0 1 4.4 0V6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

/** Точка на шкале (транзит, фаза, станция) против периода с длительностью. */
function durationHeight(event) {
  if (!event.ends_at || !event.duration_days) return undefined;
  return Math.round(event.duration_days * PX_PER_DAY);
}

/**
 * Закрыто ли событие.
 *
 * `teaser != null` — единственный признак «закрыто» для транзита (§8):
 * бэкенд уже учёл free_unlocked, и топ-2 значимых транзита на free открыты.
 * Выводить это из тарифа на клиенте нельзя — получилась бы вторая копия
 * тарифного правила, которая разойдётся с серверной. `locked` закрывает
 * периоды планера, у которых тизера нет вовсе.
 */
export function isLocked(event) {
  return Boolean(event.teaser || event.locked);
}

const rowStyle = {
  fontSize: 13,
  fontFamily: 'var(--font-body)',
  color: 'var(--text-secondary)',
  lineHeight: 1.5,
};

export default function FeedEventCard({ event, onOpen }) {
  const meta = event.meta || {};
  const locked = isLocked(event);
  const extraHeight = durationHeight(event);

  // Строка знаков — только когда пришли оба знака: у не-транзитов их нет.
  const hasSigns = meta.transit_sign && meta.natal_sign;
  const degree = typeof meta.transit_degree === 'number'
    ? `${meta.transit_degree.toFixed(1)}° `
    : '';

  // Орб и точность приходят вместе и только у транзита.
  const hasOrb = typeof meta.peak_orb === 'number';
  const precision = typeof meta.applying === 'boolean'
    ? (meta.applying ? 'точный' : 'отходит')
    : null;

  // Тапом открывается только то, что есть чем открыть: у события без тизера
  // и без locked панели показать нечего, и «нажимаемая» карточка, которая
  // ничего не делает, читается как поломка.
  const openable = locked && typeof onOpen === 'function';

  return (
    <article
      onClick={openable ? () => onOpen(event) : undefined}
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 20,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        cursor: openable ? 'pointer' : 'default',
        // minHeight, а не height: длительность задаёт нижнюю границу, но
        // длинный заголовок не должен обрезаться.
        minHeight: extraHeight ? 64 + extraHeight : undefined,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.09em',
            fontFamily: 'var(--font-display)',
            color: 'var(--text-secondary)',
          }}
        >
          {timePart(event.at)}
        </span>
        {locked && (
          <span
            title="Разбор — на платном тарифе"
            aria-label="Закрыто"
            style={{ display: 'inline-flex', color: 'var(--text-secondary)', opacity: 0.55 }}
          >
            {LOCK_ICON}
          </span>
        )}
      </div>

      <h3
        style={{
          margin: 0,
          fontSize: 18,
          fontWeight: 600,
          fontFamily: 'var(--font-display)',
          color: 'var(--text-primary)',
          lineHeight: 1.3,
        }}
      >
        {event.text || '—'}
      </h3>

      {hasSigns && (
        <div style={rowStyle}>
          {degree}{signRu(meta.transit_sign)} → {signRu(meta.natal_sign)}
        </div>
      )}

      {(precision || hasOrb) && (
        <div style={rowStyle}>
          {precision}
          {precision && hasOrb ? ' · ' : ''}
          {hasOrb ? `орб ${meta.peak_orb.toFixed(1)}°` : ''}
        </div>
      )}
    </article>
  );
}
