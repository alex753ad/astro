import React from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import { AuthProvider } from './hooks/useAuth.jsx';
import useAuth from './hooks/useAuth.jsx';
import HomePage from './pages/HomePage';
import ChartPage from './pages/ChartPage';
import PlannerPage from './PlannerPage';

function Header() {
  return (
    <header className="border-b border-brand-accent/10 bg-brand-dark/80 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3 group">
          <span className="text-2xl">✦</span>
          <span className="font-display text-xl font-bold text-brand-glow group-hover:text-white transition-colors">
            Astro SPA
          </span>
        </Link>
        <nav className="flex items-center gap-6 text-sm text-brand-muted">
          <Link to="/" className="hover:text-brand-text transition-colors">Главная</Link>
          <a href="/api/docs" target="_blank" rel="noopener"
             className="hover:text-brand-text transition-colors">API Docs</a>
        </nav>
      </div>
    </header>
  );
}

// Отдельный компонент внутри AuthProvider — чтобы useAuth работал
function AppRoutes() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<HomePage />} />
          {/* currentUser пробрасывается в ChartPage для синхронизации режима эксперта */}
          <Route path="/chart/:chartId" element={<ChartPage currentUser={user} />} />
          <Route path="/planner/:id" element={<PlannerPage />} />
        </Routes>
      </main>
      <footer className="border-t border-brand-accent/10 py-6 text-center text-brand-muted text-xs">
        Astro SPA © {new Date().getFullYear()} · Расчёты: Swiss Ephemeris · AI: GPT-4o / DeepSeek
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
