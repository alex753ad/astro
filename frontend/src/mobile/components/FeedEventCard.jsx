/**
 * FeedEventCard.jsx — карточка события в потоке ленты (§8 спецификации).
 *
 * В карточке: время, заголовок, знаки, точность и орб.
 *
 * ⚠️ Тизера здесь нет намеренно, и это правка спецификации от 05.09.2026.
 * Первый заход показывал intro/outro прямо в карточке — на боевых данных
 * текст оказался ОДИНАКОВЫМ на всех ~700 закрытых карточках (он общий для
 * тарифа, а не для события) и из подсказки превращался в шум, заодно
 * съедая высоту в ленте, где высота значит длительность. Полный тизер и
 * кнопка доступа живут в панели по тапу (FeedEventPanel.jsx) — как на вебе,
 * где разбор тоже открывается отдельной панелью, а не лежит в списке.
 *
 * ⚠️ Помечается ОТКРЫТОЕ, а не закрытое (решение владельца 05.09.2026).
 * Сначала стоял замок на закрытых — и он оказался на 689 карточках из 718:
 * пометка, которая стоит почти везде, не сообщает ничего, кроме шума.
 * Открытых на free всего два (топ-2 значимых транзита, их выбирает
 * бэкенд) — вот их и видно.
 *
 * Карточка одна на все семь видов событий, остающихся в потоке. Отдельных
 * вёрсток по kind нет: у не-транзитов просто нет части полей (знаков, орба),
 * и строки не рисуются. Развилка на каждый вид дала бы семь почти
 * одинаковых блоков, которые разойдутся при первой же правке.
 */

import React from 'react';
import BlurredHint from './BlurredHint';
import { eventTitle, signRu, timePart } from '../lib/feedTime';

// Высота блока пропорциональна длительности (§8). Коэффициент подобран под
// то, что реально остаётся в потоке после изъятия долгосрочных периодов:
// самый длинный — месячный период Солнца, 30 суток, то есть +75px к базовой
// высоте. Потолок НЕ вводится (решение владельца, §12.2): пропорция должна
// остаться честной.
const PX_PER_DAY = 2.5;

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

  // Витрина под блюром — только у закрытого периода: у него есть высота
  // (она значит длительность), но нечего в ней показать, потому что на free
  // сервер отдаёт пустые theme и groups.
  const showFiller = locked && Boolean(extraHeight);

  // ⚠️ Высота по длительности идёт В ПАРЕ с витриной, а не сама по себе.
  // Растянутая карточка без содержимого — это пустая коробка, и владелец
  // просил такие не тянуть: у них высота по контенту. Поэтому minHeight
  // ставится ровно тогда, когда есть чем его заполнить.
  const minHeight = showFiller ? 64 + extraHeight : undefined;

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

  // Открытый разбор помечается только у транзитов: у фазы, затмения,
  // равноденствия и станции разбора нет в принципе, и «открыто» на них
  // значило бы «доступно то, чего не существует».
  const openInterpretation = event.kind === 'transit' && !locked;

  // Тапом открывается только то, что есть чем открыть: у события без тизера
  // и без locked панели показать нечего, и «нажимаемая» карточка, которая
  // ничего не делает, читается как поломка.
  const openable = locked && typeof onOpen === 'function';

  return (
    <article
      onClick={openable ? () => onOpen(event) : undefined}
      style={{
        background: 'var(--bg-card)',
        border: `1px solid ${openInterpretation ? 'var(--accent)' : 'var(--border)'}`,
        borderRadius: 20,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        cursor: openable ? 'pointer' : 'default',
        // minHeight, а не height: длительность задаёт нижнюю границу, но
        // длинный заголовок не должен обрезаться.
        minHeight,
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
        {openInterpretation && (
          <span
            // Точка объясняет рамку: одна рамка без подписи читается как
            // «выделено», но не говорит чем.
            aria-label="Разбор открыт"
            title="Разбор открыт"
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: 'var(--accent)',
              display: 'inline-block',
            }}
          />
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
        {eventTitle(event)}
      </h3>

      {/* Тема периода — вторая строка, если пришла. На free она пустая
          (сервер отдаёт `theme: ""` вместе с locked), и строки не будет. */}
      {meta.theme && <div style={rowStyle}>{meta.theme}</div>}

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

      {/*
        flex:1 + overflow:hidden — обязательная часть, а не оформление.
        Витрина ЗАПОЛНЯЕТ оставшееся место, но не добавляет своего: иначе
        двухдневный проход Луны с тремя строками витрины стал бы ВЫШЕ
        тридцатидневного периода Солнца, и пропорция длительности — главный
        приём ленты — начала бы врать в обратную сторону.
      */}
      {showFiller && (
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <BlurredHint />
        </div>
      )}
    </article>
  );
}
