/**
 * LoginPage — email + password login with Google OAuth button.
 */

import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import useAuth from '../hooks/useAuth';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
const REDIRECT_URI     = `${window.location.origin}/oauth/callback`;

function buildGoogleOAuthUrl() {
  const params = new URLSearchParams({
    client_id:     GOOGLE_CLIENT_ID,
    redirect_uri:  REDIRECT_URI,
    response_type: 'code',
    scope:         'openid email profile',
    access_type:   'offline',
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
}

export default function LoginPage() {
  const { login, loading, error, clearError } = useAuth();
  const navigate  = useNavigate();
  const location  = useLocation();
  const from      = location.state?.from || '/';

  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [localErr, setLocalErr] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalErr('');
    clearError();
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setLocalErr(err.message || 'Ошибка входа');
    }
  };

  const displayError = localErr || error;

  return (
    <div style={{ maxWidth: 420, margin: '60px auto', padding: '0 16px' }}>
      <div className="glass-card p-8">
        <h1 className="font-display text-2xl font-bold text-center mb-2">Вход</h1>
        <p className="text-brand-muted text-sm text-center mb-8">
          Нет аккаунта?{' '}
          <Link to="/register" className="text-brand-glow hover:underline">
            Зарегистрироваться
          </Link>
        </p>

        {/* Google OAuth */}
        {GOOGLE_CLIENT_ID && (
          <>
            <a
              href={buildGoogleOAuthUrl()}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                width: '100%', padding: '12px', borderRadius: 10,
                border: '1.5px solid var(--border, #1E2235)',
                background: 'transparent',
                color: 'var(--text-primary, #E8EAF0)',
                fontSize: 14, fontWeight: 600,
                textDecoration: 'none',
                transition: 'border-color 0.2s, background 0.2s',
                marginBottom: 20,
              }}
            >
              <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
                <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.2l6.7-6.7C35.7 2.5 30.2 0 24 0 14.8 0 7 5.4 3.2 13.3l7.8 6C12.8 13 18 9.5 24 9.5z"/>
                <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.2-.4-4.7H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.4-4.1 6.9-10.2 6.9-17.4z"/>
                <path fill="#FBBC05" d="M11 28.3c-.7-2-1-4.1-1-6.3s.4-4.3 1-6.3l-7.8-6C1.2 13.5 0 18.6 0 24s1.2 10.5 3.2 14.3l7.8-6z"/>
                <path fill="#34A853" d="M24 48c6.2 0 11.4-2 15.2-5.4l-7.6-5.9c-2 1.4-4.6 2.3-7.6 2.3-6 0-11.1-4-12.9-9.5l-7.8 6C7 42.6 14.8 48 24 48z"/>
              </svg>
              Войти через Google
            </a>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20,
              color: 'var(--text-secondary, #8B8FA3)', fontSize: 12,
            }}>
              <div style={{ flex: 1, height: 1, background: 'var(--border, #1E2235)' }} />
              или
              <div style={{ flex: 1, height: 1, background: 'var(--border, #1E2235)' }} />
            </div>
          </>
        )}

        {/* Email/password form */}
        <form onSubmit={handleSubmit} noValidate>
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="you@example.com"
              style={{
                width: '100%', padding: '12px 14px', borderRadius: 10,
                border: '1.5px solid var(--border, #1E2235)',
                background: 'var(--input-bg, #0F1120)',
                color: 'var(--text-primary, #E8EAF0)',
                fontSize: 15, outline: 'none', boxSizing: 'border-box', fontFamily: 'inherit',
              }}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
              Пароль
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••"
              style={{
                width: '100%', padding: '12px 14px', borderRadius: 10,
                border: '1.5px solid var(--border, #1E2235)',
                background: 'var(--input-bg, #0F1120)',
                color: 'var(--text-primary, #E8EAF0)',
                fontSize: 15, outline: 'none', boxSizing: 'border-box', fontFamily: 'inherit',
              }}
            />
          </div>

          {displayError && (
            <div style={{
              padding: '10px 14px', borderRadius: 8, marginBottom: 14,
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.2)',
              fontSize: 13, color: '#FCA5A5',
            }} role="alert">
              {displayError}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%', padding: '13px', borderRadius: 10,
              border: 'none',
              background: loading ? 'rgba(124,108,255,0.4)' : 'linear-gradient(135deg, #7C6CFF, #A78BFA)',
              color: '#fff', fontSize: 15, fontWeight: 700,
              cursor: loading ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit',
            }}
          >
            {loading ? 'Вхожу…' : 'Войти'}
          </button>
        </form>
      </div>
    </div>
  );
}
