import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth.jsx';
import MotionButton from './MotionButton';

const API_BASE = 'https://astro-production-abcc.up.railway.app/api/v1';

async function getLastChart(accessToken) {
  try {
    const resp = await fetch(`${API_BASE}/profile/charts`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const data = await resp.json();
    const charts = data.charts || [];
    return charts.length ? charts[0] : null;
  } catch {
    return null;
  }
}

export default function AuthModal({ onClose }) {
  const { login, loading, error, clearError } = useAuth();
  const navigate = useNavigate();

  // mode: 'login' | 'register' | 'register_verify' | 'forgot' | 'forgot_sent'
  const [mode, setMode] = useState('login');

  // login / register fields
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [showPass2, setShowPass2] = useState(false);

  // OTP verify
  const [otpCode, setOtpCode] = useState('');
  const [otpLoading, setOtpLoading] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  // forgot
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);

  const [localErr, setLocalErr] = useState('');
  const [localOk, setLocalOk] = useState('');

  const displayError = localErr || error;

  // ── cooldown timer ──────────────────────────────────────
  function startCooldown() {
    setCooldown(60);
    const t = setInterval(() => {
      setCooldown(c => {
        if (c <= 1) { clearInterval(t); return 0; }
        return c - 1;
      });
    }, 1000);
  }

  const switchMode = (m) => {
    setLocalErr(''); setLocalOk(''); clearError();
    setPassword(''); setPassword2(''); setOtpCode('');
    setMode(m);
  };

  // ── Login ───────────────────────────────────────────────
  const handleLogin = async () => {
    setLocalErr(''); clearError();
    if (!email || !password) { setLocalErr('Заполните все поля'); return; }
    try {
      await login(email, password);
      onClose();
      const token = localStorage.getItem('astro_access_token');
      const last = await getLastChart(token);
      navigate(last ? `/chart/${last.id}` : '/home');
    } catch {}
  };

  // ── Register step 1: send OTP ───────────────────────────
  const handleSendCode = async () => {
    setLocalErr(''); clearError();
    if (!email || !password) { setLocalErr('Заполните все поля'); return; }
    if (!email.includes('@')) { setLocalErr('Введите корректный email'); return; }
    if (password.length < 8) { setLocalErr('Пароль минимум 8 символов'); return; }
    if (/^\d+$/.test(password)) { setLocalErr('Пароль не может состоять только из цифр'); return; }
    if (password !== password2) { setLocalErr('Пароли не совпадают'); return; }

    setOtpLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/register/email/send-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password, name: name.trim() || undefined }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Ошибка отправки кода');
      setMode('register_verify');
      startCooldown();
    } catch (e) {
      setLocalErr(e.message);
    } finally {
      setOtpLoading(false);
    }
  };

  // ── Register step 2: verify OTP ────────────────────────
  const handleVerify = async () => {
    setLocalErr(''); clearError();
    if (!/^\d{6}$/.test(otpCode)) { setLocalErr('Введите 6-значный код'); return; }

    setOtpLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/register/email/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), code: otpCode }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Ошибка подтверждения');

      localStorage.setItem('astro_access_token', data.access_token);
      localStorage.setItem('astro_refresh_token', data.refresh_token);
      localStorage.setItem('astro_user', JSON.stringify({
        id: data.user_id,
        email: data.email,
        name: data.name ?? null,
        tier: data.tier,
        is_admin: data.is_admin ?? false,
      }));

      onClose();
      window.location.replace('/home');
    } catch (e) {
      setLocalErr(e.message);
    } finally {
      setOtpLoading(false);
    }
  };

  // ── Forgot password ─────────────────────────────────────
  const handleForgot = async () => {
    setLocalErr(''); setLocalOk('');
    if (!forgotEmail.includes('@')) { setLocalErr('Введите корректный email'); return; }
    setForgotLoading(true);
    try {
      await fetch(`${API_BASE}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: forgotEmail }),
      });
      setMode('forgot_sent');
    } catch {
      setLocalErr('Ошибка сети, попробуйте снова');
    } finally {
      setForgotLoading(false);
    }
  };

  // ── Styles ──────────────────────────────────────────────
  const inp = {
    width: '100%', padding: '11px 14px', borderRadius: 8,
    border: '1px solid var(--border)', background: 'var(--bg-deeper)',
    color: 'var(--text-primary)', fontSize: 14, fontFamily: 'inherit',
    outline: 'none', boxSizing: 'border-box',
  };
  const eye = {
    position: 'absolute', right: 10, top: '50%',
    transform: 'translateY(-50%)', background: 'none',
    border: 'none', cursor: 'pointer', fontSize: 16, padding: 0, lineHeight: 1,
  };
  const btn = (disabled) => ({
    width: '100%', padding: '12px', borderRadius: 10, border: 'none',
    background: disabled
      ? 'rgba(124,108,255,0.35)'
      : 'var(--accent)',
    color: '#fff', fontWeight: 700, fontSize: 14,
    cursor: disabled ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
  });

  return (
    <div style={{ position:'fixed', inset:0, zIndex:1000, background:'rgba(0,0,0,0.7)', display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
      <div onClick={e => e.stopPropagation()} style={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:16, padding:'32px 28px', width:'100%', maxWidth:380, fontFamily:"'Inter',system-ui,sans-serif", position:'relative' }}>

        <button onClick={onClose} style={{ position:'absolute', top:14, right:16, background:'none', border:'none', color:'var(--text-secondary)', fontSize:22, cursor:'pointer' }}>×</button>

        {/* ── FORGOT SENT ── */}
        {mode === 'forgot_sent' && (
          <div style={{ textAlign:'center' }}>
            <div style={{ fontSize:40, marginBottom:12 }}>📬</div>
            <h2 style={{ margin:'0 0 10px', fontSize:18, fontWeight:700, color:'var(--text-primary)' }}>Письмо отправлено</h2>
            <p style={{ fontSize:13, color:'var(--text-secondary)', margin:'0 0 20px', lineHeight:1.6 }}>
              Если аккаунт с адресом <strong style={{color:'var(--accent-glow)'}}>{forgotEmail}</strong> существует — письмо со ссылкой уже в пути.
            </p>
            <button onClick={() => switchMode('login')} style={{ background:'none', border:'none', color:'var(--accent-glow)', cursor:'pointer', fontSize:13, fontFamily:'inherit' }}>
              ← Вернуться ко входу
            </button>
          </div>
        )}

        {/* ── FORGOT ── */}
        {mode === 'forgot' && (
          <>
            <div style={{ textAlign:'center', marginBottom:20 }}>
              <div style={{ fontSize:28, marginBottom:8 }}>🔑</div>
              <h2 style={{ margin:0, fontSize:20, fontWeight:700, color:'var(--text-primary)' }}>Восстановление пароля</h2>
              <p style={{ margin:'6px 0 0', fontSize:13, color:'var(--text-secondary)' }}>Введите email — пришлём ссылку для сброса</p>
            </div>
            <div style={{ marginBottom:14 }}>
              <input type="email" placeholder="Email" value={forgotEmail}
                onChange={e => setForgotEmail(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleForgot()}
                style={inp} />
            </div>
            {displayError && <div style={{ fontSize:12, color:'var(--color-danger)', marginBottom:12, textAlign:'center' }}>{displayError}</div>}
            <MotionButton level="primary" onClick={handleForgot} disabled={forgotLoading} style={btn(forgotLoading)}>
              {forgotLoading ? 'Отправляем…' : 'Отправить ссылку'}
            </MotionButton>
            <p style={{ textAlign:'center', marginTop:16, fontSize:13, color:'var(--text-secondary)' }}>
              <button onClick={() => switchMode('login')} style={{ background:'none', border:'none', color:'var(--accent-glow)', cursor:'pointer', fontSize:13, fontFamily:'inherit' }}>← Вернуться ко входу</button>
            </p>
          </>
        )}

        {/* ── LOGIN ── */}
        {mode === 'login' && (
          <>
            <div style={{ textAlign:'center', marginBottom:24 }}>
              <div style={{ fontSize:28, marginBottom:8 }}>✦</div>
              <h2 style={{ margin:0, fontSize:20, fontWeight:700, color:'var(--text-primary)' }}>Войти</h2>
              <p style={{ margin:'6px 0 0', fontSize:13, color:'var(--text-secondary)' }}>Войдите чтобы сохранять карты</p>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:6 }}>
              <input type="email" placeholder="Email" value={email}
                onChange={e => setEmail(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleLogin()}
                style={inp} />
              <div style={{ position:'relative' }}>
                <input type={showPass ? 'text' : 'password'} placeholder="Пароль"
                  value={password} onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleLogin()}
                  style={{ ...inp, paddingRight:40 }} />
                <button onClick={() => setShowPass(p => !p)} style={eye} tabIndex={-1}>
                  {showPass ? '🙈' : '👁'}
                </button>
              </div>
            </div>
            <div style={{ textAlign:'right', marginBottom:10 }}>
              <button onClick={() => switchMode('forgot')} style={{ background:'none', border:'none', color:'var(--text-secondary)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
                Забыли пароль?
              </button>
            </div>
            {displayError && <div style={{ fontSize:12, color:'var(--color-danger)', marginBottom:12, textAlign:'center' }}>{displayError}</div>}
            <MotionButton level="primary" onClick={handleLogin} disabled={loading} style={btn(loading)}>
              {loading ? 'Загрузка…' : 'Войти'}
            </MotionButton>
            <p style={{ textAlign:'center', marginTop:16, fontSize:13, color:'var(--text-secondary)' }}>
              Нет аккаунта?{' '}
              <button onClick={() => switchMode('register')} style={{ background:'none', border:'none', color:'var(--accent-glow)', cursor:'pointer', fontSize:13, fontFamily:'inherit' }}>
                Зарегистрироваться
              </button>
            </p>
          </>
        )}

        {/* ── REGISTER STEP 1 ── */}
        {mode === 'register' && (
          <>
            <div style={{ textAlign:'center', marginBottom:24 }}>
              <div style={{ fontSize:28, marginBottom:8 }}>✦</div>
              <h2 style={{ margin:0, fontSize:20, fontWeight:700, color:'var(--text-primary)' }}>Создать аккаунт</h2>
              <p style={{ margin:'6px 0 0', fontSize:13, color:'var(--text-secondary)' }}>Бесплатно. Без карты.</p>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:6 }}>
              <input type="text" placeholder="Ваше имя (необязательно)" value={name}
                onChange={e => setName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendCode()}
                style={inp} />
              <div>
                <input type="email" placeholder="Email (Яндекс, Mail.ru, Rambler)" value={email}
                  onChange={e => setEmail(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSendCode()}
                  style={inp} />
                <p style={{ margin:'4px 0 0', fontSize:11, color:'var(--text-secondary)', lineHeight:1.5 }}>
                  Используйте почту российского сервиса: yandex.ru, mail.ru, rambler.ru и др.
                </p>
              </div>
              <div>
                <div style={{ position:'relative' }}>
                  <input type={showPass ? 'text' : 'password'}
                    placeholder="Пароль"
                    value={password} onChange={e => setPassword(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleSendCode()}
                    style={{ ...inp, paddingRight:40 }} />
                  <button onClick={() => setShowPass(p => !p)} style={eye} tabIndex={-1}>
                    {showPass ? '🙈' : '👁'}
                  </button>
                </div>
                <p style={{ margin:'4px 0 0', fontSize:11, color:'var(--text-secondary)', lineHeight:1.5 }}>
                  Минимум 8 символов · буквы и цифры · не только цифры
                </p>
              </div>
              <div style={{ position:'relative' }}>
                <input type={showPass2 ? 'text' : 'password'}
                  placeholder="Повторите пароль"
                  value={password2} onChange={e => setPassword2(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSendCode()}
                  style={{ ...inp, paddingRight:40, borderColor: password2 && password !== password2 ? 'var(--color-danger)' : 'var(--border)' }} />
                <button onClick={() => setShowPass2(p => !p)} style={eye} tabIndex={-1}>
                  {showPass2 ? '🙈' : '👁'}
                </button>
              </div>
            </div>
            {displayError && <div style={{ fontSize:12, color:'var(--color-danger)', marginBottom:12, textAlign:'center' }}>{displayError}</div>}
            <MotionButton level="primary" onClick={handleSendCode} disabled={otpLoading} style={btn(otpLoading)}>
              {otpLoading ? 'Отправляю код…' : 'Получить код →'}
            </MotionButton>
            <p style={{ textAlign:'center', marginTop:16, fontSize:13, color:'var(--text-secondary)' }}>
              Уже есть аккаунт?{' '}
              <button onClick={() => switchMode('login')} style={{ background:'none', border:'none', color:'var(--accent-glow)', cursor:'pointer', fontSize:13, fontFamily:'inherit' }}>
                Войти
              </button>
            </p>
          </>
        )}

        {/* ── REGISTER STEP 2: OTP ── */}
        {mode === 'register_verify' && (
          <>
            <div style={{ textAlign:'center', marginBottom:24 }}>
              <div style={{ fontSize:28, marginBottom:8 }}>📬</div>
              <h2 style={{ margin:0, fontSize:20, fontWeight:700, color:'var(--text-primary)' }}>Введите код</h2>
              <p style={{ margin:'8px 0 0', fontSize:13, color:'var(--text-secondary)', lineHeight:1.6 }}>
                Код отправлен на <strong style={{color:'var(--accent-glow)'}}>{email}</strong>.<br/>
                Действителен 10 минут.
              </p>
            </div>
            <div style={{ marginBottom:16 }}>
              <input
                type="text" inputMode="numeric" maxLength={6}
                placeholder="123456"
                value={otpCode}
                onChange={e => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                onKeyDown={e => e.key === 'Enter' && handleVerify()}
                style={{ ...inp, fontSize:28, letterSpacing:10, textAlign:'center', fontWeight:700 }}
                autoFocus
              />
            </div>
            {displayError && <div style={{ fontSize:12, color:'var(--color-danger)', marginBottom:12, textAlign:'center' }}>{displayError}</div>}
            <MotionButton level="primary" onClick={handleVerify} disabled={otpLoading} style={btn(otpLoading)}>
              {otpLoading ? 'Проверяю…' : 'Подтвердить'}
            </MotionButton>
            <p style={{ textAlign:'center', marginTop:14, fontSize:12, color:'var(--text-secondary)' }}>
              {cooldown > 0 ? (
                `Отправить повторно через ${cooldown} сек.`
              ) : (
                <button onClick={() => { setMode('register'); setOtpCode(''); setLocalErr(''); }}
                  style={{ background:'none', border:'none', color:'var(--accent-glow)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
                  Отправить код повторно
                </button>
              )}
            </p>
          </>
        )}

      </div>
    </div>
  );
}
