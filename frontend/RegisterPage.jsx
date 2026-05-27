/**
 * RegisterPage — email + password registration.
 */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth';

export default function RegisterPage() {
  const { register, loading, error, clearError } = useAuth();
  const navigate = useNavigate();

  const [email,     setEmail]     = useState('');
  const [password,  setPassword]  = useState('');
  const [password2, setPassword2] = useState('');
  const [localErr,  setLocalErr]  = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalErr('');
    clearError();

    if (password !== password2) {
      setLocalErr('Пароли не совпадают');
      return;
    }
    if (password.length < 8) {
      setLocalErr('Пароль должен быть не менее 8 символов');
      return;
    }
    if (/^\d+$/.test(password)) {
      setLocalErr('Пароль не может состоять только из цифр');
      return;
    }

    try {
      await register(email, password);
      navigate('/', { replace: true });
    } catch (err) {
      setLocalErr(err.message || 'Ошибка регистрации');
    }
  };

  const displayError = localErr || error;

  const inputStyle = {
    width: '100%', padding: '12px 14px', borderRadius: 10,
    border: '1.5px solid var(--border, #1E2235)',
    background: 'var(--input-bg, #0F1120)',
    color: 'var(--text-primary, #E8EAF0)',
    fontSize: 15, outline: 'none', boxSizing: 'border-box', fontFamily: 'inherit',
  };

  const labelStyle = {
    display: 'block', fontSize: 13, fontWeight: 600,
    color: 'var(--text-secondary)', marginBottom: 6,
  };

  return (
    <div style={{ maxWidth: 420, margin: '60px auto', padding: '0 16px' }}>
      <div className="glass-card p-8">
        <h1 className="font-display text-2xl font-bold text-center mb-2">Регистрация</h1>
        <p className="text-brand-muted text-sm text-center mb-8">
          Уже есть аккаунт?{' '}
          <Link to="/login" className="text-brand-glow hover:underline">
            Войти
          </Link>
        </p>

        <form onSubmit={handleSubmit} noValidate>
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Email</label>
            <input
              type="email" value={email}
              onChange={e => setEmail(e.target.value)}
              required autoComplete="email"
              placeholder="you@example.com"
              style={inputStyle}
            />
          </div>

          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Пароль</label>
            <input
              type="password" value={password}
              onChange={e => setPassword(e.target.value)}
              required autoComplete="new-password"
              placeholder="Минимум 8 символов"
              style={inputStyle}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={labelStyle}>Повторите пароль</label>
            <input
              type="password" value={password2}
              onChange={e => setPassword2(e.target.value)}
              required autoComplete="new-password"
              placeholder="••••••••"
              style={{
                ...inputStyle,
                borderColor: password2 && password !== password2 ? '#EF4444' : undefined,
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
            type="submit" disabled={loading}
            style={{
              width: '100%', padding: '13px', borderRadius: 10, border: 'none',
              background: loading ? 'rgba(124,108,255,0.4)' : 'linear-gradient(135deg, #7C6CFF, #A78BFA)',
              color: '#fff', fontSize: 15, fontWeight: 700,
              cursor: loading ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
            }}
          >
            {loading ? 'Создаю аккаунт…' : 'Создать аккаунт'}
          </button>
        </form>

        <p style={{ marginTop: 16, fontSize: 11, color: 'var(--text-secondary)', textAlign: 'center', lineHeight: 1.5 }}>
          Регистрируясь, вы соглашаетесь с условиями использования.<br/>
          Ваши данные хранятся в зашифрованном виде.
        </p>
      </div>
    </div>
  );
}
