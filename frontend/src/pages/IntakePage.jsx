/**
 * IntakePage.jsx — публичная анкета клиента по токену (/intake/:token)
 * Клиент заполняет данные рождения + вопрос; данные падают в CRM астролога.
 */

import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

const API_BASE = 'https://astro-production-abcc.up.railway.app/api/v1';

export default function IntakePage() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({
    name: '', birth_date: '', birth_time: '', time_unknown: false,
    birth_place: '', email: '', question: '',
  });
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  useEffect(() => {
    if (!token) return;
    fetch(`${API_BASE}/crm/intake/${token}`)
      .then(r => { if (!r.ok) throw new Error('Анкета не найдена'); return r.json(); })
      .then(setInfo)
      .catch(e => setError(e.message));
  }, [token]);

  const submit = async () => {
    if (!form.name || !form.birth_date || !form.birth_place) {
      alert('Заполните имя, дату и место рождения');
      return;
    }
    setSending(true);
    try {
      const body = {
        name: form.name,
        birth_date: form.birth_date,
        birth_time: form.time_unknown ? null : (form.birth_time || null),
        birth_place: form.birth_place,
        email: form.email || null,
        question: form.question || null,
      };
      const r = await fetch(`${API_BASE}/crm/intake/${token}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || 'Не удалось отправить');
      }
      setDone(true);
    } catch (e) {
      alert(e.message);
    }
    setSending(false);
  };

  if (error) return (
    <div style={s.page}><div style={s.center}><p style={{ color: 'var(--color-danger)' }}>{error}</p></div></div>
  );

  if (!info) return (
    <div style={s.page}><div style={s.center}><div style={s.logo}>☽ ✦ ☾</div><p style={{ color: 'var(--text-secondary)' }}>Загрузка…</p></div></div>
  );

  const alreadyDone = done || info.status === 'converted' || (info.submitted && info.status !== 'pending');

  return (
    <div style={s.page}>
      <header style={s.header}>
        <div style={s.logo}>☽ ✦ ☾</div>
        <span style={s.brand}>{info.astrologer_name}</span>
      </header>

      <main style={s.main}>
        {alreadyDone ? (
          <div style={s.card}>
            <h1 style={s.title}>Спасибо!</h1>
            <p style={s.subtitle}>Ваша анкета отправлена астрологу. Он свяжется с вами.</p>
          </div>
        ) : (
          <div style={s.card}>
            <h1 style={s.title}>Анкета к консультации</h1>
            <p style={s.subtitle}>Заполните данные рождения — это нужно для расчёта вашей карты.</p>

            <label style={s.label}>Имя *</label>
            <input style={s.input} value={form.name} onChange={e => set('name', e.target.value)} />

            <label style={s.label}>Дата рождения *</label>
            <input style={s.input} type="date" value={form.birth_date} onChange={e => set('birth_date', e.target.value)} />

            <label style={s.label}>Время рождения</label>
            <input
              style={{ ...s.input, opacity: form.time_unknown ? 0.5 : 1 }}
              type="time"
              value={form.birth_time}
              disabled={form.time_unknown}
              onChange={e => set('birth_time', e.target.value)}
            />
            <label style={s.check}>
              <input type="checkbox" checked={form.time_unknown} onChange={e => set('time_unknown', e.target.checked)} />
              Не знаю точное время
            </label>

            <label style={s.label}>Место рождения *</label>
            <input style={s.input} placeholder="Город, страна" value={form.birth_place} onChange={e => set('birth_place', e.target.value)} />

            <label style={s.label}>Email</label>
            <input style={s.input} type="email" value={form.email} onChange={e => set('email', e.target.value)} />

            <label style={s.label}>Ваш вопрос / что хотите разобрать</label>
            <textarea style={{ ...s.input, minHeight: 90, resize: 'vertical' }} value={form.question} onChange={e => set('question', e.target.value)} />

            <button style={s.btn} onClick={submit} disabled={sending}>
              {sending ? 'Отправляю…' : 'Отправить анкету'}
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

const s = {
  page: {
    minHeight: '100vh',
    background: 'linear-gradient(160deg, var(--bg-deeper) 0%, var(--bg-card) 100%)',
    color: '#fff',
    fontFamily: "'Segoe UI', Arial, sans-serif",
  },
  center: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 16 },
  logo: { fontSize: 22, color: 'var(--accent-glow)' },
  header: { display: 'flex', alignItems: 'center', gap: 12, padding: '20px 32px', borderBottom: '1px solid rgba(112,80,200,0.2)' },
  brand: { fontSize: 18, fontWeight: 700, color: 'var(--accent-glow)', letterSpacing: 0.5 },
  main: { maxWidth: 520, margin: '0 auto', padding: '32px 20px 60px' },
  card: {
    background: 'rgba(255,255,255,0.03)',
    border: '1px solid rgba(112,80,200,0.2)',
    borderRadius: 20,
    padding: '28px 24px',
    display: 'flex', flexDirection: 'column',
  },
  title: { margin: '0 0 6px', fontSize: 24, fontWeight: 700, color: 'var(--accent-muted)' },
  subtitle: { margin: '0 0 20px', fontSize: 14, color: 'var(--text-secondary)' },
  label: { fontSize: 12, color: 'var(--accent)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.6, margin: '12px 0 6px' },
  input: {
    background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(112,80,200,0.3)',
    borderRadius: 10, padding: '11px 14px',
    color: '#fff', fontSize: 15, fontFamily: 'inherit', outline: 'none',
  },
  check: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-secondary)', margin: '8px 0' },
  btn: {
    marginTop: 20,
    background: 'linear-gradient(135deg, var(--accent), var(--accent))',
    color: '#fff', border: 'none', borderRadius: 12,
    padding: '14px 24px', fontSize: 15, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
  },
};
