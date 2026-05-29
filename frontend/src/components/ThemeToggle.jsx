/**
 * ThemeToggle.jsx — F3
 *
 * Переключатель dark/light темы.
 * Сохраняет выбор в localStorage под ключом astrea_theme.
 *
 * Применяет класс 'dark' на <html> для Tailwind dark-mode.
 *
 * Использование:
 *   import ThemeToggle from './components/ThemeToggle';
 *   <ThemeToggle />
 */

import React, { useState, useEffect } from 'react';

const STORAGE_KEY = 'astrea_theme';

export function useTheme() {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return stored === 'dark';
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
  });

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light');
  }, [dark]);

  const toggle = () => setDark(d => !d);
  return { dark, toggle };
}

export default function ThemeToggle({ dark, onToggle }) {
  return (
    <button
      onClick={onToggle}
      title={dark ? 'Светлая тема' : 'Тёмная тема'}
      aria-label={dark ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        width: 36, height: 36, borderRadius: 10,
        border: '1px solid rgba(112,96,160,0.2)',
        background: dark ? 'rgba(30,26,46,0.8)' : 'rgba(244,240,250,0.8)',
        cursor: 'pointer',
        fontSize: 18,
        transition: 'all 0.2s',
        flexShrink: 0,
      }}
    >
      {dark ? '☀️' : '🌙'}
    </button>
  );
}
