/**
 * ExpertModeToggle.jsx
 * Кнопка-переключатель режима эксперта. Размещается в шапке ChartPage.
 */

import React from 'react';

export default function ExpertModeToggle({ enabled, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      title={enabled ? 'Выключить режим эксперта' : 'Включить режим эксперта'}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '7px',
        padding: '7px 14px',
        borderRadius: '20px',
        border: `1.5px solid ${enabled ? 'var(--color-border-info)' : 'var(--color-border-secondary)'}`,
        background: enabled ? 'var(--color-background-info)' : 'transparent',
        color: enabled ? 'var(--color-text-info)' : 'var(--color-text-secondary)',
        fontSize: '13px',
        fontWeight: enabled ? '500' : '400',
        cursor: 'pointer',
        transition: 'border-color 0.15s, background 0.15s, color 0.15s',
        whiteSpace: 'nowrap',
        userSelect: 'none',
        lineHeight: 1,
      }}
    >
      <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
        <circle cx="6.5" cy="6.5" r="5.5" stroke="currentColor" strokeWidth="1.1" />
        <path
          d="M6.5 2L7.55 5.45L11 6.5L7.55 7.55L6.5 11L5.45 7.55L2 6.5L5.45 5.45L6.5 2Z"
          fill="currentColor"
          opacity={enabled ? 1 : 0.55}
        />
      </svg>
      Режим эксперта
      <span
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: enabled ? 'var(--color-text-info)' : 'var(--color-border-secondary)',
          flexShrink: 0,
          transition: 'background 0.15s',
        }}
      />
    </button>
  );
}
