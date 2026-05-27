import { useState } from 'react';
import useAuth from '../hooks/useAuth.jsx';

export default function AuthModal({ onClose }) {
  const { login, register, loading, error, clearError } = useAuth();
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [showPass2, setShowPass2] = useState(false);
  const [localErr, setLocalErr] = useState('');

  const handleSubmit = async () => {
    setLocalErr('');
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
    } catch (e) {}
  };

  const switchMode = () => {
    setLocalErr(''); clearError(); setPassword(''); setPassword2('');
    setMode(m => m === 'login' ? 'register' : 'login');
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

        <div style={{ textAlign:'center', marginBottom:24 }}>
          <div style={{ fontSize:28, marginBottom:8 }}>✦</div>
          <h2 style={{ margin:0, fontSize:20, fontWeight:700, color:'#f8fafc' }}>
            {mode === 'login' ? 'Войти' : 'Создать аккаунт'}
          </h2>
          <p style={{ margin:'6px 0 0', fontSize:13, color:'#64748b' }}>
            {mode === 'login' ? 'Войдите чтобы сохранять карты' : 'Бесплатно. Без карты.'}
          </p>
        </div>

        <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:14 }}>
          <input type="email" placeholder="Email" value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            style={inp} />

          <div style={{ position:'relative' }}>
            <input type={showPass ? 'text' : 'password'}
              placeholder={mode === 'register' ? 'Пароль (мин. 8 символов)' : 'Пароль'}
              value={password} onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              style={{ ...inp, paddingRight:40 }} />
            <button onClick={() => setShowPass(p => !p)} style={eye} tabIndex={-1}>
              {showPass ? '🙈' : '👁'}
            </button>
          </div>

          {mode === 'register' && (
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
          )}
        </div>

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
          <button onClick={switchMode} style={{ background:'none', border:'none', color:'#a78bfa', cursor:'pointer', fontSize:13, fontFamily:'inherit' }}>
            {mode === 'login' ? 'Зарегистрироваться' : 'Войти'}
          </button>
        </p>
      </div>
    </div>
  );
}
