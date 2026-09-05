/**
 * MoreScreen.jsx — вкладка «Ещё».
 *
 * Больше не чистая заглушка: здесь живёт переключатель темы — ему тут самое
 * место, других настроек интерфейса в приложении пока нет. Заголовок сверху,
 * а не по центру, как у Feed/Chart (ScreenStub.jsx) — список настроек читают
 * сверху вниз, а не ищут глазами в середине экрана.
 */

import React from 'react';
import ThemeToggle from '../components/ThemeToggle';

export default function MoreScreen() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '20px 20px 0' }}>
      <h1
        style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 700,
          fontSize: 22,
          color: 'var(--text-primary)',
          margin: '0 0 20px',
        }}
      >
        Ещё
      </h1>

      <ThemeToggle />
    </div>
  );
}
