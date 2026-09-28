/**
 * ForgotPasswordScreen.jsx — «Не помню пароль» в приложении, без браузера
 * (решение владельца 28.09.2026): почта → код на почту → новый пароль дважды
 * → вход.
 *
 * Сервер — /auth/password/reset-code и /reset-verify (backend/auth/router.py):
 * тот же механизм кода, что при регистрации (10 минут, 5 попыток, повтор не
 * чаще раза в минуту). ⚠️ Ответ на первом шаге одинаковый, есть такая почта
 * или нет, — поэтому текст «Если аккаунт с такой почтой есть…», а не «код
 * отправлен». Веб пока со ссылкой (TASKS: перевести на код).
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import useAuth from '../../hooks/useAuth.jsx';
import PasswordInput from '../../components/PasswordInput.jsx';
import { describeSendCodeError, describeVerifyError, normalizeOtpInput, validateOtpCode } from '../lib/registerRules';

const RESEND_SECONDS = 60;   // = OTP_RESEND_TTL на сервере

function ErrorText({ children }) {
  if (!children) return null;
  return <div role="alert" style={{ color: 'var(--color-danger)', fontSize: 13, lineHeight: 1.5 }}>{children}</div>;
}

export function validateNewPassword(password, password2) {
  if (!password) return 'Введи новый пароль';
  if (password.length < 8) return 'Пароль минимум 8 символов';
  if (/^\d+$/.test(password)) return 'Пароль не может состоять только из цифр';
  if (password !== password2) return 'Пароли не совпадают';
  return null;
}

export default function ForgotPasswordScreen() {
  const { sendPasswordCode, verifyPasswordCode } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState('email');   // 'email' | 'code'
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const timer = useRef(null);

  useEffect(() => () => clearInterval(timer.current), []);
  const startCooldown = () => {
    setCooldown(RESEND_SECONDS);
    clearInterval(timer.current);
    timer.current = setInterval(() => setCooldown((s) => {
      if (s <= 1) { clearInterval(timer.current); return 0; }
      return s - 1;
    }), 1000);
  };

  const send = useCallback(async () => {
    const e = email.trim();
    if (!e.includes('@')) { setError('Введи почту'); return; }
    setBusy(true); setError('');
    try {
      await sendPasswordCode({ email: e });
      setStep('code');
      startCooldown();
    } catch (err) {
      setError(describeSendCodeError(err).text || 'Не удалось отправить код.');
    } finally {
      setBusy(false);
    }
  }, [email, sendPasswordCode]);

  const verify = useCallback(async () => {
    const bad = validateOtpCode(code) || validateNewPassword(password, password2);
    if (bad) { setError(bad); return; }
    setBusy(true); setError('');
    try {
      await verifyPasswordCode({ email: email.trim(), code, newPassword: password });
      navigate('/app/feed', { replace: true });
    } catch (err) {
      setError(describeVerifyError(err).text || 'Не удалось сменить пароль.');
    } finally {
      setBusy(false);
    }
  }, [code, password, password2, email, verifyPasswordCode, navigate]);

  const title = { fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 26, color: 'var(--text-primary)', textAlign: 'center', margin: '0 0 12px' };
  const note = { margin: '0 0 20px', fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)', textAlign: 'center' };

  return (
    <div className="mobile-page" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
      <div style={{ padding: '0 24px' }}>
        {step === 'email' ? (
          <form onSubmit={(e) => { e.preventDefault(); send(); }} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <h1 style={title}>Сброс пароля</h1>
            <p style={note}>Пришлём код на почту — по нему задашь новый пароль.</p>
            <label className="mobile-label" htmlFor="forgot-email">Почта</label>
            <input
              id="forgot-email"
              className={`mobile-input${error ? ' has-error' : ''}`}
              type="email"
              inputMode="email"
              autoComplete="username"
              autoCapitalize="none"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setError(''); }}
              autoFocus
            />
            <ErrorText>{error}</ErrorText>
            <button type="submit" className="mobile-btn-primary" disabled={busy}>
              {busy ? 'Отправляю…' : 'Получить код'}
            </button>
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <Link to="/login" className="mobile-link">Вернуться ко входу</Link>
            </div>
          </form>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); verify(); }} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <h1 style={title}>Новый пароль</h1>
            <p style={note}>
              Если аккаунт с почтой <strong style={{ color: 'var(--text-primary)' }}>{email.trim()}</strong> есть,
              мы отправили на неё код. Он действителен 10 минут.
            </p>
            <input
              className="mobile-input"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="123456"
              aria-label="Код из письма"
              value={code}
              onChange={(e) => { setCode(normalizeOtpInput(e.target.value)); setError(''); }}
              style={{ fontSize: 26, letterSpacing: 8, textAlign: 'center', fontWeight: 700 }}
              autoFocus
            />
            <label className="mobile-label" htmlFor="forgot-pw">Новый пароль</label>
            <PasswordInput id="forgot-pw" className="mobile-input" autoComplete="new-password" placeholder="••••••••"
              value={password} onChange={(e) => { setPassword(e.target.value); setError(''); }} />
            <label className="mobile-label" htmlFor="forgot-pw2">Новый пароль ещё раз</label>
            <PasswordInput id="forgot-pw2" className="mobile-input" autoComplete="new-password" placeholder="••••••••"
              value={password2} onChange={(e) => { setPassword2(e.target.value); setError(''); }} />
            <p style={{ margin: 0, fontSize: 11, color: 'var(--text-secondary)' }}>Минимум 8 символов, не только цифры.</p>
            <ErrorText>{error}</ErrorText>
            <button type="submit" className="mobile-btn-primary" disabled={busy}>
              {busy ? 'Сохраняю…' : 'Сменить пароль и войти'}
            </button>
            {cooldown > 0 ? (
              <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
                Отправить код повторно можно через {cooldown} сек.
              </p>
            ) : (
              <button type="button" className="mobile-link" style={{ alignSelf: 'center' }} onClick={send} disabled={busy}>
                Отправить код повторно
              </button>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
