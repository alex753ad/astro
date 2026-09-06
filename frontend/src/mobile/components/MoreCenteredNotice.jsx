/**
 * MoreCenteredNotice.jsx — общий блок «загрузка/ошибка/пусто» для экрана
 * «Ещё» и его под-разделов (История, Друзья, Уведомления, Настройки).
 *
 * Тот же визуальный приём, что и локальный `CenteredNotice` в
 * FeedScreen.jsx/ChartScreen.jsx, но здесь одним файлом на пять
 * потребителей — дублировать его пять раз подряд смысла больше нет
 * (те два места не трогаем, они не часть этого захода).
 *
 * Любой отказ обязан довести до кнопки «Повторить», не оставлять
 * скелет висеть — правило §8 SPEC_CHART_SCREEN.md / SPEC_MORE_SCREEN.md.
 */

import React from 'react';

export default function MoreCenteredNotice({ title, text, action, onAction }) {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
        padding: '48px 24px',
        textAlign: 'center',
      }}
    >
      <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
        {title}
      </p>
      {text && (
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
          {text}
        </p>
      )}
      {action && (
        <button type="button" className="mobile-link" onClick={onAction} style={{ marginTop: 4 }}>
          {action}
        </button>
      )}
    </div>
  );
}
