/**
 * FeedTimelineNode.jsx — один узел вертикальной линии времени (§2-3
 * SPEC_FEED_VISUAL.md, «Заход А»: скелет структуры, карточки не трогаем).
 *
 * Колонка времени слева (64 px) + линия + точка + содержимое справа.
 * Содержимое — это ЦЕЛИКОМ существующий children (FeedEventCard как есть,
 * либо FeedLunarFold без своей точки — см. `dot={null}` у вызывающего).
 *
 * ⚠️ Линия — не один элемент на весь экран, а сегмент на каждый узел
 * (`position:absolute; top:0; bottom:0` внутри `position:relative`-обёртки,
 * которая включает и paddingBottom узла). Это даёт непрерывную линию
 * ВНУТРИ дня — соседние узлы стыкуются день без зазора, потому что зазор
 * между ними — это paddingBottom текущего узла, а не внешний gap
 * контейнера, и абсолютный элемент с top:0/bottom:0 растягивается на всю
 * область узла, padding включительно.
 *
 * Линия рвётся на липком заголовке дня (`FeedDayHeader.jsx`) и на маркере
 * «СЕГОДНЯ» (`FeedTodayMarker.jsx`) — оба живут вне узла и линии не рисуют.
 * Непрерывность через день — открытый пункт устройства (§10), не решённый
 * здесь архитектурно.
 */

import React from 'react';

const TIME_COL_WIDTH = 64;
const LINE_LEFT = TIME_COL_WIDTH - 1; // 63px от левого края контейнера ленты

export default function FeedTimelineNode({ time, bold, color, size, children, gap = 12 }) {
  const hasDot = typeof size === 'number';
  return (
    <div style={{ position: 'relative', paddingBottom: gap }}>
      <span
        style={{
          position: 'absolute',
          left: LINE_LEFT,
          top: 0,
          bottom: 0,
          width: 1,
          background: 'var(--border)',
        }}
      />
      {hasDot && (
        <span
          style={{
            position: 'absolute',
            left: LINE_LEFT,
            top: 6,
            width: size,
            height: size,
            borderRadius: '50%',
            background: 'var(--bg)',
            border: `${size >= 13 ? 2 : 1.5}px solid ${color}`,
            transform: 'translate(-50%, 0)',
          }}
        />
      )}
      <div style={{ display: 'flex', minHeight: 44 }}>
        <div
          style={{
            width: TIME_COL_WIDTH,
            flexShrink: 0,
            textAlign: 'right',
            paddingRight: 14,
            fontFamily: 'var(--font-display)',
            fontVariantNumeric: 'tabular-nums',
            fontSize: bold ? 12 : 11,
            fontWeight: bold ? 700 : 400,
            color: bold ? 'var(--text-primary)' : 'var(--text-secondary)',
            paddingTop: 2,
          }}
        >
          {time}
        </div>
        <div style={{ flex: 1, minWidth: 0, paddingLeft: 16 }}>
          {children}
        </div>
      </div>
    </div>
  );
}
