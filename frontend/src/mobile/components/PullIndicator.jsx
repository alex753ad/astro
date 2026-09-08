/**
 * PullIndicator.jsx — полоска жеста «потянуть, чтобы обновить».
 *
 * Одна на три экрана, как и сам хук (lib/usePullToRefresh.js): три копии
 * этой разметки разошлись бы по текстам и высоте — так в проекте уже было
 * с CenteredNotice, пока его не свели в MoreCenteredNotice.
 *
 * ⚠️ Высоту во время жеста задаёт НЕ этот компонент, а хук — прямой
 * записью в style по `innerRef`, мимо рендера (почему — в шапке хука).
 * Здесь высота выставляется только для фаз «обновляю» и «не удалось»:
 * пока палец на экране, React в этом не участвует вовсе.
 *
 * ⚠️ Крутилки в проекте нет вообще — ни в мобильной сборке, ни в вебе.
 * Заводить её ради этой полоски значит завести новую сущность там, где
 * хватает существующей: ожидание показывается классом `.mobile-skeleton`
 * (та же пульсация, что у скелетов загрузки, mobile.css). При
 * prefers-reduced-motion она гаснет сама — состояние читается текстом, а
 * не движением, как требует §7 DESIGN_SYSTEM.md.
 */

import React from 'react';

const ROW_HEIGHT = 34;

const textStyle = {
  fontFamily: 'var(--font-body)',
  fontSize: 13,
  lineHeight: 1,
  whiteSpace: 'nowrap',
};

export default function PullIndicator({ state, ready, innerRef, style }) {
  return (
    <div
      ref={innerRef}
      aria-live="polite"
      style={{
        // В покое высота нулевая, и полоски на экране нет. Во время жеста
        // её ведёт хук, при обновлении и отказе — эта строка.
        height: state === 'idle' ? 0 : ROW_HEIGHT,
        flexShrink: 0,
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        ...style,
      }}
    >
      {state === 'error' ? (
        <span style={{ ...textStyle, color: 'var(--color-danger)' }}>Не удалось обновить</span>
      ) : (
        <span
          className={state === 'refreshing' ? 'mobile-skeleton' : undefined}
          style={{ ...textStyle, color: 'var(--text-secondary)' }}
        >
          {state === 'refreshing'
            ? 'Обновляю…'
            : (ready ? 'Отпустите, чтобы обновить' : 'Потяните, чтобы обновить')}
        </span>
      )}
    </div>
  );
}
