/**
 * TabBar.jsx — нижняя навигация, три вкладки.
 *
 * Кнопки, а не <Link>: клик переключает вкладку через navigate(path,
 * {replace:true}) вместо push. Табы — не стек «вперёд/назад», а плоский
 * переключатель режима экрана; push плодил бы историю MemoryRouter на
 * каждое переключение без единого сценария, где это «назад» кому-то нужно.
 *
 * Экраны при этом не размонтируются (см. TabShell.jsx) — активная вкладка
 * здесь только подсвечивается, а не решает, что рендерить.
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';

// SVG, stroke=currentColor, 20×20 — правило DESIGN_SYSTEM.md §8: не
// иконочные шрифты, только inline SVG.
const ICONS = {
  feed: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <path d="M3 5.5h14M3 10h14M3 14.5h9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  ),
  chart: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="7.2" stroke="currentColor" strokeWidth="1.7" />
      <path d="M10 2.8V10l5.2 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  more: (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="4.5" cy="10" r="1.6" fill="currentColor" />
      <circle cx="10" cy="10" r="1.6" fill="currentColor" />
      <circle cx="15.5" cy="10" r="1.6" fill="currentColor" />
    </svg>
  ),
};

const TABS = [
  { key: 'feed', path: '/app/feed', label: 'Лента' },
  { key: 'chart', path: '/app/chart', label: 'Карта' },
  { key: 'more', path: '/app/more', label: 'Ещё' },
];

export default function TabBar({ active }) {
  const navigate = useNavigate();

  return (
    <nav
      className="mobile-tabbar"
      style={{
        display: 'flex',
        background: 'var(--bg-card)',
        borderTop: '1px solid var(--border)',
      }}
    >
      {TABS.map((tab) => {
        const isActive = tab.key === active;
        const color = isActive ? 'var(--accent)' : 'var(--text-secondary)';
        return (
          <button
            key={tab.key}
            type="button"
            onClick={() => navigate(tab.path, { replace: true })}
            aria-current={isActive ? 'page' : undefined}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 4,
              padding: '10px 0 8px',
              background: 'transparent',
              border: 'none',
              color,
            }}
          >
            {ICONS[tab.key]}
            <span style={{ fontSize: 11, fontFamily: 'var(--font-display)', fontWeight: 600 }}>
              {tab.label}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
