/**
 * FeedEventCard.jsx — карточка события в потоке ленты (§8 спецификации).
 *
 * Состав полей взят из спецификации дословно и не расширен: время,
 * заголовок, знаки, признак точности, орб, тизер, действие. Того, чего в
 * §8 нет (эмодзи фаз, номер дома, значок планеты), здесь нет тоже — эти
 * поля в данных есть, но решение показывать их не принималось.
 *
 * Карточка одна на все семь видов событий, остающихся в потоке (transit,
 * planner_period, planner_moon_house, moon_phase, eclipse, retrograde,
 * solar_event). Отдельных вёрсток по kind нет намеренно: у не-транзитов
 * просто нет части полей (знаков, орба, тизера), и соответствующие строки
 * не рисуются. Развилка `if (kind === …)` на каждый вид дала бы семь
 * почти одинаковых блоков, которые расходятся при первой же правке.
 *
 * ⚠️ Кнопка действия сейчас никуда не ведёт. §8 требует её показать
 * («Интерпретация» / «Открыть доступ»), но ни экрана интерпретации, ни
 * модалки апгрейда в мобильном приложении пока не существует — оба
 * вынесены в отдельные задания. Обработчик приходит пропсом `onAction`;
 * пока его не передают, кнопка отрисована, но неактивна, и это заявленное
 * состояние первого захода, а не забытый провод.
 */

import React from 'react';
import { signRu, timePart } from '../lib/feedTime';

// Высота блока пропорциональна длительности (§8). Коэффициент подобран под
// то, что реально остаётся в потоке после изъятия долгосрочных периодов:
// самый длинный — месячный период Солнца, 30 суток, то есть +75px к
// базовой высоте. Потолка нет: нужен ли он вообще — открытый вопрос §12.2,
// его решают на макете, а не здесь.
const PX_PER_DAY = 2.5;

/** Точка на шкале (транзит, фаза, станция) против периода с длительностью. */
function durationHeight(event) {
  if (!event.ends_at || !event.duration_days) return undefined;
  return Math.round(event.duration_days * PX_PER_DAY);
}

/**
 * Что написано на кнопке.
 *
 * `teaser != null` — единственный признак «закрыто» для транзита (§8):
 * бэкенд уже учёл free_unlocked и топ-2 значимых транзита на free открыты.
 * Выводить это из тарифа на клиенте нельзя — получилась бы вторая копия
 * тарифного правила, которая разойдётся с серверной.
 *
 * `locked` закрывает периоды планера, у которых тизера нет вовсе.
 * У остальных видов (фаза, затмение, равноденствие, станция) действия нет:
 * разбирать нечего, и кнопка «Интерпретация» под равноденствием обещала бы
 * несуществующий экран.
 */
function actionLabel(event) {
  if (event.teaser || event.locked) return 'Открыть доступ';
  if (event.kind === 'transit') return 'Интерпретация';
  return null;
}

const rowStyle = {
  fontSize: 13,
  fontFamily: 'var(--font-body)',
  color: 'var(--text-secondary)',
  lineHeight: 1.5,
};

export default function FeedEventCard({ event, onAction }) {
  const meta = event.meta || {};
  const label = actionLabel(event);
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

  return (
    <article
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 20,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        // minHeight, а не height: длительность задаёт нижнюю границу, но
        // текст тизера не должен обрезаться, если он длиннее блока.
        minHeight: extraHeight ? 64 + extraHeight : undefined,
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.09em',
          fontFamily: 'var(--font-display)',
          color: 'var(--text-secondary)',
        }}
      >
        {timePart(event.at)}
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

      {event.teaser && (
        <div style={{ ...rowStyle, marginTop: 2 }}>
          {event.teaser.intro && <p style={{ margin: 0 }}>{event.teaser.intro}</p>}
          {event.teaser.outro && (
            <p style={{ margin: '6px 0 0' }}>{event.teaser.outro}</p>
          )}
        </div>
      )}

      {label && (
        <button
          type="button"
          className="mobile-link"
          disabled={!onAction}
          onClick={onAction ? () => onAction(event) : undefined}
          style={{ alignSelf: 'flex-start', marginTop: 2, padding: '8px 0' }}
        >
          {label}
        </button>
      )}
    </article>
  );
}
