/**
 * LoginScreen.jsx — единственный экран с настоящим содержимым в этом задании.
 *
 * Почта + пароль → useAuth().login(). Мобильный транспорт (заголовок
 * X-Client-Platform, refresh в нативное хранилище вместо HttpOnly-куки)
 * включается САМ, без единой строчки здесь: useAuth.jsx и api/authTransport.js
 * читают import.meta.env.VITE_MOBILE — эта сборка идёт с --mode mobile
 * (build:mobile), веб об этой ветке кода даже не узнаёт на этапе минификации.
 *
 * Google-входа нет: в webview он не открывается (нужен системный браузер или
 * нативный SDK) — отдельная задача, явно исключённая из этого задания.
 */

import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import useAuth from '../../hooks/useAuth.jsx';

export default function LoginScreen() {
  const { login, loading, error, clearError } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    if (!email || !password) return;
    try {
      await login(email, password);
      navigate('/app/feed', { replace: true });
    } catch {
      // Текст ошибки уже лежит в error из хука — форма просто остаётся открытой.
    }
  }

  return (
    // mobile-page задаёт padding-top/bottom через env(safe-area-inset-*) —
    // именно поэтому здесь нет собственного inline `padding`: инлайн-стиль
    // всегда перебивает стилевой класс для тех же свойств (даже если в классе
    // они заданы не тем же шорткодом), и любой padding в этом style
    // молча стёр бы безопасные отступы сверху/снизу. Горизонтальный отступ и
    // центрирование — на вложенном div, где эта коллизия невозможна.
    <div
      className="mobile-page"
      style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
    >
      <div style={{ padding: '0 24px' }}>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: 28,
            color: 'var(--text-primary)',
            textAlign: 'center',
            margin: '0 0 32px',
          }}
        >
          Aristea Timeline
        </h1>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label className="mobile-label" htmlFor="mobile-login-email">Почта</label>
            <input
              id="mobile-login-email"
              className={`mobile-input${error ? ' has-error' : ''}`}
              type="email"
              inputMode="email"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => { setEmail(e.target.value); if (error) clearError(); }}
              required
            />
          </div>

          <div>
            <label className="mobile-label" htmlFor="mobile-login-password">Пароль</label>
            <input
              id="mobile-login-password"
              className={`mobile-input${error ? ' has-error' : ''}`}
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => { setPassword(e.target.value); if (error) clearError(); }}
              required
            />
          </div>

          {error && (
            <div style={{ color: 'var(--color-danger)', fontSize: 13 }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="mobile-btn-primary"
            disabled={loading || !email || !password}
            style={{ marginTop: 12 }}
          >
            {loading ? 'Вхожу…' : 'Войти'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <Link to="/register" className="mobile-link">
            Нет аккаунта? Зарегистрироваться
          </Link>
        </div>
      </div>
    </div>
  );
}
