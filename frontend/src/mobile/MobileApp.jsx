/**
 * MobileApp.jsx — корень Capacitor-приложения.
 *
 * Навигация — react-router с MemoryRouter, не BrowserRouter (тот в вебе,
 * App.jsx). Страница грузится не по http(s), а из локальных файлов APK
 * (webview открывает index.html с https://localhost или file:// в
 * зависимости от androidScheme) — BrowserRouter опирается на настоящий
 * window.location.pathname и History API поверх реального URL страницы;
 * MemoryRouter держит историю в памяти JS и с адресом загрузки не связан
 * вовсе, поэтому не ломается на этой почве.
 *
 * Маршрут /onboarding — приветствие, три экрана до входа (SPEC_ONBOARDING.md).
 * Показывается один раз и только не вошедшему: RequireGuest на самом
 * маршруте плюс порядок условий в `initial` ниже.
 *
 * /register остаётся заглушкой. Переключение между «не вошёл»/«вошёл»
 * держится на useAuth().isAuthenticated и работает в обе стороны реактивно:
 * не только логин уводит на /app/feed, но и потеря сессии (например,
 * неудачное обновление токена при возврате из фона) уводит обратно на
 * /login — без этого пользователь застрял бы на пустом таб-баре без сети.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '../hooks/useAuth.jsx';
import useAuth from '../hooks/useAuth.jsx';
import { resetSubscription } from './lib/tierSource';
import { offlineCache } from './lib/offlineCache';
import { ThemeProvider } from './useTheme.jsx';
import LoginScreen from './screens/LoginScreen';
import RegisterScreen from './screens/RegisterScreen';
import WelcomeScreen from './screens/WelcomeScreen';
import TabShell from './components/TabShell';
import GuestCreateScreen from './screens/GuestCreateScreen';
import { clearGuestChart, getGuestChart } from './lib/guestChart';
import { claimGuestChart } from './lib/chartApi';
import { errorText } from './lib/netError';
import { WELCOME_KEY, isSeen } from './lib/onboardingFlags';
import './mobile.css';

/**
 * Карта гостя → аккаунт, сразу после входа или регистрации, ДО того как
 * вкладки начнут грузиться: иначе лента успела бы спросить список карт и
 * показать «нет ни одной карты».
 *
 * ⚠️ Отказ по существу (4xx: карта просрочена, слоты тарифа заняты) — текст
 * и «Продолжить», карта гостя забывается: повтор дал бы тот же отказ. Сбой
 * сети или сервера — «Повторить»; «Продолжить» тогда карту НЕ забывает,
 * привязка повторится при следующем запуске. Дубля не создаём ни в каком
 * случае (backend/CLAUDE.md, «Гость приложения»).
 */
function ClaimGate({ children }) {
  const [state, setState] = useState(() => (getGuestChart() ? 'claiming' : 'done'));
  const [error, setError] = useState('');

  const run = useCallback(async () => {
    const guest = getGuestChart();
    if (!guest) { setState('done'); return; }
    setState('claiming');
    try {
      await claimGuestChart(guest.id);
      clearGuestChart();
      setState('done');
    } catch (err) {
      const final = err?.status >= 400 && err?.status < 500 && err?.status !== 401;
      setError(final ? `Карту гостя сохранить не получилось: ${err.message}` : errorText(err, 'Не удалось сохранить карту в аккаунт.'));
      setState(final ? 'final' : 'retry');
    }
  }, []);

  useEffect(() => { if (state === 'claiming') run(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (state === 'done') return children;
  const box = { height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24, textAlign: 'center' };
  if (state === 'claiming') {
    return <div style={box}><p style={{ margin: 0, color: 'var(--text-secondary)' }}>Сохраняем карту в аккаунт…</p></div>;
  }
  return (
    <div style={box}>
      <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-primary)' }}>{error}</p>
      {state === 'retry' && <button type="button" className="mobile-btn-primary" onClick={run}>Повторить</button>}
      <button
        type="button"
        className="mobile-link"
        onClick={() => { if (state === 'final') clearGuestChart(); setState('done'); }}
      >
        Продолжить
      </button>
    </div>
  );
}

function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth();

  // ⚠️ Общий кэш тарифа (mobile/lib/tierSource.js) чистится ровно здесь, при
  // потере сессии, и одним местом на всё приложение. Оставить его значило бы
  // показать следующему вошедшему тариф предыдущего — а он живёт в памяти
  // процесса и переживает разлогин. Разлогин ловим по признаку, а не по
  // вызову logout(): выходов несколько (кнопка на трёх экранах, отказ
  // аутентификации), и любой пропущенный дал бы ровно тот же дефект.
  //
  // Там же стирается сохранённое для показа без сети (offlineCache.js): оно
  // и так помечено владельцем, но на общем телефоне чужое не должно лежать
  // на диске вовсе.
  useEffect(() => {
    if (!isAuthenticated) {
      resetSubscription();
      offlineCache.clearAll();
    }
  }, [isAuthenticated]);

  if (isAuthenticated) return <ClaimGate>{children}</ClaimGate>;
  // Гость с картой видит ленту и карту без входа (lib/guestChart.js).
  if (getGuestChart()) return children;
  return <Navigate to="/login" replace />;
}

function RequireGuest({ children }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <Navigate to="/app/feed" replace /> : children;
}

function MobileRouter() {
  const { isAuthenticated } = useAuth();

  // isAuthenticated на первом рендере уже верен: useAuth читает
  // accessToken/user из localStorage синхронно при инициализации состояния
  // (loadStored() в useAuthInternal), без ожидания эффектов. initialEntries
  // применяется MemoryRouter только один раз при монтировании — этого
  // достаточно, чтобы не мелькнуть экраном входа, если сессия уже на месте.
  //
  // Приветствие встаёт третьим вариантом и читается ТОЖЕ синхронно, здесь
  // же: асинхронная проверка флага дала бы кадр с экраном входа, который
  // тут же подменился бы приветствием (SPEC_ONBOARDING.md §2).
  // Вошедшему приветствие не показывается вовсе — решение владельца
  // 07.09.2026; это обеспечивают и порядок условий здесь, и RequireGuest
  // на самом маршруте.
  const initial = (isAuthenticated || getGuestChart())
    ? '/app/feed'
    : (isSeen(WELCOME_KEY) ? '/login' : '/onboarding');

  return (
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/onboarding" element={<RequireGuest><WelcomeScreen /></RequireGuest>} />
        <Route path="/login" element={<RequireGuest><LoginScreen /></RequireGuest>} />
        <Route path="/register" element={<RequireGuest><RegisterScreen /></RequireGuest>} />
        <Route path="/guest/new" element={<RequireGuest><GuestCreateScreen /></RequireGuest>} />
        <Route path="/app/*" element={<RequireAuth><TabShell /></RequireAuth>} />
        <Route path="*" element={<Navigate to={initial} replace />} />
      </Routes>
    </MemoryRouter>
  );
}

export default function MobileApp() {
  return (
    // ThemeProvider снаружи: класс .dark на <html> нужен всему дереву сразу,
    // включая экран входа, а не только вкладке «Ещё», где живёт переключатель.
    <ThemeProvider>
      <AuthProvider>
        <MobileRouter />
      </AuthProvider>
    </ThemeProvider>
  );
}
