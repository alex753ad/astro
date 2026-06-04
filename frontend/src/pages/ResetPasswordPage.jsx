import { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

const API_BASE = 'https://astro-production-abcc.up.railway.app/api/v1';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') || '';
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [done, setDone] = useState(false);

  const handleSubmit = async () => {
    setErr('');
    if (password.length < 8) { setErr('Пароль минимум 8 символов'); return; }
    if (/^\d+$/.test(password)) { setErr('Пароль не может состоять только из цифр'); return; }
    if (password !== password2) { setErr('Пароли не совпадают'); return; }
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password }),
      });
      const data = await resp.json();
      if (!resp.ok) { setErr(data.detail || 'Ошибка сброса пароля'); return; }
      setDone(true);
      setTimeout(() => navigate('/'), 3000);
    } catch {
      setErr('Ошибка сети, попробуйте снова');
    } finally {
      setLoading(false);
    }
  };

  const inp = {
    width: '100%', padding: '11px 14px', borderRadius: 8,
    border: '1px solid #334155', background: '#0f172a',
    color: '#e2e8f0', fontSize: 14, fontFamily: 'inherit',
    outline: 'none', boxSizing: 'border-box',
  };

  return (
    <div style={{ minHeight:'100vh', background:'#0f172a', display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
      <div style={{ background:'#1e293b', border:'1px solid #334155', borderRadius:16, padding:'32px 28px', width:'100%', maxWidth:380, fontFamily:"'Inter',system-ui,sans-serif" }}>
        {done ? (
          <div style={{ textAlign:'center' }}>
            <div style={{ fontSize:40, marginBottom:12 }}>✅</div>
            <h2 style={{ margin:'0 0 10px', fontSize:18, fontWeight:700, color:'#f8fafc' }}>Пароль изменён</h2>
            <p style={{ fontSize:13, color:'#94a3b8' }}>Перенаправляем вас на главную…</p>
          </div>
        ) : (
          <>
            <div style={{ textAlign:'center', marginBottom:24 }}>
              <div style={{ fontSize:28, marginBottom:8 }}>🔑</div>
              <h2 style={{ margin:0, fontSize:20, fontWeight:700, color:'#f8fafc' }}>Новый пароль</h2>
              <p style={{ margin:'6px 0 0', fontSize:13, color:'#64748b' }}>Минимум 8 символов, буквы и цифры</p>
            </div>

            {!token && (
              <div style={{ fontSize:13, color:'#f87171', textAlign:'center', marginBottom:16 }}>
                Ссылка недействительна. Запросите сброс пароля снова.
              </div>
            )}

            <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:14 }}>
              <div style={{ position:'relative' }}>
                <input type={showPass ? 'text' : 'password'}
                  placeholder="Новый пароль"
                  value={password} onChange={e => setPassword(e.target.value)}
                  style={{ ...inp, paddingRight:40 }} />
                <button onClick={() => setShowPass(p => !p)} style={{ position:'absolute', right:10, top:'50%', transform:'translateY(-50%)', background:'none', border:'none', cursor:'pointer', fontSize:16, padding:0 }} tabIndex={-1}>
                  {showPass ? '🙈' : '👁'}
                </button>
              </div>
              <input type="password" placeholder="Повторите пароль"
                value={password2} onChange={e => setPassword2(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                style={{ ...inp, borderColor: password2 && password !== password2 ? '#f87171' : '#334155' }} />
            </div>

            {err && <div style={{ fontSize:12, color:'#f87171', marginBottom:12, textAlign:'center' }}>{err}</div>}

            <button onClick={handleSubmit} disabled={loading || !token} style={{ width:'100%', padding:'12px', borderRadius:10, border:'none', background:'linear-gradient(135deg,#7C6CFF,#A78BFA)', color:'#fff', fontWeight:700, fontSize:14, cursor: loading ? 'not-allowed':'pointer', opacity: (loading || !token) ? 0.6:1, fontFamily:'inherit' }}>
              {loading ? 'Сохраняем…' : 'Сохранить пароль'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
