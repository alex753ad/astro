import React, { useState } from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import { AuthProvider } from './hooks/useAuth.jsx';
import useAuth from './hooks/useAuth.jsx';
import HomePage from './pages/HomePage';
import ChartPage from './pages/ChartPage';
import PlannerPage from './PlannerPage';
import ProfilePage from './pages/ProfilePage';
import AuthModal from './components/AuthModal';
import LunarCalendarPage from './pages/LunarCalendarPage';

function Header() {
  const { user, logout } = useAuth();
  const [showAuth, setShowAuth] = useState(false);

  return (
    <>
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
              Astro SPA
            </span>
          </Link>

          {/* Навигация */}
          <nav className="flex items-center gap-1 text-sm">
            <Link
              to="/"
              className="px-3 py-1.5 rounded-full text-slate-600 hover:text-slate-900
                         hover:bg-astro-purple/20 transition-all duration-200"
            >
              Главная
            </Link>
            <Link
              to="/lunar"
              className="px-3 py-1.5 rounded-full text-slate-600 hover:text-slate-900
                         hover:bg-astro-blue/40 transition-all duration-200"
            >
              🌙 Луна
            </Link>
            <a
              href="/api/docs"
              target="_blank"
              rel="noopener"
              className="px-3 py-1.5 rounded-full text-slate-600 hover:text-slate-900
                         hover:bg-slate-100 transition-all duration-200"
            >
              API Docs
            </a>

            {user ? (
              <>
                <Link
                  to="/profile"
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full
                             text-slate-600 hover:text-slate-900 hover:bg-slate-100
                             transition-all duration-200"
                >
                  <span>👤</span>
                  <span>{user.email?.split('@')[0]}</span>
                </Link>
                <button
                  onClick={logout}
                  className="
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
                onClick={() => setShowAuth(true)}
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
          </nav>
        </div>
      </header>

      {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
    </>
  );
}

function AppRoutes() {
  const { user } = useAuth();

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
        <Header />

        <main className="flex-1">
          <Routes>
            <Route path="/"               element={<HomePage />} />
            <Route path="/chart/:chartId" element={<ChartPage currentUser={user} />} />
            <Route path="/planner/:id"    element={<PlannerPage />} />
            <Route path="/profile"        element={<ProfilePage />} />
            <Route path="/lunar"          element={<LunarCalendarPage />} />
          </Routes>
        </main>

        <footer className="
          border-t border-astro-purple/15 py-5
          text-center text-slate-400 text-xs
          bg-white/50 backdrop-blur-sm
        ">
          Astro SPA © {new Date().getFullYear()} · Расчёты: Swiss Ephemeris · AI: GPT-4o / DeepSeek
        </footer>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
