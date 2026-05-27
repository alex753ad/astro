import React, { useState } from 'react';
import { Routes, Route, Link, useNavigate } from 'react-router-dom';
import { AuthProvider } from './hooks/useAuth.jsx';
import useAuth from './hooks/useAuth.jsx';
import HomePage from './pages/HomePage';
import ChartPage from './pages/ChartPage';
import PlannerPage from './PlannerPage';
import ProfilePage from './pages/ProfilePage';
import AuthModal from './components/AuthModal';

function Header() {
  const { user, logout } = useAuth();
  const [showAuth, setShowAuth] = useState(false);

  return (
    <>
      <header className="border-b border-brand-accent/10 bg-brand-dark/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3 group">
            <span className="text-2xl">✦</span>
            <span className="font-display text-xl font-bold text-brand-glow group-hover:text-white transition-colors">
              Astrea Timeline
            </span>
          </Link>

          <nav className="flex items-center gap-4 text-sm text-brand-muted">
            <Link to="/" className="hover:text-brand-text transition-colors">Главная</Link>
            <a href="/api/docs" target="_blank" rel="noopener"
               className="hover:text-brand-text transition-colors">API Docs</a>

            {user ? (
              <>
                <Link
                  to="/profile"
                  className="hover:text-brand-text transition-colors"
                  style={{ display: 'flex', alignItems: 'center', gap: 4 }}
                >
                  <span>👤</span>
                  {user.email?.split('@')[0]}
                </Link>
                <button
                  onClick={logout}
                  style={{
                    padding: '6px 14px', borderRadius: 8,
                    border: '1px solid #334155', background: 'transparent',
                    color: '#94a3b8', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit',
                  }}
                >
                  Выйти
                </button>
              </>
            ) : (
              <button
                onClick={() => setShowAuth(true)}
                style={{
                  padding: '7px 18px', borderRadius: 8, border: 'none',
                  background: 'linear-gradient(135deg, #7C6CFF, #A78BFA)',
                  color: '#fff', fontWeight: 600, fontSize: 13,
                  cursor: 'pointer', fontFamily: 'inherit',
                }}
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
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/chart/:chartId" element={<ChartPage currentUser={user} />} />
          <Route path="/planner/:id" element={<PlannerPage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Routes>
      </main>
      <footer className="border-t border-brand-accent/10 py-6 text-center text-brand-muted text-xs">
        Astrea Timeline © {new Date().getFullYear()} · Расчёты: Swiss Ephemeris · AI: GPT-4o / DeepSeek
      </footer>
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
