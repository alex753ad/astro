import React, { useState, useEffect } from 'react';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { AuthProvider } from './hooks/useAuth.jsx';
import useAuth from './hooks/useAuth.jsx';
import HomePage from './pages/HomePage';
import LandingPage from './pages/LandingPage';
import ChartPage from './pages/ChartPage';
import PlannerPage from './pages/PlannerPage';
import ProfilePage from './pages/ProfilePage';
import AuthModal from './components/AuthModal';
import LunarCalendarPage from './pages/LunarCalendarPage';
import SharePage from './pages/SharePage';
import GiftPage from './pages/GiftPage';
import ZodiacPage from './pages/ZodiacPage';
import CRMPage from './pages/CRMPage';
import AnalyticsPage from './pages/AnalyticsPage';
import AdminPage from './pages/AdminPage';
import PrivacyPage from './pages/PrivacyPage';
import TermsPage from './pages/TermsPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import { ToastProvider } from './components/Toast';
import ThemeToggle from './components/ThemeToggle';

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
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
  });
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('astrea_theme', dark ? 'dark' : 'light');
  }, [dark]);
  return [dark, () => setDark(d => !d)];
}

// ─── Header ───────────────────────────────────────────────────────────────────

function Header({ onShowAuth, dark, toggleDark }) {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const lastChartId = localStorage.getItem('astro_last_chart_id');
  const lastChartName = localStorage.getItem('astro_last_chart_name');
  const navChartLabel = lastChartName || (user?.email?.split('@')[0]) || 'Карта';

  const navLink = (to) => {
    const isActive = location.pathname === to || location.pathname.startsWith(to + '/');
    return isActive
      ? "px-3 py-1.5 rounded-full text-violet-600 bg-violet-100 border border-violet-300 transition-all duration-200 text-sm font-medium"
      : "px-3 py-1.5 rounded-full text-slate-600 hover:text-slate-900 hover:bg-astro-purple/20 transition-all duration-200 text-sm";
  };

  return (
    <header className="
      sticky top-0 z-50
      bg-white/80 backdrop-blur-md
      border-b border-astro-purple/20
      shadow-sm
    ">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">

        {/* Логотип */}
        <Link to="/" className="flex items-center gap-2 group">
          <span className="text-xl text-violet-400">✦</span>
          <span className="
            font-display text-lg font-bold text-slate-800
            group-hover:text-violet-500 transition-colors duration-200
          ">
            Astrea Timeline
          </span>
          <span className="hidden sm:block text-sm text-slate-400 border-l border-violet-200 pl-3 ml-1">
            — плавное выравнивание жизни по ритму космических циклов
          </span>
        </Link>

        {/* Навигация */}
        <nav className="flex items-center gap-1 text-sm">

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
            {user?.tier === 'premium' && (
              <Link to="/dashboard/clients" className={navLink('/dashboard/clients')}>
                Клиенты
              </Link>
            )}
            {user?.tier === 'premium' && (
              <Link to="/dashboard/analytics" className={navLink('/dashboard/analytics')}>
                Аналитика
              </Link>
            )}
          </div>

          {/* Profile / Auth — всегда видно */}
          {user ? (
            <>
              <Link
                to="/profile"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full
                           text-white font-medium transition-all duration-200"
                style={{ background: 'linear-gradient(135deg, #7C6CFF, #a855f7)' }}
              >
                <span>{user.email?.split('@')[0]}</span>
              </Link>
              <button
                onClick={logout}
                className="
                  hidden md:block
                  px-4 py-1.5 rounded-full text-sm font-medium
                  text-slate-500 border border-slate-200
                  hover:border-slate-300 hover:text-slate-700
                  transition-all duration-200
                "
              >
                Выйти
              </button>
            </>
          ) : (
            <button
              onClick={onShowAuth}
              className="
                px-5 py-1.5 rounded-full text-sm font-semibold text-white
                bg-gradient-to-r from-astro-purple to-astro-pink
                hover:shadow-pastel hover:-translate-y-0.5
                transition-all duration-300
              "
            >
              Войти
            </button>
          )}

          <ThemeToggle dark={dark} onToggle={toggleDark} />

          {/* Hamburger — только мобильный, только для авторизованных с картой */}
          {user && lastChartId && (
            <button
              onClick={() => setMenuOpen(m => !m)}
              className="md:hidden flex flex-col justify-center gap-1 p-2 rounded-lg text-slate-600 hover:bg-slate-100 transition-colors"
              aria-label="Меню"
            >
              <span className={`block w-5 h-0.5 bg-current transition-all duration-200 ${menuOpen ? 'rotate-45 translate-y-1.5' : ''}`} />
              <span className={`block w-5 h-0.5 bg-current transition-all duration-200 ${menuOpen ? 'opacity-0' : ''}`} />
              <span className={`block w-5 h-0.5 bg-current transition-all duration-200 ${menuOpen ? '-rotate-45 -translate-y-1.5' : ''}`} />
            </button>
          )}
        </nav>
      </div>

      {/* Mobile dropdown */}
      {menuOpen && user && lastChartId && (
        <div className="md:hidden border-t border-astro-purple/10 bg-white/95 backdrop-blur-md">
          <div className="max-w-6xl mx-auto px-4 py-2 flex flex-col gap-1">
            <Link to={`/chart/${lastChartId}`} className={navLink(`/chart/${lastChartId}`)} onClick={() => setMenuOpen(false)}>
              Натальная карта
            </Link>
            <Link to={`/planner/${lastChartId}`} className={navLink(`/planner/${lastChartId}`)} onClick={() => setMenuOpen(false)}>
              Timeline Планер
            </Link>
            <Link to="/lunar" className={navLink('/lunar')} onClick={() => setMenuOpen(false)}>
              Лунный календарь
            </Link>
            {user?.tier === 'premium' && (
              <Link to="/dashboard/clients" className={navLink('/dashboard/clients')} onClick={() => setMenuOpen(false)}>
                Клиенты
              </Link>
            )}
            {user?.tier === 'premium' && (
              <Link to="/dashboard/analytics" className={navLink('/dashboard/analytics')} onClick={() => setMenuOpen(false)}>
                Аналитика
              </Link>
            )}
            <button
              onClick={() => { logout(); setMenuOpen(false); }}
              className="self-start mt-1 px-4 py-1.5 rounded-full text-sm font-medium text-slate-500 border border-slate-200 hover:border-slate-300 hover:text-slate-700 transition-all duration-200"
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
  const [dark, toggleDark] = useDarkMode();

  useOGMeta();

  return (
    <div className="relative min-h-screen bg-astro-bg text-slate-800 overflow-x-hidden">

      {/* Декоративный блоб справа */}
      <div
        aria-hidden="true"
        className="
          pointer-events-none select-none
          absolute top-[8%] right-[-200px]
          w-[600px] h-[600px] rounded-full
          bg-gradient-to-br from-astro-yellow via-astro-pink to-astro-purple
          blur-[120px] opacity-60 z-0
        "
      />

      {/* Второй блоб снизу слева */}
      <div
        aria-hidden="true"
        className="
          pointer-events-none select-none
          absolute bottom-[5%] left-[-150px]
          w-[400px] h-[400px] rounded-full
          bg-gradient-to-tr from-astro-blue to-astro-purple
          blur-[100px] opacity-40 z-0
        "
      />

      {/* Основной контент поверх блобов */}
      <div className="relative z-10 flex flex-col min-h-screen">
        <Header onShowAuth={() => setShowAuth(true)} dark={dark} toggleDark={toggleDark} />

        <main className="flex-1">
          <Routes>
            <Route path="/"               element={<LandingPage currentUser={user} onShowAuth={() => setShowAuth(true)} />} />
            <Route path="/home"           element={<HomePage currentUser={user} onShowAuth={() => setShowAuth(true)} />} />
            <Route path="/chart/share/:token" element={<SharePage />} />
            <Route path="/chart/:chartId" element={<ChartPage currentUser={user} onShowAuth={() => setShowAuth(true)} />} />
            <Route path="/planner/:id"    element={<PlannerPage />} />
            <Route path="/profile"        element={<ProfilePage />} />
            <Route path="/lunar"          element={<LunarCalendarPage />} />
            <Route path="/gift"           element={<GiftPage />} />
            <Route path="/zodiac/:sign"          element={<ZodiacPage />} />
            <Route path="/dashboard/clients"     element={<CRMPage />} />
            <Route path="/dashboard/analytics"  element={<AnalyticsPage />} />
            <Route path="/admin"                element={<AdminPage />} />
            <Route path="/privacy"             element={<PrivacyPage />} />
            <Route path="/terms"               element={<TermsPage />} />
            <Route path="/reset-password"      element={<ResetPasswordPage />} />
          </Routes>
        </main>

        <footer className="
          border-t border-astro-purple/15 py-5
          text-center text-slate-400 text-xs
          bg-white/50 backdrop-blur-sm
        ">
          Astrea Timeline © {new Date().getFullYear()} · Расчёты: Swiss Ephemeris · AI: GPT-4o / DeepSeek
          <span className="mx-2">·</span>
          <Link to="/privacy" className="hover:text-slate-600 transition-colors">Политика конфиденциальности</Link>
          <span className="mx-2">·</span>
          <Link to="/terms" className="hover:text-slate-600 transition-colors">Условия использования</Link>
        </footer>
      </div>

      {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
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
