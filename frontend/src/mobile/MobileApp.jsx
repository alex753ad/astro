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

import React from 'react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '../hooks/useAuth.jsx';
import useAuth from '../hooks/useAuth.jsx';
import { ThemeProvider } from './useTheme.jsx';
import LoginScreen from './screens/LoginScreen';
import RegisterScreen from './screens/RegisterScreen';
import WelcomeScreen from './screens/WelcomeScreen';
import TabShell from './components/TabShell';
import { WELCOME_KEY, isSeen } from './lib/onboardingFlags';
import './mobile.css';

function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? children : <Navigate to="/login" replace />;
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
  const initial = isAuthenticated
    ? '/app/feed'
    : (isSeen(WELCOME_KEY) ? '/login' : '/onboarding');

  return (
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/onboarding" element={<RequireGuest><WelcomeScreen /></RequireGuest>} />
        <Route path="/login" element={<RequireGuest><LoginScreen /></RequireGuest>} />
        <Route path="/register" element={<RequireGuest><RegisterScreen /></RequireGuest>} />
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
