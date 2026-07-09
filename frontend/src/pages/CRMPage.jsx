/**
 * CRMPage — управление клиентами для Premium астрологов.
 * Маршрут: /dashboard/clients
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import NatalChart from '../components/NatalChart';
import TransitTimeline from '../components/TransitTimeline';
import ChartSummary from '../components/ChartSummary';
import AspectTable from '../components/AspectTable';
import AspectGrid from '../components/AspectGrid';
import { useState as _useStateD, useEffect as _useEffectD } from 'react';

// Реактивно читаем класс .dark на <html>
function useIsDark() {
  const [dark, setDark] = _useStateD(() => document.documentElement.classList.contains('dark'));
  _useEffectD(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => setDark(el.classList.contains('dark')));
    obs.observe(el, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);
  return dark;
}

const CRM_THEME_CSS = `
  .crm-scope { --crm-text:#1e293b; --crm-card:rgba(255,255,255,0.85); --crm-title:#7c3aed; --crm-input:#f8f4ff; --crm-muted:#94a3b8; }
  .dark .crm-scope { --crm-text:#E2DFF0; --crm-card:rgba(26,18,48,0.55); --crm-title:#A78BFA; --crm-input:rgba(35,28,56,0.60); --crm-muted:#9B97B0; }
`;

// ─── Мини-превью карты ────────────────────────────────────────────────────────
function MiniChartPreview({ clientId, authFetch }) {
  const dark = useIsDark();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!clientId) return;
    setLoading(true);
    authFetch(`/api/v1/clients/${clientId}/chart`)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [clientId]);

  if (!clientId) return null;
  if (loading) return <div style={{ width: 80, height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: 11 }}>…</div>;
  if (!data) return null;

  return (
    <div style={{ width: 80, height: 80, flexShrink: 0 }}>
      <NatalChart
        planets={data.planets}
        houses={data.houses}
        aspects={data.aspects}
        ascendant={data.ascendant}
        compact={true}
        dark={dark}
      />
    </div>
  );
}

const API = '/api/v1';

const ZODIAC_SIGNS = ['Овен','Телец','Близнецы','Рак','Лев','Дева','Весы','Скорпион','Стрелец','Козерог','Водолей','Рыбы'];
const PLANETS      = ['Sun','Moon','Mercury','Venus','Mars','Jupiter','Saturn','Uranus','Neptune','Pluto'];
const HOUSES       = [1,2,3,4,5,6,7,8,9,10,11,12];

const S = {
  page: { minHeight: '100vh', background: 'transparent', color: 'var(--crm-text)', fontFamily: "'Inter', system-ui, sans-serif", padding: '24px 16px' },
  inner: { maxWidth: 900, margin: '0 auto' },
  card: { background: 'var(--crm-card)', border: '1px solid rgba(139,92,246,0.15)', borderRadius: 12, padding: '20px 24px', marginBottom: 16 },
  title: { fontSize: 14, fontWeight: 700, margin: '0 0 16px', color: 'var(--crm-title)', textTransform: 'uppercase', letterSpacing: '0.06em' },
  row: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' },
  btn: (v = 'ghost') => ({
    padding: '8px 16px', borderRadius: 8, border: v === 'ghost' ? '1px solid rgba(139,92,246,0.25)' : 'none', cursor: 'pointer', fontFamily: 'inherit',
    background: v === 'primary' ? 'linear-gradient(135deg,#7C6CFF,#A78BFA)' : v === 'danger' ? '#ef4444' : 'transparent',
    color: v === 'ghost' ? 'var(--crm-title)' : '#fff', fontWeight: 600, fontSize: 13,
  }),
  input: { width: '100%', background: 'var(--crm-input)', border: '1px solid rgba(139,92,246,0.25)', borderRadius: 8, padding: '8px 12px', color: 'var(--crm-text)', fontSize: 13, fontFamily: 'inherit', boxSizing: 'border-box' },
  muted: { fontSize: 12, color: 'var(--crm-muted)' },
  label: { fontSize: 12, color: 'var(--crm-title)', marginBottom: 4, display: 'block' },
};

// ─── Форма добавления клиента ─────────────────────────────────────────────────
const STATUS_META = {
  lead:     ['Лид', '#f59e0b'],
  active:   ['Активный', '#22c55e'],
  regular:  ['Постоянный', '#8b5cf6'],
  archived: ['Архив', '#64748b'],
};
const STATUS_OPTIONS = Object.entries(STATUS_META).map(([v, m]) => [v, m[0]]);

function StatusBadge({ status }) {
  const m = STATUS_META[status];
  if (!m) return null;
  return (
    <span style={{ fontSize: 11, fontWeight: 600, color: m[1], background: m[1] + '22', padding: '2px 8px', borderRadius: 6, whiteSpace: 'nowrap' }}>
      {m[0]}
    </span>
  );
}

const parseTags = (str) => (str || '').split(',').map(t => t.trim().replace(/^#/, '')).filter(Boolean);

function TagChips({ tags }) {
  if (!tags || !tags.length) return null;
  return <>{tags.map((t, i) => (
    <span key={i} style={{ fontSize: 11, color: '#38bdf8', background: '#38bdf822', padding: '2px 7px', borderRadius: 6, marginRight: 4 }}>#{t}</span>
  ))}</>;
}

function daysToBirthday(bd) {
  if (!bd || bd.length < 10) return null;
  const mo = Number(bd.slice(5, 7)), d = Number(bd.slice(8, 10));
  if (!mo || !d) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  let next = new Date(today.getFullYear(), mo - 1, d);
  if (next < today) next = new Date(today.getFullYear() + 1, mo - 1, d);
  return Math.round((next - today) / 86400000);
}

function BirthdayBadge({ birthDate }) {
  const n = daysToBirthday(birthDate);
  if (n === null || n > 14) return null;
  const label = n === 0 ? '🎂 ДР сегодня' : `🎂 ДР через ${n} дн.`;
  return <span style={{ fontSize: 11, fontWeight: 600, color: '#ec4899', background: '#ec489922', padding: '2px 8px', borderRadius: 6, whiteSpace: 'nowrap' }}>{label}</span>;
}

function AddClientForm({ onSave, onCancel, authFetch }) {
  const [form, setForm] = useState({ name: '', birth_date: '', birth_time: '', birth_place: '', notes: '', email: '', status: 'lead', source: '', tags: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      const body = { ...form };
      if (!body.birth_time) delete body.birth_time;
      if (!body.notes) delete body.notes;
      if (!body.email) delete body.email;
      if (!body.source) delete body.source;
      body.tags = parseTags(form.tags);
      const client = await authFetch(`${API}/clients`, { method: 'POST', body: JSON.stringify(body) });
      onSave(client);
    } catch (err) {
      setError(err.message || 'Ошибка');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={S.card}>
      <p style={S.title}>Новый клиент</p>
      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
          <div>
            <label style={S.label}>Имя *</label>
            <input style={S.input} value={form.name} onChange={e => set('name', e.target.value)} required />
          </div>
          <div>
            <label style={S.label}>Место рождения *</label>
            <input style={S.input} value={form.birth_place} onChange={e => set('birth_place', e.target.value)} required />
          </div>
          <div>
            <label style={S.label}>Дата рождения *</label>
            <input style={S.input} type="date" value={form.birth_date} onChange={e => set('birth_date', e.target.value)} required />
          </div>
          <div>
            <label style={S.label}>Время рождения</label>
            <input style={S.input} type="time" value={form.birth_time} onChange={e => set('birth_time', e.target.value)} />
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
          <div>
            <label style={S.label}>Статус</label>
            <select style={S.input} value={form.status} onChange={e => set('status', e.target.value)}>
              {STATUS_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label style={S.label}>Источник</label>
            <input style={S.input} placeholder="Instagram, рекомендация…" value={form.source} onChange={e => set('source', e.target.value)} />
          </div>
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={S.label}>Теги (через запятую)</label>
          <input style={S.input} placeholder="хорар, бизнес, сложный" value={form.tags} onChange={e => set('tags', e.target.value)} />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={S.label}>Email (для рассылки)</label>
          <input style={S.input} type="email" value={form.email} onChange={e => set('email', e.target.value)} />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={S.label}>Заметки</label>
          <textarea style={{ ...S.input, minHeight: 60, resize: 'vertical' }} value={form.notes} onChange={e => set('notes', e.target.value)} />
        </div>
        {error && <p style={{ color: '#f87171', fontSize: 12, margin: '0 0 12px' }}>{error}</p>}
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="submit" style={S.btn('primary')} disabled={loading}>{loading ? 'Сохраняю…' : 'Сохранить'}</button>
          <button type="button" style={S.btn()} onClick={onCancel}>Отмена</button>
        </div>
      </form>
    </div>
  );
}

// ─── Карточка клиента ─────────────────────────────────────────────────────────
function ClientCard({ client, authFetch, onBack, onUpdated, initialTab }) {
  const dark = useIsDark();
  const [chart, setChart] = useState(null);
  const [notes, setNotes] = useState(client.notes || '');
  const [notesLoading, setNotesLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [aiText, setAiText] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [tab, setTab] = useState(initialTab || 'chart');

  // Консультации (020)
  const [consultations, setConsultations] = useState([]);
  const [consLoading, setConsLoading] = useState(false);
  const [showConsForm, setShowConsForm] = useState(false);
  const [consForm, setConsForm] = useState({ date: '', topic: '', notes: '', assignment: '', price: '', status: 'done', question_moment: '', question_place: '' });
  const [consSaving, setConsSaving] = useState(false);
  const setCF = (k, v) => setConsForm(p => ({ ...p, [k]: v }));

  const loadConsultations = async () => {
    setConsLoading(true);
    try {
      const data = await authFetch(`${API}/clients/${client.id}/consultations`);
      setConsultations(data);
    } catch {}
    setConsLoading(false);
  };

  const saveConsultation = async () => {
    setConsSaving(true);
    try {
      const body = { topic: consForm.topic || null, notes: consForm.notes || null, assignment: consForm.assignment || null, status: consForm.status };
      if (consForm.date) body.date = new Date(consForm.date).toISOString();
      if (consForm.price) body.price = Number(consForm.price);
      if (consForm.topic === 'хорар') {
        if (consForm.question_moment) body.question_moment = new Date(consForm.question_moment).toISOString();
        if (consForm.question_place) body.question_place = consForm.question_place;
      }
      const created = await authFetch(`${API}/clients/${client.id}/consultations`, { method: 'POST', body: JSON.stringify(body) });
      setConsultations(prev => [created, ...prev]);
      setConsForm({ date: '', topic: '', notes: '', assignment: '', price: '', status: 'done', question_moment: '', question_place: '' });
      setShowConsForm(false);
    } catch (e) {
      alert('Ошибка: ' + (e.message || ''));
    }
    setConsSaving(false);
  };

  const deleteConsultation = async (cid) => {
    if (!window.confirm('Удалить консультацию?')) return;
    try {
      await authFetch(`${API}/clients/${client.id}/consultations/${cid}`, { method: 'DELETE' });
      setConsultations(prev => prev.filter(c => c.id !== cid));
    } catch {}
  };

  // Бриф к встрече (021)
  const [briefOpen, setBriefOpen] = useState(false);
  const [briefText, setBriefText] = useState('');
  const [briefLoading, setBriefLoading] = useState(false);
  const [briefSaving, setBriefSaving] = useState(false);

  const loadBrief = async () => {
    setBriefOpen(true);
    setBriefLoading(true);
    setBriefText('');
    try {
      const res = await fetch(`${API}/clients/${client.id}/brief`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('astro_access_token')}` },
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let result = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ') && !line.includes('[DONE]')) {
            try {
              const d = JSON.parse(line.slice(6));
              if (d.text) { result += d.text; setBriefText(result); }
            } catch {}
          }
        }
      }
    } catch (e) {
      setBriefText('Ошибка подготовки брифа.');
    }
    setBriefLoading(false);
  };

  const saveBriefToConsultation = async () => {
    if (!briefText.trim()) return;
    setBriefSaving(true);
    try {
      const created = await authFetch(`${API}/clients/${client.id}/consultations`, {
        method: 'POST',
        body: JSON.stringify({ topic: 'подготовка', notes: briefText, status: 'planned' }),
      });
      setConsultations(prev => [created, ...prev]);
      setBriefOpen(false);
      setTab('consultations');
    } catch (e) {
      alert('Ошибка: ' + (e.message || ''));
    }
    setBriefSaving(false);
  };

  // Резюме клиента (024)
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryText, setSummaryText] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryCached, setSummaryCached] = useState(false);

  const loadSummary = async (refresh) => {
    setSummaryOpen(true);
    setSummaryLoading(true);
    if (!refresh) setSummaryText('');
    try {
      const r = await authFetch(`${API}/clients/${client.id}/summary${refresh ? '?refresh=1' : ''}`);
      setSummaryText(r.summary || '');
      setSummaryCached(!!r.cached);
    } catch (e) {
      setSummaryText('Ошибка генерации резюме.');
    }
    setSummaryLoading(false);
  };

  // Портал клиента (026)
  const [portal, setPortal] = useState(null);
  const [portalBusy, setPortalBusy] = useState(false);
  const [portalCopied, setPortalCopied] = useState(false);

  useEffect(() => {
    authFetch(`${API}/clients/${client.id}/portal`).then(setPortal).catch(() => {});
  }, []);

  const setPortalEnabled = async (enabled) => {
    setPortalBusy(true);
    try {
      const p = await authFetch(`${API}/clients/${client.id}/portal`, { method: 'POST', body: JSON.stringify({ enabled }) });
      setPortal(p);
    } catch (e) { alert('Ошибка: ' + (e.message || '')); }
    setPortalBusy(false);
  };

  const copyPortal = () => {
    if (!portal?.url) return;
    navigator.clipboard.writeText(portal.url).then(() => { setPortalCopied(true); setTimeout(() => setPortalCopied(false), 2000); });
  };

  // Редактирование данных клиента
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: client.name, birth_date: client.birth_date, birth_time: client.birth_time || '', birth_place: client.birth_place, notes: client.notes || '', email: client.email || '', status: client.status || 'lead', source: client.source || '', tags: (client.tags || []).join(', ') });
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState('');
  const setEF = (k, v) => setEditForm(p => ({ ...p, [k]: v }));

  const saveEdit = async () => {
    setEditLoading(true); setEditError('');
    try {
      const body = { ...editForm };
      if (!body.birth_time) delete body.birth_time;
      body.tags = parseTags(editForm.tags);
      const updated = await authFetch(`${API}/clients/${client.id}`, { method: 'PATCH', body: JSON.stringify(body) });
      onUpdated(updated);
      setEditing(false);
    } catch (err) {
      setEditError(err.message || 'Ошибка');
    } finally {
      setEditLoading(false);
    }
  };

  // Шаблоны заметок
  const [templates, setTemplates] = useState([]);
  const [showTemplateDropdown, setShowTemplateDropdown] = useState(false);
  const [showNewTemplateForm, setShowNewTemplateForm] = useState(false);
  const [newTplTitle, setNewTplTitle] = useState('');
  const [newTplContent, setNewTplContent] = useState('');
  const [tplSaving, setTplSaving] = useState(false);
  const textareaRef = useRef(null);

  useEffect(() => {
    authFetch('/api/v1/note-templates').then(setTemplates).catch(() => {});
  }, []);

  useEffect(() => {
    authFetch(`${API}/clients/${client.id}/chart`).then(setChart).catch(() => {});
  }, [client.id]);

  const loadAI = async () => {
    if (!client.natal_chart_id) return;
    setAiLoading(true);
    setAiText('');
    try {
      const res = await fetch(`/api/v1/chart/${client.natal_chart_id}/interpret`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('astro_access_token')}` },
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let result = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ') && !line.includes('[DONE]')) {
            try {
              const d = JSON.parse(line.slice(6));
              if (d.text) { result += d.text; setAiText(result); }
            } catch {}
          }
        }
      }
    } catch (e) {
      setAiText('Ошибка загрузки интерпретации.');
    }
    setAiLoading(false);
  };

  const saveNotes = async () => {
    setNotesLoading(true);
    try {
      const updated = await authFetch(`${API}/clients/${client.id}`, { method: 'PATCH', body: JSON.stringify({ notes }) });
      onUpdated(updated);
    } catch {}
    setNotesLoading(false);
  };

  const [wordLimit, setWordLimit] = useState(2000);

  const generateReport = async () => {
    setReportLoading(true);
    try {
      const token = localStorage.getItem('astro_access_token');
      const res = await fetch(`${API}/clients/${client.id}/report`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ word_limit: wordLimit }),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        let detail = res.statusText;
        try { detail = JSON.parse(text).detail || text || res.statusText; } catch { detail = text || res.statusText; }
        throw new Error(`${res.status}: ${detail}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `natal_${client.name.replace(/ /g, '_')}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
    setReportLoading(false);
  };

  const tabs = ['chart', 'transits', 'ai', 'notes', 'consultations'];
  const tabLabels = { chart: 'Карта', transits: 'Транзиты', ai: 'AI-интерпретация', notes: 'Заметки', consultations: 'Консультации' };

  return (
    <div>
      <div style={{ ...S.row, marginBottom: 16 }}>
        <button style={S.btn()} onClick={onBack}>← Назад</button>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button style={S.btn('primary')} onClick={loadBrief}>✨ Подготовить встречу</button>
          <button style={S.btn()} onClick={() => loadSummary(false)}>🧾 Резюме клиента</button>
          <select
            value={wordLimit}
            onChange={e => setWordLimit(Number(e.target.value))}
            style={{ ...S.input, width: 'auto', padding: '7px 10px' }}
            disabled={reportLoading}
          >
            {[1000, 2000, 3000, 4000, 5000].map(w => (
              <option key={w} value={w}>{w} слов</option>
            ))}
          </select>
          <button style={S.btn('primary')} onClick={generateReport} disabled={reportLoading}>
            {reportLoading ? 'Создаю…' : '📄 Создать PDF отчёт'}
          </button>
        </div>
      </div>

      <div style={S.card}>
        <div style={S.row}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4, flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 700, fontSize: 18 }}>{client.name}</span>
              <StatusBadge status={client.status} />
              <BirthdayBadge birthDate={client.birth_date} />
            </div>
            <div style={S.muted}>{client.birth_date}{client.birth_time ? ` · ${client.birth_time}` : ''} · {client.birth_place}{client.source ? ` · ${client.source}` : ''}</div>
            {client.tags && client.tags.length > 0 && <div style={{ marginTop: 6 }}><TagChips tags={client.tags} /></div>}
          </div>
          <button style={S.btn()} onClick={() => { setEditing(v => !v); setEditError(''); }}>
            {editing ? 'Отмена' : 'Редактировать'}
          </button>
        </div>

        {editing && (
          <div style={{ marginTop: 16, borderTop: '1px solid rgba(139,92,246,0.12)', paddingTop: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
              <div>
                <label style={S.label}>Имя</label>
                <input style={S.input} value={editForm.name} onChange={e => setEF('name', e.target.value)} />
              </div>
              <div>
                <label style={S.label}>Место рождения</label>
                <input style={S.input} value={editForm.birth_place} onChange={e => setEF('birth_place', e.target.value)} />
              </div>
              <div>
                <label style={S.label}>Дата рождения</label>
                <input style={S.input} type="date" value={editForm.birth_date} onChange={e => setEF('birth_date', e.target.value)} />
              </div>
              <div>
                <label style={S.label}>Время рождения</label>
                <input style={S.input} type="time" value={editForm.birth_time} onChange={e => setEF('birth_time', e.target.value)} />
              </div>
              <div>
                <label style={S.label}>Email (для рассылки)</label>
                <input style={S.input} type="email" value={editForm.email} onChange={e => setEF('email', e.target.value)} />
              </div>
              <div>
                <label style={S.label}>Статус</label>
                <select style={S.input} value={editForm.status} onChange={e => setEF('status', e.target.value)}>
                  {STATUS_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
              <div>
                <label style={S.label}>Источник</label>
                <input style={S.input} placeholder="Instagram, рекомендация…" value={editForm.source} onChange={e => setEF('source', e.target.value)} />
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <label style={S.label}>Теги (через запятую)</label>
                <input style={S.input} placeholder="хорар, бизнес, сложный" value={editForm.tags} onChange={e => setEF('tags', e.target.value)} />
              </div>
            </div>
            {editError && <p style={{ color: '#f87171', fontSize: 12, margin: '0 0 10px' }}>{editError}</p>}
            <button style={S.btn('primary')} onClick={saveEdit} disabled={editLoading}>
              {editLoading ? 'Сохраняю…' : 'Сохранить'}
            </button>
          </div>
        )}
      </div>

      {briefOpen && (
        <div style={S.card}>
          <div style={{ ...S.row, marginBottom: 12 }}>
            <label style={S.label}>Бриф к встрече</label>
            <button style={S.btn()} onClick={() => setBriefOpen(false)}>Закрыть</button>
          </div>
          {briefLoading && !briefText && <div style={S.muted}>Готовлю бриф…</div>}
          {briefText && (
            <>
              <div style={{ fontSize: 14, color: 'var(--crm-text)', lineHeight: 1.7, whiteSpace: 'pre-wrap', marginBottom: 12 }}>
                {briefText}
              </div>
              <button style={S.btn('primary')} onClick={saveBriefToConsultation} disabled={briefSaving || briefLoading}>
                {briefSaving ? 'Сохраняю…' : 'Сохранить как подготовку'}
              </button>
            </>
          )}
        </div>
      )}

      {summaryOpen && (
        <div style={S.card}>
          <div style={{ ...S.row, marginBottom: 12 }}>
            <label style={S.label}>Резюме клиента{summaryCached && !summaryLoading ? ' · из кэша' : ''}</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <button style={S.btn()} onClick={() => loadSummary(true)} disabled={summaryLoading}>Обновить</button>
              <button style={S.btn()} onClick={() => setSummaryOpen(false)}>Закрыть</button>
            </div>
          </div>
          {summaryLoading && !summaryText && <div style={S.muted}>Генерирую…</div>}
          {summaryText && (
            <div style={{ fontSize: 14, color: 'var(--crm-text)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
              {summaryText}
            </div>
          )}
        </div>
      )}

      <div style={S.card}>
        <div style={S.row}>
          <label style={S.label}>Портал клиента (read-only ссылка)</label>
          {portal?.enabled
            ? <button style={S.btn()} onClick={() => setPortalEnabled(false)} disabled={portalBusy}>Выключить</button>
            : <button style={S.btn('primary')} onClick={() => setPortalEnabled(true)} disabled={portalBusy}>Включить портал</button>}
        </div>
        {portal?.enabled && portal?.url && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
            <input style={{ ...S.input, flex: 1, minWidth: 220 }} value={portal.url} readOnly />
            <button style={S.btn()} onClick={copyPortal}>{portalCopied ? '✓ Скопировано' : 'Копировать'}</button>
          </div>
        )}
      </div>

      {/* Вкладки */}
      <div style={{ display: 'flex', gap: 4, background: 'rgba(139,92,246,0.08)', borderRadius: 10, padding: 4, marginBottom: 16 }}>
        {tabs.map(t => (
          <button key={t} onClick={() => {
            setTab(t);
            if (t === 'ai' && !aiText) loadAI();
            if (t === 'consultations') loadConsultations();
          }}
            style={{ flex: 1, padding: '8px 12px', borderRadius: 8, border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 500,
              background: tab === t ? 'var(--crm-card)' : 'transparent', color: tab === t ? 'var(--crm-title)' : 'var(--crm-muted)' }}>
            {tabLabels[t]}
          </button>
        ))}
      </div>

      {tab === 'chart' && (
        <div style={S.card}>
          {chart ? (
            <>
              <NatalChart planets={chart.planets} houses={chart.houses} aspects={chart.aspects} ascendant={chart.ascendant} midheaven={chart.midheaven} compact={false} dark={dark} />
              <div style={{ borderTop: '1px solid rgba(139,92,246,0.1)', marginTop: 16, paddingTop: 8 }}>
                <ChartSummary planets={chart.planets} ascendant={chart.ascendant} midheaven={chart.midheaven} houses={chart.houses} timeUnknown={!client.birth_time} plain />
              </div>
              <div style={{ borderTop: '1px solid rgba(139,92,246,0.1)', marginTop: 8 }}>
                <AspectTable aspects={chart.aspects} />
              </div>
              <div style={{ borderTop: '1px solid rgba(139,92,246,0.1)', marginTop: 8 }}>
                <AspectGrid aspects={chart.aspects} planets={chart.planets} />
              </div>
            </>
          ) : (
            <div style={S.muted}>Загрузка карты…</div>
          )}
        </div>
      )}

      {tab === 'transits' && (
        <div style={{ ...S.card, padding: 0, overflow: 'hidden' }}>
          <TransitTimeline
            chartId={client.natal_chart_id}
            mockMode={!client.natal_chart_id}
            userTier="premium"
          />
        </div>
      )}

      {tab === 'ai' && (
        <div style={S.card}>
          {!aiText && !aiLoading && (
            <button style={S.btn('primary')} onClick={loadAI}>✨ Получить AI-интерпретацию</button>
          )}
          {aiLoading && <div style={S.muted}>Генерирую интерпретацию…</div>}
          {aiText && (() => {
            // Убираем XML-теги <section ...> и </section>, рендерим чистый текст
            const cleaned = aiText
              .replace(/<section[^>]*>/gi, '')
              .replace(/<\/section>/gi, '')
              .trim();
            return (
              <div style={{ fontSize: 14, color: '#e2e8f0', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                {cleaned}
              </div>
            );
          })()}
        </div>
      )}

      {tab === 'notes' && (
        <div style={S.card}>
          <label style={S.label}>Заметки</label>

          {/* Кнопки шаблонов */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, position: 'relative' }}>
            <div style={{ position: 'relative' }}>
              <button style={S.btn()} onClick={() => { setShowTemplateDropdown(v => !v); setShowNewTemplateForm(false); }}>
                📋 Шаблоны
              </button>
              {showTemplateDropdown && (
                <div style={{
                  position: 'absolute', top: '100%', left: 0, zIndex: 100,
                  background: 'var(--crm-card)', border: '1px solid rgba(139,92,246,0.2)', borderRadius: 8,
                  minWidth: 220, padding: 4, marginTop: 4,
                }}>
                  {templates.length === 0 && (
                    <div style={{ padding: '8px 12px', color: '#64748b', fontSize: 13 }}>Нет шаблонов</div>
                  )}
                  {templates.map(tpl => (
                    <div
                      key={tpl.id}
                      style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        padding: '6px 12px', borderRadius: 6,
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = '#334155'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <span
                        onClick={() => {
                          const hasText = notes.trim().length > 0;
                          if (hasText && !window.confirm('Заменить текущие заметки шаблоном?')) return;
                          setNotes(tpl.content);
                          setShowTemplateDropdown(false);
                        }}
                        style={{ cursor: 'pointer', fontSize: 13, color: '#e2e8f0', flex: 1 }}
                      >
                        {tpl.title}
                      </span>
                      <span
                        onClick={async (e) => {
                          e.stopPropagation();
                          if (!window.confirm(`Удалить шаблон "${tpl.title}"?`)) return;
                          try {
                            await authFetch(`/api/v1/note-templates/${tpl.id}`, { method: 'DELETE' });
                            setTemplates(prev => prev.filter(t => t.id !== tpl.id));
                          } catch {}
                        }}
                        style={{ cursor: 'pointer', color: '#64748b', fontSize: 14, padding: '0 4px', marginLeft: 8 }}
                        title="Удалить"
                      >
                        ✕
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button style={S.btn()} onClick={() => { setShowNewTemplateForm(v => !v); setShowTemplateDropdown(false); }}>
              + Новый шаблон
            </button>
          </div>

          {/* Форма нового шаблона */}
          {showNewTemplateForm && (
            <div style={{ background: '#f8f4ff', border: '1px solid rgba(139,92,246,0.2)', borderRadius: 8, padding: 12, marginBottom: 10 }}>
              <input
                style={{ ...S.input, marginBottom: 8 }}
                placeholder="Название шаблона"
                value={newTplTitle}
                onChange={e => setNewTplTitle(e.target.value)}
              />
              <textarea
                style={{ ...S.input, minHeight: 80, resize: 'vertical', marginBottom: 8 }}
                placeholder="Текст шаблона"
                value={newTplContent}
                onChange={e => setNewTplContent(e.target.value)}
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  style={S.btn('primary')}
                  disabled={tplSaving || !newTplTitle.trim()}
                  onClick={async () => {
                    setTplSaving(true);
                    try {
                      const tpl = await authFetch('/api/v1/note-templates', {
                        method: 'POST',
                        body: JSON.stringify({ title: newTplTitle.trim(), content: newTplContent }),
                      });
                      setTemplates(prev => [tpl, ...prev]);
                      setNewTplTitle('');
                      setNewTplContent('');
                      setShowNewTemplateForm(false);
                    } catch {}
                    setTplSaving(false);
                  }}
                >
                  {tplSaving ? 'Сохраняю…' : 'Сохранить шаблон'}
                </button>
                <button style={S.btn()} onClick={() => setShowNewTemplateForm(false)}>Отмена</button>
              </div>
            </div>
          )}

          <div style={{ marginBottom: 8 }}>
            <button style={S.btn()} onClick={() => {
              const d = new Date();
              const stamp = `[${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}] `;
              setNotes(prev => stamp + (prev ? '\n' + prev : ''));
              if (textareaRef.current) textareaRef.current.focus();
            }}>+ запись с датой</button>
          </div>
          <textarea
            ref={textareaRef}
            style={{ ...S.input, minHeight: 120, resize: 'vertical', marginBottom: 12 }}
            value={notes}
            onChange={e => setNotes(e.target.value)}
          />
          <button style={S.btn('primary')} onClick={saveNotes} disabled={notesLoading}>
            {notesLoading ? 'Сохраняю…' : 'Сохранить'}
          </button>
        </div>
      )}

      {tab === 'consultations' && (
        <div style={S.card}>
          <div style={{ ...S.row, marginBottom: 12 }}>
            <label style={S.label}>Консультации</label>
            <button style={S.btn('primary')} onClick={() => setShowConsForm(v => !v)}>
              {showConsForm ? 'Отмена' : '+ Консультация'}
            </button>
          </div>

          {showConsForm && (
            <div style={{ borderTop: '1px solid rgba(139,92,246,0.12)', paddingTop: 12, marginBottom: 16 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                <div>
                  <label style={S.label}>Дата</label>
                  <input style={S.input} type="date" value={consForm.date} onChange={e => setCF('date', e.target.value)} />
                </div>
                <div>
                  <label style={S.label}>Тема</label>
                  <select style={S.input} value={consForm.topic} onChange={e => setCF('topic', e.target.value)}>
                    <option value="">—</option>
                    {['натал', 'соляр', 'хорар', 'синастрия', 'транзиты', 'другое'].map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={S.label}>Стоимость, ₽</label>
                  <input style={S.input} type="number" value={consForm.price} onChange={e => setCF('price', e.target.value)} />
                </div>
                <div>
                  <label style={S.label}>Статус</label>
                  <select style={S.input} value={consForm.status} onChange={e => setCF('status', e.target.value)}>
                    <option value="done">Проведена</option>
                    <option value="planned">Запланирована</option>
                    <option value="canceled">Отменена</option>
                  </select>
                </div>
              </div>
              <label style={S.label}>Заметки</label>
              <textarea
                style={{ ...S.input, minHeight: 80, resize: 'vertical', marginBottom: 12 }}
                value={consForm.notes}
                onChange={e => setCF('notes', e.target.value)}
              />
              {consForm.topic === 'хорар' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12, padding: 12, border: '1px solid rgba(139,92,246,0.2)', borderRadius: 8 }}>
                  <div>
                    <label style={S.label}>Момент вопроса</label>
                    <input style={S.input} type="datetime-local" value={consForm.question_moment} onChange={e => setCF('question_moment', e.target.value)} />
                  </div>
                  <div>
                    <label style={S.label}>Место вопроса</label>
                    <input style={S.input} placeholder="Город, страна" value={consForm.question_place} onChange={e => setCF('question_place', e.target.value)} />
                  </div>
                  <div style={{ gridColumn: '1 / -1', ...S.muted }}>Карта на момент вопроса построится автоматически.</div>
                </div>
              )}
              <label style={S.label}>Домашнее задание (видно клиенту в портале)</label>
              <textarea
                style={{ ...S.input, minHeight: 60, resize: 'vertical', marginBottom: 12 }}
                value={consForm.assignment}
                onChange={e => setCF('assignment', e.target.value)}
              />
              <button style={S.btn('primary')} onClick={saveConsultation} disabled={consSaving}>
                {consSaving ? 'Сохраняю…' : 'Сохранить'}
              </button>
            </div>
          )}

          {consLoading ? (
            <div style={S.muted}>Загрузка…</div>
          ) : consultations.length === 0 ? (
            <div style={S.muted}>Пока нет консультаций.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {consultations.map(c => {
                const badge = ({
                  done: ['Проведена', '#22c55e'],
                  planned: ['Запланирована', '#8b5cf6'],
                  canceled: ['Отменена', '#ef4444'],
                })[c.status] || [c.status, '#64748b'];
                return (
                  <div key={c.id} style={{ border: '1px solid rgba(139,92,246,0.15)', borderRadius: 10, padding: '12px 14px' }}>
                    <div style={{ ...S.row, marginBottom: c.notes ? 8 : 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 600, fontSize: 13 }}>{(c.date || '').slice(0, 10)}</span>
                        {c.topic && <span style={S.muted}>{c.topic}</span>}
                        <span style={{ fontSize: 11, fontWeight: 600, color: badge[1], background: badge[1] + '22', padding: '2px 8px', borderRadius: 6 }}>{badge[0]}</span>
                        {c.price != null && <span style={S.muted}>{c.price} ₽</span>}
                        {c.horary_chart_id && <span style={{ fontSize: 11, fontWeight: 600, color: '#0ea5e9' }}>🕐 хорар-карта</span>}
                      </div>
                      <button style={S.btn('danger')} onClick={() => deleteConsultation(c.id)}>Удалить</button>
                    </div>
                    {c.notes && <div style={{ fontSize: 13, color: 'var(--crm-text)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{c.notes}</div>}
                    {c.assignment && (
                      <div style={{ marginTop: 8, borderLeft: '3px solid #8b5cf6', paddingLeft: 10, fontSize: 13, color: 'var(--crm-text)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: '#8b5cf6' }}>ЗАДАНИЕ · </span>{c.assignment}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Список клиентов ──────────────────────────────────────────────────────────
function ClientList({ clients, allClients, onSelect, onAdd, onDelete, onFilteredClients, authFetch }) {
  const [search, setSearch]           = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [tagFilter, setTagFilter]     = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [showFilter, setShowFilter]   = useState(false);
  const [filterLoading, setFilterLoading] = useState(false);
  const [isFiltered, setIsFiltered]   = useState(false);

  const emptyFilters = { sun_sign: '', moon_sign: '', asc_sign: '', planet: '', house: '' };
  const [filters, setFilters] = useState(emptyFilters);
  const setF = (k, v) => setFilters(p => ({ ...p, [k]: v }));

  const allTags = [...new Set(clients.flatMap(c => c.tags || []))].sort();

  // Локальный поиск по имени/городу + статусу + тегу поверх текущего списка
  const filtered = clients.filter(c =>
    (c.name.toLowerCase().includes(search.toLowerCase()) ||
     c.birth_place.toLowerCase().includes(search.toLowerCase())) &&
    (!statusFilter || c.status === statusFilter) &&
    (!tagFilter || (c.tags || []).includes(tagFilter))
  );

  const exportCSV = () => {
    const cols = ['name', 'birth_date', 'birth_time', 'birth_place', 'status', 'source', 'email', 'tags'];
    const esc = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const lines = [cols.join(',')];
    for (const c of filtered) {
      lines.push(cols.map(k => esc(k === 'tags' ? (c.tags || []).join('; ') : c[k])).join(','));
    }
    const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'clients.csv';
    a.click();
  };

  const handleDelete = async (id) => {
    try {
      await authFetch(`${API}/clients/${id}`, { method: 'DELETE' });
      onDelete(id);
      setDeleteConfirm(null);
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  };

  const applyFilter = async () => {
    const hasFilter = Object.values(filters).some(v => v !== '');
    if (!hasFilter) {
      onFilteredClients(null); // вернуть оригинальный список
      setIsFiltered(false);
      return;
    }
    setFilterLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.sun_sign)  params.set('sun_sign',  filters.sun_sign);
      if (filters.moon_sign) params.set('moon_sign', filters.moon_sign);
      if (filters.asc_sign)  params.set('asc_sign',  filters.asc_sign);
      if (filters.planet)    params.set('planet',    filters.planet);
      if (filters.house)     params.set('house',     filters.house);
      const data = await authFetch(`${API}/clients/search?${params}`);
      onFilteredClients(Array.isArray(data) ? data : []);
      setIsFiltered(true);
    } catch (e) {
      alert('Ошибка фильтрации: ' + e.message);
    } finally {
      setFilterLoading(false);
    }
  };

  const resetFilter = () => {
    setFilters(emptyFilters);
    setShowFilter(false);
    setIsFiltered(false);
    setSearch('');
    onFilteredClients(null);
  };

  const selectStyle = { ...S.input, width: 'auto', minWidth: 120 };

  return (
    <div>
      {/* ── Строка поиска + кнопки ── */}
      <div style={{ ...S.row, marginBottom: 12 }}>
        <input style={{ ...S.input, maxWidth: 260 }} placeholder="Поиск по имени или городу…"
          value={search} onChange={e => setSearch(e.target.value)} />
        <div style={{ display: 'flex', gap: 8 }}>
          <select style={{ ...S.input, width: 'auto', minWidth: 130 }} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="">Все статусы</option>
            {STATUS_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {allTags.length > 0 && (
            <select style={{ ...S.input, width: 'auto', minWidth: 120 }} value={tagFilter} onChange={e => setTagFilter(e.target.value)}>
              <option value="">Все теги</option>
              {allTags.map(t => <option key={t} value={t}>#{t}</option>)}
            </select>
          )}
          <button style={S.btn('ghost')} onClick={exportCSV}>⬇ CSV</button>
          <button style={S.btn(showFilter ? 'primary' : 'ghost')} onClick={() => setShowFilter(v => !v)}>
            🔍 Фильтр по карте
          </button>
          <button style={S.btn('primary')} onClick={onAdd}>+ Добавить клиента</button>
        </div>
      </div>

      {/* ── Панель фильтров ── */}
      {showFilter && (
        <div style={{ ...S.card, marginBottom: 16, display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
          <div>
            <label style={S.label}>Знак Солнца</label>
            <select style={selectStyle} value={filters.sun_sign} onChange={e => setF('sun_sign', e.target.value)}>
              <option value="">Любой</option>
              {ZODIAC_SIGNS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label style={S.label}>Знак Луны</label>
            <select style={selectStyle} value={filters.moon_sign} onChange={e => setF('moon_sign', e.target.value)}>
              <option value="">Любой</option>
              {ZODIAC_SIGNS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label style={S.label}>Знак Асцендента</label>
            <select style={selectStyle} value={filters.asc_sign} onChange={e => setF('asc_sign', e.target.value)}>
              <option value="">Любой</option>
              {ZODIAC_SIGNS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label style={S.label}>Планета</label>
            <select style={selectStyle} value={filters.planet} onChange={e => setF('planet', e.target.value)}>
              <option value="">Любая</option>
              {PLANETS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6 }}>
            <span style={{ ...S.muted, paddingBottom: 8 }}>в</span>
            <div>
              <label style={S.label}>Доме</label>
              <select style={{ ...selectStyle, minWidth: 70 }} value={filters.house} onChange={e => setF('house', e.target.value)}>
                <option value="">Любом</option>
                {HOUSES.map(h => <option key={h} value={h}>{h}</option>)}
              </select>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignSelf: 'flex-end' }}>
            <button style={S.btn('primary')} onClick={applyFilter} disabled={filterLoading}>
              {filterLoading ? 'Ищу…' : 'Применить'}
            </button>
            <button style={S.btn()} onClick={resetFilter}>Сбросить</button>
          </div>
        </div>
      )}

      {/* ── Индикатор активного фильтра ── */}
      {isFiltered && (
        <div style={{ ...S.muted, marginBottom: 12, fontSize: 12 }}>
          Показаны результаты фильтра — {clients.length} кл.
          <button style={{ marginLeft: 8, background: 'none', border: 'none', color: '#7C6CFF', cursor: 'pointer', fontSize: 12 }} onClick={resetFilter}>
            Сбросить
          </button>
        </div>
      )}

      {/* ── Пустые состояния ── */}
      {filtered.length === 0 && (
        <div style={{ ...S.card, color: '#64748b', textAlign: 'center', fontSize: 13 }}>
          {isFiltered
            ? 'По заданным параметрам клиентов не найдено.'
            : clients.length === 0 ? 'Нет клиентов. Добавьте первого.' : 'Ничего не найдено.'}
        </div>
      )}

      {/* ── Карточки ── */}
      {filtered.map(client => (
        <div key={client.id} style={S.card}>
          <div style={S.row}>
            <div style={{ cursor: 'pointer', flexShrink: 0 }} onClick={() => onSelect(client)}>
              <MiniChartPreview clientId={client.id} authFetch={authFetch} />
            </div>
            <div style={{ cursor: 'pointer', flex: 1 }} onClick={() => onSelect(client)}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3, flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{client.name}</span>
                <StatusBadge status={client.status} />
                <BirthdayBadge birthDate={client.birth_date} />
              </div>
              <div style={S.muted}>{client.birth_date} · {client.birth_place}{client.source ? ` · ${client.source}` : ''}</div>
              {client.tags && client.tags.length > 0 && <div style={{ marginTop: 4 }}><TagChips tags={client.tags} /></div>}
            </div>
            <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
              {client.natal_chart_id && (
                <Link
                  to={`/planner/${client.natal_chart_id}`}
                  style={{ ...S.btn('ghost'), textDecoration: 'none', fontSize: 12, padding: '6px 12px', color: '#a78bfa', border: '1px solid #a78bfa40' }}
                >
                  Планер
                </Link>
              )}
              {deleteConfirm === client.id ? (
                <>
                  <button style={{ ...S.btn('danger'), fontSize: 12, padding: '6px 10px' }} onClick={() => handleDelete(client.id)}>Удалить</button>
                  <button style={{ ...S.btn(), fontSize: 12, padding: '6px 10px' }} onClick={() => setDeleteConfirm(null)}>Отмена</button>
                </>
              ) : (
                <button style={{ ...S.btn(), fontSize: 12, padding: '6px 10px' }} onClick={() => setDeleteConfirm(client.id)}>✕</button>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Панель рассылки (021) ────────────────────────────────────────────────────
function BroadcastPanel({ authFetch, clients }) {
  const withEmail = clients.filter(c => c.email);
  const [open, setOpen] = useState(false);
  const [previewClient, setPreviewClient] = useState('');
  const [previewHtml, setPreviewHtml] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [queued, setQueued] = useState(0);
  const [history, setHistory] = useState(null);
  const [aiMode, setAiMode] = useState(false);

  // Бренд + автоотправка (022)
  const [brandName, setBrandName] = useState('');
  const [brandAuto, setBrandAuto] = useState(false);
  const [brandLoaded, setBrandLoaded] = useState(false);
  const [brandSaving, setBrandSaving] = useState(false);

  useEffect(() => {
    if (!open || brandLoaded) return;
    authFetch(`${API}/crm/profile`)
      .then(p => { setBrandName(p.display_name || ''); setBrandAuto(!!p.broadcast_auto); })
      .catch(() => {})
      .finally(() => setBrandLoaded(true));
  }, [open]);

  const saveBrand = async () => {
    setBrandSaving(true);
    try {
      const p = await authFetch(`${API}/crm/profile`, {
        method: 'PATCH',
        body: JSON.stringify({ display_name: brandName, broadcast_auto: brandAuto }),
      });
      setBrandName(p.display_name || '');
      setBrandAuto(!!p.broadcast_auto);
    } catch (e) { alert('Ошибка: ' + (e.message || '')); }
    setBrandSaving(false);
  };

  const doPreview = async () => {
    if (!previewClient) return;
    setPreviewLoading(true); setPreviewHtml('');
    try {
      const r = await authFetch(`${API}/crm/broadcast/preview`, {
        method: 'POST', body: JSON.stringify({ client_id: Number(previewClient), mode: aiMode ? 'ai' : 'template' }),
      });
      setPreviewHtml(r.html || '');
    } catch (e) { alert('Ошибка: ' + (e.message || '')); }
    setPreviewLoading(false);
  };

  const doSend = async () => {
    const label = aiMode ? 'AI-версию прогноза' : 'прогноз месяца';
    if (!window.confirm(`Отправить ${label} ${withEmail.length} клиентам?`)) return;
    setSending(true);
    try {
      const r = await authFetch(`${API}/crm/broadcast/send`, {
        method: 'POST', body: JSON.stringify({ mode: aiMode ? 'ai' : 'template' }),
      });
      setQueued(r.recipients ?? withEmail.length);
    } catch (e) { alert('Ошибка: ' + (e.message || '')); }
    setSending(false);
  };

  const loadHistory = async () => {
    try { const h = await authFetch(`${API}/crm/broadcast/history`); setHistory(Array.isArray(h) ? h : []); }
    catch { setHistory([]); }
  };

  return (
    <div style={{ ...S.card }}>
      <div style={{ ...S.row, cursor: 'pointer' }} onClick={() => setOpen(v => !v)}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>📧 Рассылка месяца</div>
        <div style={S.muted}>{withEmail.length} с email · {open ? '▲' : '▼'}</div>
      </div>

      {open && (
        <div style={{ marginTop: 16, borderTop: '1px solid rgba(139,92,246,0.12)', paddingTop: 16 }}>
          <div style={{ ...S.muted, marginBottom: 12 }}>
            Каждый клиент с указанным email получит персональный прогноз на месяц под вашим именем.
          </div>

          {/* Бренд + автоотправка */}
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 8, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={S.label}>Ваш бренд (имя отправителя)</label>
              <input style={S.input} value={brandName} onChange={e => setBrandName(e.target.value)} placeholder="Например: Астролог Мария" />
            </div>
            <button style={S.btn()} onClick={saveBrand} disabled={brandSaving}>
              {brandSaving ? 'Сохраняю…' : 'Сохранить'}
            </button>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={brandAuto} onChange={e => setBrandAuto(e.target.checked)} />
            Автоотправка 1-го числа каждого месяца (не забудьте «Сохранить»)
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={aiMode} onChange={e => setAiMode(e.target.checked)} />
            AI-версия письма (индивидуальный текст, платно) — иначе шаблонный список транзитов
          </label>

          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 12, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={S.label}>Предпросмотр письма клиента</label>
              <select style={S.input} value={previewClient} onChange={e => setPreviewClient(e.target.value)}>
                <option value="">— выберите клиента —</option>
                {withEmail.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <button style={S.btn()} onClick={doPreview} disabled={!previewClient || previewLoading}>
              {previewLoading ? 'Гружу…' : 'Предпросмотр'}
            </button>
          </div>

          {previewHtml && (
            <iframe
              title="preview"
              srcDoc={previewHtml}
              style={{ width: '100%', height: 420, border: '1px solid rgba(139,92,246,0.2)', borderRadius: 8, marginBottom: 12, background: '#0e0c1a' }}
            />
          )}

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <button style={S.btn('primary')} onClick={doSend} disabled={sending || withEmail.length === 0}>
              {sending ? 'Ставлю в очередь…' : `Отправить прогноз месяца (${withEmail.length})`}
            </button>
            <button style={S.btn()} onClick={loadHistory}>История</button>
            {queued > 0 && <span style={S.muted}>✓ Поставлено в очередь: {queued}</span>}
          </div>

          {history && (
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {history.length === 0 && <div style={S.muted}>Отправок пока не было.</div>}
              {history.map((h, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span>{h.name} · {h.period_ym}</span>
                  <span style={{ color: h.status === 'success' ? '#22c55e' : '#ef4444' }}>
                    {h.status === 'success' ? 'отправлено' : 'ошибка'}{h.sent_at ? ` · ${h.sent_at.slice(0, 10)}` : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Панель анкет (023) ───────────────────────────────────────────────────────
function IntakePanel({ authFetch, onConverted }) {
  const [open, setOpen] = useState(false);
  const [intakes, setIntakes] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newUrl, setNewUrl] = useState('');
  const [copied, setCopied] = useState('');
  const [busyId, setBusyId] = useState(null);

  const load = async () => {
    try { const d = await authFetch(`${API}/crm/intake/list`); setIntakes(Array.isArray(d) ? d : []); }
    catch {}
    setLoaded(true);
  };

  useEffect(() => { if (open && !loaded) load(); }, [open]);

  const createLink = async () => {
    setCreating(true);
    try {
      const r = await authFetch(`${API}/crm/intake/create`, { method: 'POST' });
      setNewUrl(r.url);
      await load();
    } catch (e) { alert('Ошибка: ' + (e.message || '')); }
    setCreating(false);
  };

  const copy = (url) => {
    navigator.clipboard.writeText(url).then(() => { setCopied(url); setTimeout(() => setCopied(''), 2000); });
  };

  const convert = async (id) => {
    setBusyId(id);
    try {
      await authFetch(`${API}/crm/intake/${id}/convert`, { method: 'POST' });
      await load();
      onConverted && onConverted();
    } catch (e) { alert('Ошибка: ' + (e.message || '')); }
    setBusyId(null);
  };

  const remove = async (id) => {
    if (!window.confirm('Удалить анкету?')) return;
    try { await authFetch(`${API}/crm/intake/${id}`, { method: 'DELETE' }); setIntakes(p => p.filter(x => x.id !== id)); }
    catch {}
  };

  const submitted = intakes.filter(i => i.status === 'pending' && i.submitted_at);
  const waiting = intakes.filter(i => i.status === 'pending' && !i.submitted_at);

  return (
    <div style={S.card}>
      <div style={{ ...S.row, cursor: 'pointer' }} onClick={() => setOpen(v => !v)}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>📋 Анкеты клиентов</div>
        <div style={S.muted}>{submitted.length ? `${submitted.length} новых · ` : ''}{open ? '▲' : '▼'}</div>
      </div>

      {open && (
        <div style={{ marginTop: 16, borderTop: '1px solid rgba(139,92,246,0.12)', paddingTop: 16 }}>
          <div style={{ ...S.muted, marginBottom: 12 }}>
            Отправьте клиенту ссылку — он сам заполнит данные рождения, и анкета появится здесь.
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
            <button style={S.btn('primary')} onClick={createLink} disabled={creating}>
              {creating ? 'Создаю…' : '+ Создать ссылку-анкету'}
            </button>
          </div>

          {newUrl && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
              <input style={{ ...S.input, flex: 1, minWidth: 220 }} value={newUrl} readOnly />
              <button style={S.btn()} onClick={() => copy(newUrl)}>{copied === newUrl ? '✓ Скопировано' : 'Копировать'}</button>
            </div>
          )}

          {submitted.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 12 }}>
              {submitted.map(i => {
                const d = i.submitted_data || {};
                return (
                  <div key={i.id} style={{ border: '1px solid rgba(139,92,246,0.2)', borderRadius: 10, padding: '12px 14px' }}>
                    <div style={{ ...S.row, marginBottom: 8 }}>
                      <div>
                        <span style={{ fontWeight: 600, fontSize: 14 }}>{d.name || '—'}</span>
                        <span style={{ ...S.muted, marginLeft: 8 }}>{d.birth_date} · {d.birth_place}</span>
                      </div>
                      <span style={S.muted}>{(i.submitted_at || '').slice(0, 10)}</span>
                    </div>
                    {d.question && <div style={{ fontSize: 13, color: 'var(--crm-text)', marginBottom: 8, whiteSpace: 'pre-wrap' }}>❓ {d.question}</div>}
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button style={S.btn('primary')} onClick={() => convert(i.id)} disabled={busyId === i.id}>
                        {busyId === i.id ? 'Добавляю…' : 'Добавить в клиенты'}
                      </button>
                      <button style={S.btn('danger')} onClick={() => remove(i.id)}>Удалить</button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {waiting.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {waiting.map(i => (
                <div key={i.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, fontSize: 13 }}>
                  <span style={S.muted}>Ожидает заполнения</span>
                  <span style={{ display: 'flex', gap: 8 }}>
                    <button style={S.btn()} onClick={() => copy(i.url)}>{copied === i.url ? '✓' : 'Ссылка'}</button>
                    <button style={S.btn('danger')} onClick={() => remove(i.id)}>✕</button>
                  </span>
                </div>
              ))}
            </div>
          )}

          {loaded && submitted.length === 0 && waiting.length === 0 && !newUrl && (
            <div style={S.muted}>Пока нет анкет.</div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Панель аналитики (09/15/16) ─────────────────────────────────────────────
function StatsPanel({ authFetch, onOpenClient }) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [stats, setStats] = useState(null);
  const [insights, setInsights] = useState(null);
  const [reactivation, setReactivation] = useState([]);

  const load = async () => {
    const now = new Date();
    const from = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
    const to = now.toISOString().slice(0, 10);
    try {
      const [s, i, r] = await Promise.all([
        authFetch(`${API}/crm/stats?from=${from}&to=${to}`),
        authFetch(`${API}/crm/insights`),
        authFetch(`${API}/crm/reactivation`),
      ]);
      setStats(s); setInsights(i); setReactivation(Array.isArray(r) ? r : []);
    } catch {}
    setLoaded(true);
  };
  useEffect(() => { if (open && !loaded) load(); }, [open]);

  const topEntry = (obj) => {
    const e = Object.entries(obj || {});
    return e.length ? e.reduce((a, b) => (b[1] > a[1] ? b : a)) : null;
  };
  const waterPct = () => {
    const me = insights?.moon_elements || {};
    const total = Object.values(me).reduce((a, b) => a + b, 0);
    return total ? Math.round((me['вода'] || 0) / total * 100) : 0;
  };

  const stat = (label, value) => (
    <div style={{ flex: 1, minWidth: 90 }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--crm-text)' }}>{value}</div>
      <div style={S.muted}>{label}</div>
    </div>
  );

  const topSun = insights && topEntry(insights.sun_signs);
  const topTopic = insights?.top_topics?.[0];
  const withReason = reactivation.filter(r => r.reason);

  return (
    <div style={S.card}>
      <div style={{ ...S.row, cursor: 'pointer' }} onClick={() => setOpen(v => !v)}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>📊 Практика</div>
        <div style={S.muted}>{withReason.length ? `${withReason.length} к реактивации · ` : ''}{open ? '▲' : '▼'}</div>
      </div>

      {open && (
        <div style={{ marginTop: 16, borderTop: '1px solid rgba(139,92,246,0.12)', paddingTop: 16 }}>
          {!loaded ? (
            <div style={S.muted}>Загрузка…</div>
          ) : (
            <>
              {/* №9 — цифры */}
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>В цифрах (текущий месяц)</div>
              <div style={{ display: 'flex', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
                {stat('доход, ₽', (stats?.revenue ?? 0).toLocaleString('ru-RU'))}
                {stat('консультаций', stats?.count ?? 0)}
                {stat('средний чек, ₽', (stats?.avg_check ?? 0).toLocaleString('ru-RU'))}
              </div>
              {stats?.by_topic && Object.keys(stats.by_topic).length > 0 && (
                <div style={{ ...S.muted, marginBottom: 18 }}>
                  {Object.entries(stats.by_topic).map(([t, v]) => `${t}: ${v.count}`).join(' · ')}
                </div>
              )}

              {/* №15 — инсайты */}
              <div style={{ fontWeight: 600, fontSize: 13, margin: '4px 0 8px' }}>Инсайты по базе</div>
              <div style={{ ...S.muted, marginBottom: 18, lineHeight: 1.9 }}>
                Клиентов с картой: {insights?.clients_with_chart ?? 0}<br />
                Луна в водных знаках: {waterPct()}%<br />
                {topSun && <>Чаще всего Солнце: {topSun[0]} ({topSun[1]})<br /></>}
                {topTopic && <>Частая тема: {topTopic[0]} ({topTopic[1]})</>}
              </div>

              {/* №16 — реактивация */}
              <div style={{ fontWeight: 600, fontSize: 13, margin: '4px 0 8px' }}>Пора напомнить о себе</div>
              {reactivation.length === 0 ? (
                <div style={S.muted}>Все клиенты недавно на связи.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {reactivation.map((r, i) => (
                    <div
                      key={i}
                      onClick={() => onOpenClient && onOpenClient(r.client_id)}
                      style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
                        padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
                        background: r.reason ? 'rgba(139,92,246,0.08)' : 'rgba(148,163,184,0.06)' }}
                    >
                      <div>
                        <span style={{ fontWeight: 600, fontSize: 13 }}>{r.name}</span>
                        {r.reason && <span style={{ ...S.muted, marginLeft: 8, color: '#a78bfa' }}>повод: {r.reason}</span>}
                      </div>
                      <span style={S.muted}>{r.last_consultation ? `был(а): ${r.last_consultation.slice(0, 10)}` : 'без консультаций'}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Библиотека авторских трактовок (028) ─────────────────────────────────────
function AuthorLibraryPanel({ authFetch }) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ key: '', content: '' });
  const [editId, setEditId] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try { const d = await authFetch(`${API}/astrologer/interpretations`); setItems(Array.isArray(d) ? d : []); }
    catch {}
    setLoaded(true);
  };
  useEffect(() => { if (open && !loaded) load(); }, [open]);

  const save = async () => {
    if (!form.key.trim() || !form.content.trim()) { alert('Заполните ключ и текст'); return; }
    setSaving(true);
    try {
      if (editId) await authFetch(`${API}/astrologer/interpretations/${editId}`, { method: 'PATCH', body: JSON.stringify(form) });
      else await authFetch(`${API}/astrologer/interpretations`, { method: 'POST', body: JSON.stringify(form) });
      setForm({ key: '', content: '' }); setEditId(null);
      await load();
    } catch (e) { alert('Ошибка: ' + (e.message || '')); }
    setSaving(false);
  };

  const edit = (it) => { setForm({ key: it.key, content: it.content }); setEditId(it.id); };
  const cancel = () => { setForm({ key: '', content: '' }); setEditId(null); };
  const remove = async (id) => {
    if (!window.confirm('Удалить трактовку?')) return;
    try { await authFetch(`${API}/astrologer/interpretations/${id}`, { method: 'DELETE' }); setItems(p => p.filter(x => x.id !== id)); }
    catch {}
  };

  return (
    <div style={S.card}>
      <div style={{ ...S.row, cursor: 'pointer' }} onClick={() => setOpen(v => !v)}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>✍️ Мои трактовки</div>
        <div style={S.muted}>{loaded ? `${items.length} · ` : ''}{open ? '▲' : '▼'}</div>
      </div>

      {open && (
        <div style={{ marginTop: 16, borderTop: '1px solid rgba(139,92,246,0.12)', paddingTop: 16 }}>
          <div style={{ ...S.muted, marginBottom: 12 }}>
            Ваши формулировки подмешиваются в AI-разборы (отчёт, бриф, резюме) по совпадению ключей.
            Ключи: <b>planet_sign</b> (sun_taurus), <b>planet_house_N</b> (saturn_house_7), <b>asc_sign</b> (asc_leo). Планеты — по-английски строчными.
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
            <input style={S.input} placeholder="Ключ, напр. saturn_house_7" value={form.key} onChange={e => setForm(p => ({ ...p, key: e.target.value }))} />
            <textarea style={{ ...S.input, minHeight: 80, resize: 'vertical' }} placeholder="Ваш авторский текст трактовки…" value={form.content} onChange={e => setForm(p => ({ ...p, content: e.target.value }))} />
            <div style={{ display: 'flex', gap: 8 }}>
              <button style={S.btn('primary')} onClick={save} disabled={saving}>{saving ? 'Сохраняю…' : (editId ? 'Обновить' : 'Добавить')}</button>
              {editId && <button style={S.btn()} onClick={cancel}>Отмена</button>}
            </div>
          </div>

          {loaded && items.length === 0 ? (
            <div style={S.muted}>Пока нет трактовок.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {items.map(it => (
                <div key={it.id} style={{ border: '1px solid rgba(139,92,246,0.15)', borderRadius: 8, padding: '10px 12px' }}>
                  <div style={{ ...S.row, marginBottom: 6 }}>
                    <span style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 700, color: '#8b5cf6' }}>{it.key}</span>
                    <span style={{ display: 'flex', gap: 6 }}>
                      <button style={S.btn()} onClick={() => edit(it)}>✎</button>
                      <button style={S.btn('danger')} onClick={() => remove(it.id)}>✕</button>
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--crm-text)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{it.content}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Групповой прогноз (18) ───────────────────────────────────────────────────
function GroupForecastPanel({ authFetch, clients }) {
  const withChart = clients.filter(c => c.natal_chart_id);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState({});
  const [planet, setPlanet] = useState('');
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);

  const ids = Object.keys(selected).filter(k => selected[k]).map(Number);
  const toggle = (id) => setSelected(p => ({ ...p, [id]: !p[id] }));
  const PLANETS = [['', 'любая медленная'], ['Jupiter', 'Юпитер'], ['Saturn', 'Сатурн'], ['Uranus', 'Уран'], ['Neptune', 'Нептун'], ['Pluto', 'Плутон']];

  const run = async () => {
    if (!ids.length) { alert('Отметьте клиентов'); return; }
    setRunning(true); setResults(null);
    try {
      const r = await authFetch(`${API}/crm/group-forecast`, { method: 'POST', body: JSON.stringify({ client_ids: ids, planet: planet || null }) });
      setResults(Array.isArray(r) ? r : []);
    } catch (e) { alert('Ошибка: ' + (e.message || '')); }
    setRunning(false);
  };

  return (
    <div style={S.card}>
      <div style={{ ...S.row, cursor: 'pointer' }} onClick={() => setOpen(v => !v)}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>🔮 Групповой прогноз</div>
        <div style={S.muted}>{ids.length ? `${ids.length} выбрано · ` : ''}{open ? '▲' : '▼'}</div>
      </div>

      {open && (
        <div style={{ marginTop: 16, borderTop: '1px solid rgba(139,92,246,0.12)', paddingTop: 16 }}>
          <div style={{ ...S.muted, marginBottom: 12 }}>
            Отметьте клиентов (для групп/марафонов) — покажу, у кого значимый транзит в ближайший месяц.
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
            <select style={{ ...S.input, width: 'auto' }} value={planet} onChange={e => setPlanet(e.target.value)}>
              {PLANETS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <button style={S.btn('primary')} onClick={run} disabled={running || ids.length === 0}>
              {running ? 'Считаю…' : 'Прогноз по выбранным'}
            </button>
            <button style={S.btn()} onClick={() => setSelected(Object.fromEntries(withChart.map(c => [c.id, true])))}>Все</button>
            <button style={S.btn()} onClick={() => setSelected({})}>Сброс</button>
          </div>

          <div style={{ maxHeight: 180, overflowY: 'auto', border: '1px solid rgba(139,92,246,0.12)', borderRadius: 8, padding: 8, marginBottom: 12 }}>
            {withChart.length === 0 ? (
              <div style={S.muted}>Нет клиентов с рассчитанной картой.</div>
            ) : withChart.map(c => (
              <label key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontSize: 13, cursor: 'pointer' }}>
                <input type="checkbox" checked={!!selected[c.id]} onChange={() => toggle(c.id)} />
                {c.name}
              </label>
            ))}
          </div>

          {results && (
            results.length === 0 ? (
              <div style={S.muted}>Ни у кого из выбранных нет значимого транзита в этот период.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {results.map((r, i) => (
                  <div key={i} style={{ border: '1px solid rgba(139,92,246,0.15)', borderRadius: 8, padding: '10px 12px' }}>
                    <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{r.name}</div>
                    {r.events.map((e, j) => (
                      <div key={j} style={S.muted}>{e.event}{e.date ? ` · ${e.date}` : ''}{e.orb != null ? ` · орб ${e.orb}°` : ''}</div>
                    ))}
                  </div>
                ))}
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}

// ─── Главный компонент ────────────────────────────────────────────────────────
export default function CRMPage() {
  const { user, authFetch } = useAuth();
  const [clients, setClients] = useState([]);
  const [filteredClients, setFilteredClients] = useState(null); // null = не фильтровано
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('list'); // 'list' | 'add' | 'card'
  const [selected, setSelected] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [cardTab, setCardTab] = useState('chart');

  const displayedClients = filteredClients ?? clients;

  const loadClients = () =>
    authFetch(`${API}/clients`)
      .then(data => setClients(Array.isArray(data) ? data : []))
      .catch(() => {});

  useEffect(() => {
    loadClients().finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (user?.tier !== 'premium') return;
    authFetch(`${API}/crm/alerts`)
      .then(d => setAlerts(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  const openClientTransits = (clientId) => {
    const c = clients.find(x => x.id === clientId);
    if (!c) return;
    setSelected(c);
    setCardTab('transits');
    setView('card');
  };

  if (user?.tier !== 'premium') {
    return (
      <div className="crm-scope" style={{ ...S.page, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <style>{CRM_THEME_CSS}</style>
        <div style={{ ...S.card, textAlign: 'center', maxWidth: 400 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🔒</div>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>CRM доступен на Premium</div>
          <div style={{ ...S.muted, marginBottom: 16 }}>Управляйте клиентами, стройте их карты и создавайте PDF-отчёты.</div>
          <Link to="/upgrade" style={{ ...S.btn('primary'), textDecoration: 'none', display: 'inline-block' }}>
            Перейти на Premium →
          </Link>
        </div>
      </div>
    );
  }

  if (loading) return <div style={{ ...S.page, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>Загрузка…</div>;

  return (
    <div className="crm-scope" style={S.page}>
      <style>{CRM_THEME_CSS}</style>
      <div style={S.inner}>
        <div style={{ ...S.row, marginBottom: 24 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>👥 Клиенты</h1>
          <div style={S.muted}>{clients.length} клиентов</div>
        </div>

        {view === 'list' && <StatsPanel authFetch={authFetch} onOpenClient={openClientTransits} />}

        {view === 'list' && <GroupForecastPanel authFetch={authFetch} clients={clients} />}

        {view === 'list' && <AuthorLibraryPanel authFetch={authFetch} />}

        {view === 'list' && <IntakePanel authFetch={authFetch} onConverted={loadClients} />}

        {view === 'list' && <BroadcastPanel authFetch={authFetch} clients={clients} />}

        {view === 'list' && alerts.length > 0 && (
          <div style={{ ...S.card, border: '1px solid rgba(139,92,246,0.35)' }}>
            <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 12 }}>⚡ Важные периоды у клиентов</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {alerts.map((a, i) => (
                <div
                  key={i}
                  onClick={() => openClientTransits(a.client_id)}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
                    padding: '10px 12px', borderRadius: 8, background: 'rgba(139,92,246,0.06)', cursor: 'pointer' }}
                >
                  <div>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{a.name}</span>
                    <span style={{ ...S.muted, marginLeft: 8 }}>{a.event}</span>
                  </div>
                  <div style={S.muted}>
                    {(a.exact_date || '').slice(0, 10)}{a.orb != null ? ` · орб ${a.orb}°` : ''}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {view === 'list' && (
          <ClientList
            clients={displayedClients}
            allClients={clients}
            authFetch={authFetch}
            onFilteredClients={data => setFilteredClients(data)}
            onSelect={c => { setSelected(c); setCardTab('chart'); setView('card'); }}
            onAdd={() => setView('add')}
            onDelete={id => {
              setClients(p => p.filter(c => c.id !== id));
              setFilteredClients(p => p ? p.filter(c => c.id !== id) : null);
            }}
          />
        )}

        {view === 'add' && (
          <AddClientForm
            authFetch={authFetch}
            onSave={c => { setClients(p => [...p, c]); setView('list'); }}
            onCancel={() => setView('list')}
          />
        )}

        {view === 'card' && selected && (
          <ClientCard
            client={selected}
            authFetch={authFetch}
            initialTab={cardTab}
            onBack={() => { setSelected(null); setView('list'); }}
            onUpdated={updated => {
              setClients(p => p.map(c => c.id === updated.id ? updated : c));
              setSelected(updated);
            }}
          />
        )}
      </div>
    </div>
  );
}
