import React, { useState, useEffect, useRef } from 'react';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { AuthProvider } from './hooks/useAuth.jsx';
import useAuth from './hooks/useAuth.jsx';
import { API_BASE } from './config';
import HomePage from './pages/HomePage';
import LandingPage from './pages/LandingPage';
import OrionPage from './pages/OrionPage';
import ChartPage from './pages/ChartPage';
import PlannerPage from './pages/PlannerPage';
import SolarReturnPage from './pages/SolarReturnPage';
import SynastryPage from './pages/SynastryPage';
import RelocationPage from './pages/RelocationPage';
import ProfilePage from './pages/ProfilePage';
import AuthModal from './components/AuthModal';
import LunarCalendarPage from './pages/LunarCalendarPage';
import SharePage from './pages/SharePage';
import IntakePage from './pages/IntakePage';
import PortalPage from './pages/PortalPage';
import GiftPage from './pages/GiftPage';
import ZodiacPage from './pages/ZodiacPage';
import CRMPage from './pages/CRMPage';
import AdminPage from './pages/AdminPage';
import PrivacyPage from './pages/PrivacyPage';
import TermsPage from './pages/TermsPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import PilotClaim from './components/PilotClaim';
import ExitSurveyModal from './components/ExitSurveyModal';
import FeedbackButton from './components/FeedbackButton';
import { ToastProvider } from './components/Toast';
import ThemeToggle from './components/ThemeToggle';
import NebulaBackground from './components/NebulaBackground';

// ─── OG meta updater ─────────────────────────────────────────────────────────

const ZODIAC_SIGNS = {
  aries: 'Овен', taurus: 'Телец', gemini: 'Близнецы', cancer: 'Рак',
  leo: 'Лев', virgo: 'Дева', libra: 'Весы', scorpio: 'Скорпион',
  sagittarius: 'Стрелец', capricorn: 'Козерог', aquarius: 'Водолей', pisces: 'Рыбы',
};

function setMeta(property, content) {
  let el = document.querySelector(`meta[property="${property}"]`);
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute('property', property);
    document.head.appendChild(el);
  }
  el.setAttribute('content', content);
}

function updateOG({ title, description, url }) {
  document.title = title;
  setMeta('og:title', title);
  setMeta('og:description', description);
  setMeta('og:url', url || window.location.href);
}

function useOGMeta() {
  const location = useLocation();

  useEffect(() => {
    const path = location.pathname;
    const base = 'https://astreatime.ru';

    if (path === '/' || path === '/home') {
      updateOG({
        title: 'Astrea Timeline — Натальные карты и AI-астрология',
        description: 'Постройте натальную карту, получите AI-интерпретацию транзитов и персональный астро-планер.',
        url: `${base}${path}`,
      });
    } else if (path.startsWith('/zodiac/')) {
      const sign = path.split('/zodiac/')[1]?.toLowerCase();
      const signRu = ZODIAC_SIGNS[sign] || sign;
      updateOG({
        title: `${signRu} — характеристика знака зодиака | Astrea`,
        description: `Подробная характеристика знака ${signRu}: личность, карьера, отношения. AI-астрология на Astrea Timeline.`,
        url: `${base}${path}`,
      });
    } else if (path === '/lunar' || path.startsWith('/calendar/lunar')) {
      updateOG({
        title: 'Лунный календарь 2026 | Astrea Timeline',
        description: 'Фазы Луны, знак Луны на каждый день, благоприятные дни. Персональный лунный календарь.',
        url: `${base}${path}`,
      });
    }
    // Авторизованная зона — OG не обновляем
  }, [location.pathname]);
}

// ─── Dark mode ────────────────────────────────────────────────────────────────

function useDarkMode() {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem('astrea_theme');
    if (stored) return stored === 'dark';
    return false;
  });
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('astrea_theme', dark ? 'dark' : 'light');
  }, [dark]);
  return [dark, () => setDark(d => !d)];
}

// ─── Header ───────────────────────────────────────────────────────────────────

function Header({ onShowAuth, dark, toggleDark }) {
  const { user, logout, authFetch } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [calcOpen, setCalcOpen] = useState(false);
  const calcRef = useRef(null);
  const location = useLocation();

  // Мгновенный первый рендер на уже знакомом устройстве — снимок один раз
  // при монтировании, не источник правды (см. useEffect ниже). Раньше это
  // localStorage.getItem был ЕДИНСТВЕННЫМ источником навигации: на новом
  // устройстве/браузере, где карту ещё не открывали, шапка оставалась
  // пустой, хотя карты у пользователя есть на сервере.
  const [cachedChartId]   = useState(() => localStorage.getItem('astro_last_chart_id'));
  const [cachedChartName] = useState(() => localStorage.getItem('astro_last_chart_name'));

  const [serverChartId,   setServerChartId]   = useState(null);
  const [serverChartName, setServerChartName] = useState(null);
  const [chartsChecked,   setChartsChecked]   = useState(false); // серверный запрос завершился
  const [hasAnyChart,     setHasAnyChart]     = useState(true);  // оптимистично до проверки — не мигать CTA раньше времени

  // Список карт — с сервера аккаунта, а не только из кэша этого устройства.
  // Сбрасывается и перезапрашивается при каждой смене пользователя (логаут →
  // логин другим аккаунтом на этом же устройстве не должен унаследовать
  // чужой результат проверки).
  useEffect(() => {
    setChartsChecked(false);
    setServerChartId(null);
    setServerChartName(null);
    setHasAnyChart(true);
    if (!user) return;
    let cancelled = false;
    authFetch(`${API_BASE}/profile/charts`)
      .then(d => {
        if (cancelled) return;
        const charts = d.charts || [];
        const chosen = charts.find(c => c.id === d.primary_chart_id) || charts[0] || null;
        if (chosen) {
          setServerChartId(chosen.id);
          if (chosen.birth_place) setServerChartName(chosen.birth_place);
        } else {
          setHasAnyChart(false);
        }
        // Ставим только при успешном ответе — иначе при сетевой ошибке
        // (offline, таймаут) навигация ниже (lastChartId) откатывалась бы на
        // null вместо кэша из localStorage, и меню/гамбургер пропадали бы
        // при рабочей сессии.
        setChartsChecked(true);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [user?.id, authFetch]);

  // Карта, которую пользователь смотрит прямо сейчас — самый свежий сигнал:
  // после создания новой карты ChartPage грузится по её id раньше, чем успел
  // бы перезапроситься список выше, поэтому навигация обновляется без
  // перезагрузки страницы.
  const urlChartMatch = location.pathname.match(/^\/chart\/([^/]+)$/);
  const urlChartId = urlChartMatch && urlChartMatch[1] !== 'anonymous' ? urlChartMatch[1] : null;

  const lastChartId = urlChartId || serverChartId || (!chartsChecked ? cachedChartId : null);
  const lastChartName = serverChartName || (!chartsChecked ? cachedChartName : null);
  const navChartLabel = lastChartName || (user?.email?.split('@')[0]) || 'Карта';
  // Залогинен, сервер подтвердил отсутствие карт вообще — не пустая шапка,
  // а понятный путь дальше, а не три вкладки в никуда.
  const showCreateChartCta = Boolean(user) && chartsChecked && !hasAnyChart && !lastChartId;

  // Дропдаун «Расчёты» закрывается по клику вне него.
  useEffect(() => {
    function handler(e) {
      if (calcRef.current && !calcRef.current.contains(e.target)) setCalcOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const navLink = (to) => {
    const isActive = location.pathname === to || location.pathname.startsWith(to + '/');
    return isActive
      ? "px-3 py-1.5 rounded-lg text-brand-accent bg-brand-accent/10 border border-brand-border transition-colors duration-200 text-sm font-medium"
      : "px-3 py-1.5 rounded-lg text-brand-muted hover:text-brand-text hover:bg-brand-accent/10 transition-colors duration-200 text-sm";
  };

  return (
    <header className="sticky top-0 z-50 bg-brand-card/80 backdrop-blur-md border-b border-brand-border">
      <div className="max-w-6xl mx-auto px-4 py-3">

        {/* Логотип + слоган — верхняя строка фиксированной высоты, без переноса */}
        <Link to="/" className="flex items-center gap-2 group h-8 overflow-hidden">
          <img src="/logo_120x120.png" alt="Astrea Timeline" className="w-8 h-8 rounded-full shrink-0" />
          <span className="font-display text-lg font-bold text-brand-text group-hover:text-brand-accent transition-colors duration-200 whitespace-nowrap">
            Astrea Timeline
          </span>
          <span className="hidden sm:block text-sm text-brand-muted border-l border-brand-border pl-3 ml-1 min-w-0 truncate">
            — плавное выравнивание жизни по ритму космических циклов
          </span>
        </Link>

        {/* Навигация — отдельная строка под логотипом */}
        <nav className="flex items-center gap-1 text-sm mt-2">

          {/* Desktop links */}
          <div className="hidden md:flex items-center gap-1">
            {user && lastChartId && (
              <>
                <Link to={`/chart/${lastChartId}`} className={navLink(`/chart/${lastChartId}`)}>
                  Натальная карта
                </Link>
                <Link to={`/planner/${lastChartId}`} className={navLink(`/planner/${lastChartId}`)}>
                  Timeline Планер
                </Link>
                <Link to={`/lunar`} className={navLink('/lunar')}>
                  Лунный календарь
                </Link>
              </>
            )}
            {/* «Скоро» — анонс будущих функций, видно всем; переход внутрь работает только у админа */}
            {lastChartId && (
              <div className="relative" ref={calcRef}>
                <button
                  onClick={() => setCalcOpen(o => !o)}
                  className="px-3 py-1.5 rounded-lg text-brand-muted hover:text-brand-text hover:bg-brand-accent/10 transition-colors duration-200 text-sm"
                  aria-haspopup="menu"
                  aria-expanded={calcOpen}
                >
                  Скоро ▾
                </button>
                {calcOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 mt-1 min-w-[180px] rounded-lg border border-brand-border bg-brand-card/95 backdrop-blur-md shadow-lg py-1 z-50"
                  >
                    {user?.is_admin ? (
                      <>
                        <Link to={`/solar-return/${lastChartId}`} onClick={() => setCalcOpen(false)}
                          className="block px-4 py-2 text-sm text-brand-muted hover:text-brand-text hover:bg-brand-accent/10 transition-colors">
                          Соляр
                        </Link>
                        <Link to={`/synastry/${lastChartId}`} onClick={() => setCalcOpen(false)}
                          className="block px-4 py-2 text-sm text-brand-muted hover:text-brand-text hover:bg-brand-accent/10 transition-colors">
                          Синастрия
                        </Link>
                        <Link to={`/relocation/${lastChartId}`} onClick={() => setCalcOpen(false)}
                          className="block px-4 py-2 text-sm text-brand-muted hover:text-brand-text hover:bg-brand-accent/10 transition-colors">
                          Релокация
                        </Link>
                      </>
                    ) : (
                      <>
                        <div className="px-4 py-2 text-sm text-brand-muted cursor-default">Соляр</div>
                        <div className="px-4 py-2 text-sm text-brand-muted cursor-default">Синастрия</div>
                        <div className="px-4 py-2 text-sm text-brand-muted cursor-default">Релокация</div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
            {user?.tier === 'premium' && (
              <Link to="/dashboard/clients" className={navLink('/dashboard/clients')}>
                Кабинет астролога
              </Link>
            )}
          </div>

          {/* Залогинен, но карт вообще нет (подтверждено сервером) — понятный
              вход вместо пустой шапки. Видно на всех размерах экрана, не
              только на десктопе — на мобильном хамбургер и так скрыт без карты. */}
          {showCreateChartCta && (
            <Link to="/home" className={navLink('/home')}>
              Создать карту
            </Link>
          )}

          {/* Profile / Auth — всегда видно */}
          {user ? (
            <>
              <Link
                to="/profile"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                           text-white font-medium transition-colors duration-200"
                style={{ background: 'var(--accent)' }}
              >
                <span>{user.name || user.email?.split('@')[0]}</span>
              </Link>
              <button
                onClick={logout}
                className="hidden md:block px-4 py-1.5 rounded-lg text-sm font-medium text-brand-muted border border-brand-border hover:border-brand-accent hover:text-brand-text transition-colors duration-200"
              >
                Выйти
              </button>
            </>
          ) : (
            <button
              onClick={() => onShowAuth()}
              className="btn-primary !h-auto px-5 py-1.5 text-sm"
            >
              Войти
            </button>
          )}

          <ThemeToggle dark={dark} onToggle={toggleDark} />

          {/* Hamburger — только мобильный, для всех авторизованных (не зависит
              от lastChartId: иначе временная ошибка /profile/charts или
              отсутствие карт у нового пользователя гасили доступ к меню
              совсем, включая профиль/выход). */}
          {user && (
            <button
              onClick={() => setMenuOpen(m => !m)}
              className="md:hidden flex flex-col justify-center gap-1 p-2 rounded-lg text-brand-muted hover:bg-brand-accent/10 transition-colors"
              aria-label="Меню"
            >
              <span className={`block w-5 h-0.5 bg-current transition-all duration-200 ${menuOpen ? 'rotate-45 translate-y-1.5' : ''}`} />
              <span className={`block w-5 h-0.5 bg-current transition-all duration-200 ${menuOpen ? 'opacity-0' : ''}`} />
              <span className={`block w-5 h-0.5 bg-current transition-all duration-200 ${menuOpen ? '-rotate-45 -translate-y-1.5' : ''}`} />
            </button>
          )}
        </nav>
      </div>

      {/* Mobile dropdown — открывается для любого авторизованного, не только
          с известной картой (см. комментарий у гамбургера выше). */}
      {menuOpen && user && (
        <div className="md:hidden border-t border-brand-border bg-brand-card/95 backdrop-blur-md">
          <div className="max-w-6xl mx-auto px-4 py-2 flex flex-col gap-1">
            {lastChartId && (
              <>
                <Link to={`/chart/${lastChartId}`} className={navLink(`/chart/${lastChartId}`)} onClick={() => setMenuOpen(false)}>
                  Натальная карта
                </Link>
                <Link to={`/planner/${lastChartId}`} className={navLink(`/planner/${lastChartId}`)} onClick={() => setMenuOpen(false)}>
                  Timeline Планер
                </Link>
              </>
            )}
            <Link to="/lunar" className={navLink('/lunar')} onClick={() => setMenuOpen(false)}>
              Лунный календарь
            </Link>
            {user?.tier === 'premium' && (
              <Link to="/dashboard/clients" className={navLink('/dashboard/clients')} onClick={() => setMenuOpen(false)}>
                Кабинет астролога
              </Link>
            )}
            {/* «Скоро» — анонс будущих функций, видно всем; переход внутрь работает только у админа */}
            {lastChartId && (
              <>
                <div className="px-3 pt-2 pb-1 text-xs font-semibold text-brand-muted uppercase tracking-wide">Скоро</div>
                {user?.is_admin ? (
                  <>
                    <Link to={`/solar-return/${lastChartId}`} className={navLink(`/solar-return/${lastChartId}`)} onClick={() => setMenuOpen(false)}>
                      Соляр
                    </Link>
                    <Link to={`/synastry/${lastChartId}`} className={navLink(`/synastry/${lastChartId}`)} onClick={() => setMenuOpen(false)}>
                      Синастрия
                    </Link>
                    <Link to={`/relocation/${lastChartId}`} className={navLink(`/relocation/${lastChartId}`)} onClick={() => setMenuOpen(false)}>
                      Релокация
                    </Link>
                  </>
                ) : (
                  <>
                    <span className="px-3 py-1.5 text-sm text-brand-muted">Соляр</span>
                    <span className="px-3 py-1.5 text-sm text-brand-muted">Синастрия</span>
                    <span className="px-3 py-1.5 text-sm text-brand-muted">Релокация</span>
                  </>
                )}
              </>
            )}
            <button
              onClick={() => { logout(); setMenuOpen(false); }}
              className="self-start mt-1 px-4 py-1.5 rounded-lg text-sm font-medium text-brand-muted border border-brand-border hover:border-brand-accent hover:text-brand-text transition-colors duration-200"
            >
              Выйти
            </button>
          </div>
        </div>
      )}
    </header>
  );
}

// ─── Routes ───────────────────────────────────────────────────────────────────

function AppRoutes() {
  const { user } = useAuth();
  const [showAuth, setShowAuth] = useState(false);
  const [authReturnTo, setAuthReturnTo] = useState(null);
  const [dark, toggleDark] = useDarkMode();
  const location = useLocation();
  const prefersReducedMotion = useReducedMotion();

  useOGMeta();

  // Общий обработчик открытия модалки входа: если передан returnTo (напр. со
  // страницы карты по ссылке из письма), после логина вернёт именно туда.
  const openAuth = (returnTo) => {
    setAuthReturnTo(returnTo || null);
    setShowAuth(true);
  };

  return (
    <div className="relative min-h-screen overflow-x-hidden" style={{ background: dark ? 'transparent' : 'linear-gradient(135deg, #f8f0ff 0%, #f0e8ff 20%, #fce8f4 45%, #e8f0ff 70%, #f0f8ff 100%)', color: 'var(--text-primary)' }}>

      {/* Космический фон — только в тёмной теме */}
      {dark && <NebulaBackground element={null} />}

      <div className="relative z-10 flex flex-col min-h-screen">
        <Header onShowAuth={openAuth} dark={dark} toggleDark={toggleDark} />

        <main className="flex-1">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={prefersReducedMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={prefersReducedMotion ? undefined : { opacity: 0 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
            >
              <Routes location={location}>
                <Route path="/"               element={<LandingPage currentUser={user} onShowAuth={openAuth} />} />
                <Route path="/orion"          element={<OrionPage currentUser={user} />} />
                <Route path="/home"           element={<HomePage currentUser={user} onShowAuth={openAuth} />} />
                <Route path="/chart/share/:token" element={<SharePage />} />
                <Route path="/intake/:token" element={<IntakePage />} />
                <Route path="/portal/:token" element={<PortalPage />} />
                <Route path="/chart/:chartId" element={<ChartPage currentUser={user} onShowAuth={openAuth} dark={dark} />} />
                <Route path="/planner/:id"    element={<PlannerPage dark={dark} />} />
                <Route path="/solar-return/:chartId" element={<SolarReturnPage />} />
                <Route path="/synastry/:chartId"     element={<SynastryPage />} />
                <Route path="/relocation/:chartId"   element={<RelocationPage />} />
                <Route path="/profile"        element={<ProfilePage />} />
                <Route path="/lunar"          element={<LunarCalendarPage />} />
                <Route path="/gift"           element={<GiftPage />} />
                <Route path="/zodiac/:sign"          element={<ZodiacPage />} />
                <Route path="/dashboard/clients"     element={<CRMPage />} />
                <Route path="/admin"                element={<AdminPage />} />
                <Route path="/privacy"             element={<PrivacyPage />} />
                <Route path="/terms"               element={<TermsPage />} />
                <Route path="/reset-password"      element={<ResetPasswordPage />} />
                <Route path="/pilot/claim"         element={<PilotClaim onShowAuth={openAuth} />} />
                <Route path="/exit-survey"         element={<ExitSurveyModal page />} />
              </Routes>
            </motion.div>
          </AnimatePresence>
        </main>

        <footer className="border-t border-brand-border py-5 text-center text-brand-muted text-xs bg-brand-card/50">
          Astrea Timeline © {new Date().getFullYear()} · Расчёты: Swiss Ephemeris
          <span className="mx-2">·</span>
          <Link to="/privacy" className="hover:text-slate-600 transition-colors">Политика конфиденциальности</Link>
          <span className="mx-2">·</span>
          <Link to="/terms" className="hover:text-slate-600 transition-colors">Условия использования</Link>
        </footer>
      </div>

      <AnimatePresence>
        {showAuth && <AuthModal onClose={() => { setShowAuth(false); setAuthReturnTo(null); }} returnTo={authReturnTo} />}
      </AnimatePresence>
      <FeedbackButton />
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </ToastProvider>
  );
}
