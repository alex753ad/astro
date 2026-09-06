/**
 * MoreMenuList.jsx — список пунктов меню экрана «Ещё» (SPEC_MORE_SCREEN.md
 * §6). Значки — те же контуры, что в прототипе `aristea-mobile.html`
 * (`.mlist svg`).
 *
 * «Скачать мои данные» пунктом меню здесь НЕТ — решение, не пропуск
 * (SPEC_MORE_SCREEN.md §6.2, там же причина). Вместо него ниже отдельная
 * строка-ссылка на веб-кабинет.
 */

import React from 'react';
import { openInBrowser } from '../lib/openInBrowser';

const ITEMS = [
  {
    id: 'history',
    label: 'История разборов',
    icon: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v4l3 2" />
      </>
    ),
  },
  {
    id: 'referral',
    label: 'Друзья',
    icon: (
      <>
        <path d="M16 20v-2a4 4 0 0 0-8 0v2" />
        <circle cx="12" cy="8" r="3.5" />
      </>
    ),
  },
  {
    id: 'notifications',
    label: 'Уведомления',
    icon: (
      <>
        <path d="M18 15V10a6 6 0 1 0-12 0v5l-2 3h16z" />
        <path d="M10 21h4" />
      </>
    ),
  },
  {
    id: 'settings',
    label: 'Настройки',
    icon: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M18 6l-2 2M6 18l2-2M18 18l-2-2" />
      </>
    ),
  },
];

function MenuRow({ item, onOpen }) {
  return (
    <li style={{ borderBottom: '1px solid var(--border)' }}>
      <button
        type="button"
        onClick={() => onOpen(item.id)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 13,
          padding: '15px 0',
          background: 'transparent',
          border: 'none',
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-body)',
          fontSize: 15,
          textAlign: 'left',
        }}
      >
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          {item.icon}
        </svg>
        <span style={{ flex: 1 }}>{item.label}</span>
        <span aria-hidden="true" style={{ color: 'var(--text-secondary)', fontSize: 16 }}>›</span>
      </button>
    </li>
  );
}

export default function MoreMenuList({ onOpen }) {
  return (
    <section>
      <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
        {ITEMS.map((item) => (
          <MenuRow key={item.id} item={item} onOpen={onOpen} />
        ))}
      </ul>

      <button
        type="button"
        onClick={() => openInBrowser('https://aristeatime.ru/profile')}
        style={{
          width: '100%',
          textAlign: 'left',
          background: 'transparent',
          border: 'none',
          padding: '13px 0 4px',
          fontFamily: 'var(--font-body)',
          fontSize: 13,
          color: 'var(--text-secondary)',
        }}
      >
        Выгрузка ваших данных доступна в личном кабинете на сайте →
      </button>
    </section>
  );
}
