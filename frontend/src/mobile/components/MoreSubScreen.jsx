/**
 * MoreSubScreen.jsx — общая шапка «‹ Назад · Заголовок» для под-разделов
 * экрана «Ещё» (История, Друзья, Уведомления, Настройки). Своего роутера в
 * приложении нет — переключение живёт локальным состоянием в MoreScreen.jsx,
 * это просто общая рамка вокруг содержимого каждого раздела.
 */

import React from 'react';

export default function MoreSubScreen({ title, onBack, children }) {
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px 8px', flexShrink: 0 }}>
        <button
          type="button"
          onClick={onBack}
          aria-label="Назад"
          style={{ background: 'transparent', border: 'none', padding: 6, marginLeft: -6, color: 'var(--text-primary)', display: 'flex' }}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
          {title}
        </h1>
      </header>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 16px 24px' }}>
        {children}
      </div>
    </div>
  );
}
