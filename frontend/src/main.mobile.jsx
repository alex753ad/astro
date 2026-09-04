/**
 * main.mobile.jsx — точка входа Capacitor-сборки.
 *
 * Экранов приложения здесь нет и не должно быть: задача этого файла —
 * доказать, что цепочка «vite → dist-mobile → cap sync → APK → webview»
 * собрана правильно и что из webview работает сеть до боевого API.
 *
 * Поэтому на экране ровно две вещи: версия сборки и результат одного запроса
 * к публичной ручке. Ручка выбрана без авторизации (/calendar/lunar) — иначе
 * проверка сети смешалась бы с проверкой логина, и по красному экрану было бы
 * не понять, что именно не работает.
 *
 * ВАЖНО: API_BASE импортируется из общего src/config.js, а не задаётся здесь
 * константой. Смысл именно в этом — сборка идёт с `--mode mobile`, Vite
 * подхватывает .env.mobile с VITE_API_URL, и config.js отдаёт абсолютный
 * https://www.aristeatime.ru/api/v1 вместо относительного /api/v1. Если
 * прописать URL прямо тут, проверка станет бессмысленной: она подтвердит
 * работу этого файла, а не работу настоящего пути к API.
 */

import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { API_BASE } from './config';

// Подставляется на этапе сборки из package.json (define в vite.config.mobile.js).
const VERSION = __APP_VERSION__;

// Токены из DESIGN_SYSTEM.md, тёмная тема (основная).
const S = {
  page: {
    minHeight: '100vh',
    margin: 0,
    padding: '24px',
    boxSizing: 'border-box',
    background: '#0F0A1A',
    color: '#E2DFF0',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    justifyContent: 'center',
  },
  version: { fontSize: '20px', fontWeight: 600, color: '#E2DFF0' },
  muted: { fontSize: '13px', color: '#9B97B0', wordBreak: 'break-all' },
  card: {
    background: '#1A1230',
    border: '1px solid #2A2245',
    borderRadius: '12px',
    padding: '16px',
    fontSize: '14px',
    lineHeight: 1.5,
  },
  ok: { color: '#8B5CF6', fontWeight: 600 },
  err: { color: '#F87171', fontWeight: 600 },
};

function App() {
  const [state, setState] = useState({ status: 'loading' });

  useEffect(() => {
    const now = new Date();
    const url = `${API_BASE}/calendar/lunar?year=${now.getFullYear()}&month=${now.getMonth() + 1}`;

    fetch(url)
      .then(async (resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return resp.json();
      })
      .then((data) => {
        // Форму ответа намеренно не разбираем: нужен факт, что тело дошло и
        // прочиталось. Любая привязка к схеме сделала бы проверку сети
        // хрупкой к изменениям бэкенда.
        const days = Array.isArray(data?.days) ? data.days.length : null;
        setState({ status: 'ok', days, keys: Object.keys(data || {}) });
      })
      // Сюда же приходит блокировка по CORS: браузер отдаёт TypeError без
      // статуса и без текста причины. Поэтому рядом печатается URL — по нему
      // сразу видно, ушёл запрос на боевой домен или на относительный путь.
      .catch((err) => setState({ status: 'error', message: String(err?.message || err) }));
  }, []);

  return (
    <div style={S.page}>
      <div style={S.version}>Aristea Timeline · v{VERSION}</div>
      <div style={S.muted}>API: {API_BASE}</div>

      <div style={S.card}>
        {state.status === 'loading' && <span>Запрос к лунному календарю…</span>}

        {state.status === 'ok' && (
          <>
            <div style={S.ok}>Сеть и CORS работают</div>
            <div style={S.muted}>
              дней в ответе: {state.days ?? '—'}
              <br />
              поля: {state.keys.join(', ') || '—'}
            </div>
          </>
        )}

        {state.status === 'error' && (
          <>
            <div style={S.err}>Запрос не прошёл</div>
            <div style={S.muted}>{state.message}</div>
          </>
        )}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
