/**
 * AuthModal.jsx — модальное окно входа / регистрации.
 * Копировать в: frontend/src/components/AuthModal.jsx
 */

import { useState } from 'react';
import useAuth from '../hooks/useAuth.jsx';

export default function AuthModal({ onClose }) {
  const { login, register, loading, error, clearError } = useAuth();
  const [mode, setMode]         = useState('login'); // 'login' | 'register'
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [localErr, setLocalErr] = useState('');

  const handleSubmit = async () => {
    setLocalErr('');
    clearError();
    if (!email || !password) { setLocalErr('Заполните все поля'); return; }
    try {
      if (mode === 'login') {
        await login(email, password);
      } else {
        await register(email, password);
      }
      onClose();
    } catch (e) {
      // error уже в useAuth
    }
  };

  const switchMode = () => {
    setLocalErr('');
    clearError();
    setMode(m => m === 'login' ? 'register' : 'login');
  };

  const displayError = localErr || error;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: 16,
          padding: '32px 28px',
          width: '100%', maxWidth: 380,
          fontFamily: "'Inter', system-ui, sans-serif",
        }}
      >
        {/* Заголовок */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>✦</div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#f8fafc' }}>
            {mode === 'login' ? 'Войти' : 'Создать аккаунт'}
          </h2>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: '#64748b' }}>
            {mode === 'login' ? 'Войдите чтобы сохранять карты' : 'Бесплатно. Без карты.'}
          </p>
        </div>

        {/* Поля */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            style={inputStyle}
          />
          <input
            type="password"
            placeholder="Пароль"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            style={inputStyle}
          />
        </div>

        {/* Ошибка */}
        {displayError && (
          <div style={{ fontSize: 12, color: '#f87171', marginBottom: 12, textAlign: 'center' }}>
            {displayError}
          </div>
        )}

        {/* Кнопка */}
        <button
          onClick={handleSubmit}
          disabled={loading}
          style={{
            width: '100%',
            padding: '12px',
            borderRadius: 10,
            border: 'none',
            background: 'linear-gradient(135deg, #7C6CFF, #A78BFA)',
            color: '#fff',
            fontWeight: 700,
            fontSize: 14,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.7 : 1,
            fontFamily: 'inherit',
          }}
        >
          {loading ? 'Загрузка…' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'}
        </button>

        {/* Переключение */}
        <p style={{ textAlign: 'center', marginTop: 16, fontSize: 13, color: '#64748b' }}>
          {mode === 'login' ? 'Нет аккаунта?' : 'Уже есть аккаунт?'}{' '}
          <button
            onClick={switchMode}
            style={{ background: 'none', border: 'none', color: '#a78bfa', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit' }}
          >
            {mode === 'login' ? 'Зарегистрироваться' : 'Войти'}
          </button>
        </p>

        {/* Закрыть */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 16, right: 16,
            background: 'none', border: 'none',
            color: '#64748b', fontSize: 20, cursor: 'pointer',
          }}
        >
          ×
        </button>
      </div>
    </div>
  );
}

const inputStyle = {
  width: '100%',
  padding: '11px 14px',
  borderRadius: 8,
  border: '1px solid #334155',
  background: '#0f172a',
  color: '#e2e8f0',
  fontSize: 14,
  fontFamily: 'inherit',
  outline: 'none',
  boxSizing: 'border-box',
};
