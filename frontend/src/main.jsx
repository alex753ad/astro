import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import * as Sentry from '@sentry/react';
import App from './App';
import { initMetrika } from './analytics';
import './index.css';

// Без VITE_SENTRY_DSN SDK не инициализируется — работает как раньше.
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: 'production',
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
  });
}

// Регистрация service worker. Раньше это был инлайновый <script> в index.html —
// он не переживает CSP с script-src 'self' (без 'unsafe-inline'), поэтому код
// переехал в бандл.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(console.error);
  });
}

// Счётчик посещаемости. Без VITE_YANDEX_METRIKA_ID не грузится вообще —
// переменная задаётся только в /opt/astro/frontend.env на сервере, где и
// собирается боевой фронтенд. Подробности и состав отключённых опций —
// в analytics.js.
initMetrika();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
