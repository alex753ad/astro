import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth.jsx';

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
  const { login, register, loading, error, clearError } = useAuth();
  const navigate = useNavigate();
  // mode: 'login' | 'register' | 'forgot' | 'forgot_sent' | 'reset'
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [showPass2, setShowPass2] = useState(false);
  const [localErr, setLocalErr] = useState('');
  const [localOk, setLocalOk] = useState('');
  const [forgotEmail, setForgotEmail] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);

  const handleSubmit = async () => {
    setLocalErr(''); setLocalOk('');
    clearError();
    if (!email || !password) { setLocalErr('Заполните все поля'); return; }
    if (!email.includes('@')) { setLocalErr('Введите корректный email'); return; }
    if (mode === 'register') {
      if (password.length < 8) { setLocalErr('Пароль минимум 8 символов'); return; }
      if (/^\d+$/.test(password)) { setLocalErr('Пароль не может состоять только из цифр'); return; }
      if (password !== password2) { setLocalErr('Пароли не совпадают'); return; }
    }
    try {
      if (mode === 'login') { await login(email, password); }
      else { await register(email, password); }
      onClose();
      const token = localStorage.getItem('astro_access_token');
      const last = await getLastChart(token);
      navigate(last ? `/chart/${last.id}` : '/home');
    } catch (e) {}
  };

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

  const switchMode = (m) => {
    setLocalErr(''); setLocalOk(''); clearError();
    setPassword(''); setPassword2('');
    setMode(m);
  };

  const displayError = localErr || error;

  const inp = {
    width: '100%', padding: '11px 14px', borderRadius: 8,
    border: '1px solid #334155', background: '#0f172a',
    color: '#e2e8f0', fontSize: 14, fontFamily: 'inherit',
    outline: 'none', boxSizing: 'border-box',
  };
  const eye = {
    position: 'absolute', right: 10, top: '50%',
    transform: 'translateY(-50%)', background: 'none',
    border: 'none', cursor: 'pointer', fontSize: 16, padding: 0, lineHeight: 1,
  };

  return (
    <div style={{ position:'fixed', inset:0, zIndex:1000, background:'rgba(0,0,0,0.7)', display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
      <div onClick={e => e.stopPropagation()} style={{ background:'#1e293b', border:'1px solid #334155', borderRadius:16, padding:'32px 28px', width:'100%', maxWidth:380, fontFamily:"'Inter',system-ui,sans-serif", position:'relative' }}>

        <button onClick={onClose} style={{ position:'absolute', top:14, right:16, background:'none', border:'none', color:'#64748b', fontSize:22, cursor:'pointer' }}>×</button>

        {/* ── FORGOT SENT ── */}
        {mode === 'forgot_sent' && (
          <div style={{ textAlign:'center' }}>
            <div style={{ fontSize:40, marginBottom:12 }}>📬</div>
            <h2 style={{ margin:'0 0 10px', fontSize:18, fontWeight:700, color:'#f8fafc' }}>Письмо отправлено</h2>
            <p style={{ fontSize:13, color:'#94a3b8', margin:'0 0 20px', lineHeight:1.6 }}>
              Если аккаунт с адресом <strong style={{color:'#a78bfa'}}>{forgotEmail}</strong> существует — письмо со ссылкой уже в пути. Проверьте папку «Спам».
            </p>
            <button onClick={() => switchMode('login')} style={{ background:'none', border:'none', color:'#a78bfa', cursor:'pointer', fontSize:13, fontFamily:'inherit' }}>
              ← Вернуться ко входу
            </button>
          </div>
        )}

        {/* ── FORGOT ── */}
        {mode === 'forgot' && (
          <>
            <div style={{ textAlign:'center', marginBottom:20 }}>
              <div style={{ fontSize:28, marginBottom:8 }}>🔑</div>
              <h2 style={{ margin:0, fontSize:20, fontWeight:700, color:'#f8fafc' }}>Восстановление пароля</h2>
              <p style={{ margin:'6px 0 0', fontSize:13, color:'#64748b' }}>Введите email — пришлём ссылку для сброса</p>
            </div>
            <div style={{ marginBottom:14 }}>
              <input type="email" placeholder="Email" value={forgotEmail}
                onChange={e => setForgotEmail(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleForgot()}
                style={inp} />
            </div>
            {displayError && <div style={{ fontSize:12, color:'#f87171', marginBottom:12, textAlign:'center' }}>{displayError}</div>}
            <button onClick={handleForgot} disabled={forgotLoading} style={{ width:'100%', padding:'12px', borderRadius:10, border:'none', background:'linear-gradient(135deg,#7C6CFF,#A78BFA)', color:'#fff', fontWeight:700, fontSize:14, cursor: forgotLoading ? 'not-allowed':'pointer', opacity: forgotLoading ? 0.7:1, fontFamily:'inherit' }}>
              {forgotLoading ? 'Отправляем…' : 'Отправить ссылку'}
            </button>
            <p style={{ textAlign:'center', marginTop:16, fontSize:13, color:'#64748b' }}>
              <button onClick={() => switchMode('login')} style={{ background:'none', border:'none', color:'#a78bfa', cursor:'pointer', fontSize:13, fontFamily:'inherit' }}>← Вернуться ко входу</button>
            </p>
          </>
        )}

        {/* ── LOGIN / REGISTER ── */}
        {(mode === 'login' || mode === 'register') && (
          <>
            <div style={{ textAlign:'center', marginBottom:24 }}>
              <div style={{ fontSize:28, marginBottom:8 }}>✦</div>
              <h2 style={{ margin:0, fontSize:20, fontWeight:700, color:'#f8fafc' }}>
                {mode === 'login' ? 'Войти' : 'Создать аккаунт'}
              </h2>
              <p style={{ margin:'6px 0 0', fontSize:13, color:'#64748b' }}>
                {mode === 'login' ? 'Войдите чтобы сохранять карты' : 'Бесплатно. Без карты.'}
              </p>
            </div>

            <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:6 }}>
              <input type="email" placeholder="Email" value={email}
                onChange={e => setEmail(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                style={inp} />

              <div style={{ position:'relative' }}>
                <input type={showPass ? 'text' : 'password'}
                  placeholder={mode === 'register' ? 'Пароль (мин. 8 символов, не только цифры)' : 'Пароль'}
                  value={password} onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                  style={{ ...inp, paddingRight:40 }} />
                <button onClick={() => setShowPass(p => !p)} style={eye} tabIndex={-1}>
                  {showPass ? '🙈' : '👁'}
                </button>
              </div>

              {mode === 'register' && (
                <>
                  <p style={{ margin:'2px 0 4px', fontSize:11, color:'#64748b', lineHeight:1.5 }}>
                    Пароль: минимум 8 символов, буквы и цифры, не только цифры
                  </p>
                  <div style={{ position:'relative' }}>
                    <input type={showPass2 ? 'text' : 'password'}
                      placeholder="Повторите пароль"
                      value={password2} onChange={e => setPassword2(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                      style={{ ...inp, paddingRight:40, borderColor: password2 && password !== password2 ? '#f87171' : '#334155' }} />
                    <button onClick={() => setShowPass2(p => !p)} style={eye} tabIndex={-1}>
                      {showPass2 ? '🙈' : '👁'}
                    </button>
                  </div>
                </>
              )}
            </div>

            {mode === 'login' && (
              <div style={{ textAlign:'right', marginBottom:10 }}>
                <button onClick={() => switchMode('forgot')} style={{ background:'none', border:'none', color:'#64748b', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
                  Забыли пароль?
                </button>
              </div>
            )}

            {displayError && (
              <div style={{ fontSize:12, color:'#f87171', marginBottom:12, textAlign:'center' }}>
                {displayError}
              </div>
            )}

            <button onClick={handleSubmit} disabled={loading} style={{ width:'100%', padding:'12px', borderRadius:10, border:'none', background:'linear-gradient(135deg,#7C6CFF,#A78BFA)', color:'#fff', fontWeight:700, fontSize:14, cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1, fontFamily:'inherit' }}>
              {loading ? 'Загрузка…' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'}
            </button>

            <p style={{ textAlign:'center', marginTop:16, fontSize:13, color:'#64748b' }}>
              {mode === 'login' ? 'Нет аккаунта?' : 'Уже есть аккаунт?'}{' '}
              <button onClick={() => switchMode(mode === 'login' ? 'register' : 'login')} style={{ background:'none', border:'none', color:'#a78bfa', cursor:'pointer', fontSize:13, fontFamily:'inherit' }}>
                {mode === 'login' ? 'Зарегистрироваться' : 'Войти'}
              </button>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
