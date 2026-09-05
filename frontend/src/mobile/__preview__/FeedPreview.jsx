/**
 * ВРЕМЕННЫЙ стенд для приёмки экрана «Лента». Удаляется после проверки,
 * в коммит не идёт.
 *
 * Зачем: CORS боевого API не пускает dev-origin (http://localhost:5173 —
 * проверено, ответ без access-control-allow-origin), поэтому браузер не
 * может сходить в ручку напрямую. Стенд подменяет ТОЛЬКО window.fetch,
 * отдавая настоящий боевой ответ (723 события, окно 2026-08-05..12-31,
 * снят с прода сегодня) — сам FeedScreen и все его компоненты работают
 * без единой правки, включая состояния, группировку и прокрутку к сегодня.
 */

import React from 'react';
import { createRoot } from 'react-dom/client';
import fixture from './fixture.json';
import { ThemeProvider } from '../useTheme.jsx';
import FeedScreen from '../screens/FeedScreen';
import '../mobile.css';

const json = (body) => Promise.resolve({
  ok: true,
  status: 200,
  json: () => Promise.resolve(body),
});

window.fetch = (url) => {
  const u = String(url);
  if (u.includes('/profile/charts')) return json(fixture.charts);
  if (u.includes('/feed')) return json(fixture.feed);
  return Promise.reject(new Error(`стенд не знает ручки ${u}`));
};

// Токен нужен только чтобы authFetch не ушёл в ветку обновления.
localStorage.setItem('astro_access_token', 'preview');

// Скроллер живёт в TabShell — здесь его роль играет эта обёртка, иначе
// sticky и scrollIntoView проверялись бы в других условиях, чем в приложении.
function PreviewShell() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
        <div style={{ display: 'flex', flex: 1, flexDirection: 'column' }}>
          <FeedScreen />
        </div>
      </div>
    </div>
  );
}

const t0 = performance.now();
createRoot(document.getElementById('root')).render(
  <ThemeProvider><PreviewShell /></ThemeProvider>,
);
requestAnimationFrame(() => {
  window.__renderMs = Math.round(performance.now() - t0);
  console.log('render ms:', window.__renderMs, 'cards:', document.querySelectorAll('article').length);
});
