/**
 * FeedTodayMarker.jsx — маркер «СЕГОДНЯ» на линии времени (§2
 * SPEC_FEED_VISUAL.md). Ставится в FeedScreen.jsx один раз, между вчерашним
 * и сегодняшним днём — не заменяет липкий заголовок дня, идёт вместе с ним.
 */

import React from 'react';

export default function FeedTodayMarker() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0' }}>
      <span
        style={{
          flexShrink: 0,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.09em',
          textTransform: 'uppercase',
          fontFamily: 'var(--font-display)',
          color: 'var(--accent-glow)',
        }}
      >
        Сегодня
      </span>
      <span style={{ flex: 1, height: 1, background: 'var(--accent)' }} />
    </div>
  );
}
