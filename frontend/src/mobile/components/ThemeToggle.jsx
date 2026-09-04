/**
 * ThemeToggle.jsx — строка переключения темы на вкладке «Ещё».
 *
 * SVG-глиф, stroke="currentColor", без эмодзи — правило B5 DESIGN_SYSTEM.md.
 * Те же пути солнца/луны, что в компоненте ThemeToggle веба
 * (src/components/ThemeToggle.jsx) — свой файл (там кнопка-иконка в шапке,
 * здесь строка настроек в списке), но один и тот же глиф, а не два похожих.
 */

import React from 'react';
import useTheme from '../useTheme.jsx';

function SunIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

export default function ThemeToggle() {
  const { dark, toggle } = useTheme();

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
      style={{
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        padding: '14px 16px',
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 16,
        color: 'var(--text-primary)',
      }}
    >
      <span style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ color: 'var(--text-secondary)', display: 'flex' }}>
          {dark ? <MoonIcon /> : <SunIcon />}
        </span>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 16 }}>
          Тёмная тема
        </span>
      </span>

      {/* Простой индикатор состояния вместо отдельного графического
          свитча — на touch-экране весь ряд и так кликабелен целиком,
          второй интерактивный элемент внутри кнопки был бы лишним. */}
      <span
        style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 600,
          fontSize: 13,
          color: dark ? 'var(--accent)' : 'var(--text-secondary)',
        }}
      >
        {dark ? 'Вкл' : 'Выкл'}
      </span>
    </button>
  );
}
