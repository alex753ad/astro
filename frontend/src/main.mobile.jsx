/**
 * main.mobile.jsx — точка входа Capacitor-сборки.
 *
 * До этого коммита здесь жил временный экран-проверка: версия сборки +
 * запрос к /calendar/lunar без авторизации, доказывавший, что сеть и CORS
 * работают из webview. Это было единственной функциональностью первой
 * мобильной сборки — намеренно, отдельным этапом задачи (см. git-историю
 * этого файла). Теперь цепочка сборки и сеть уже доказаны, и этот файл
 * монтирует настоящий каркас приложения — src/mobile/MobileApp.jsx.
 *
 * Заглушку проверки обновления токена (AuthProbe) тоже убрали: раньше она
 * была нужна, потому что взять refresh было неоткуда — экрана входа не
 * существовало. Теперь эту работу делает сам вход: LoginScreen кладёт
 * refresh в нативное хранилище через useAuth(), а обновление токена
 * проверяется тем, что вышедшее из фона приложение не разлогинивает — это
 * ровно то, что useAuth.jsx уже делает и для веба, без отдельного кода здесь.
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import * as Sentry from '@sentry/react';
import MobileApp from './mobile/MobileApp';
import { scrubEvent } from './lib/sentryScrub';
import { isNetworkNoise } from './mobile/lib/netError';

// Только JS-ошибки: @sentry/capacitor (падения нативной части) не взят —
// нативный плагин, решение владельца 24.09.2026. Без VITE_SENTRY_DSN в
// .env.mobile условие сворачивается при сборке, и SDK в APK не попадает.
// Фильтр персональных данных — общий с вебом (lib/sentryScrub.js).
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: 'android',
    release: __APP_RELEASE__,
    tracesSampleRate: 0,
    sendDefaultPii: false,
    // Нет сети и таймаут — не поломка, а шум, который съел бы лимит
    // (решение владельца 24.09.2026). 5xx остаётся: его видно и на бэкенде,
    // но с устройства — с контекстом экрана.
    beforeSend: (event, hint) => (isNetworkNoise(event, hint) ? null : scrubEvent(event)),
  });
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <MobileApp />
  </React.StrictMode>
);
