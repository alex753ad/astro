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

// ─── Мини-превью карты ────────────────────────────────────────────────────────
function MiniChartPreview({ clientId, authFetch }) {
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
      />
    </div>
  );
}

const API = '/api/v1';

const ZODIAC_SIGNS = ['Овен','Телец','Близнецы','Рак','Лев','Дева','Весы','Скорпион','Стрелец','Козерог','Водолей','Рыбы'];
const PLANETS      = ['Sun','Moon','Mercury','Venus','Mars','Jupiter','Saturn','Uranus','Neptune','Pluto'];
const HOUSES       = [1,2,3,4,5,6,7,8,9,10,11,12];

const S = {
  page: { minHeight: '100vh', background: 'transparent', color: '#1e293b', fontFamily: "'Inter', system-ui, sans-serif", padding: '24px 16px' },
  inner: { maxWidth: 900, margin: '0 auto' },
  card: { background: 'rgba(255,255,255,0.85)', border: '1px solid rgba(139,92,246,0.15)', borderRadius: 12, padding: '20px 24px', marginBottom: 16 },
  title: { fontSize: 14, fontWeight: 700, margin: '0 0 16px', color: '#7c3aed', textTransform: 'uppercase', letterSpacing: '0.06em' },
  row: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' },
  btn: (v = 'ghost') => ({
    padding: '8px 16px', borderRadius: 8, border: v === 'ghost' ? '1px solid rgba(139,92,246,0.25)' : 'none', cursor: 'pointer', fontFamily: 'inherit',
    background: v === 'primary' ? 'linear-gradient(135deg,#7C6CFF,#A78BFA)' : v === 'danger' ? '#ef4444' : 'transparent',
    color: v === 'ghost' ? '#7c3aed' : '#fff', fontWeight: 600, fontSize: 13,
  }),
  input: { width: '100%', background: '#f8f4ff', border: '1px solid rgba(139,92,246,0.25)', borderRadius: 8, padding: '8px 12px', color: '#1e293b', fontSize: 13, fontFamily: 'inherit', boxSizing: 'border-box' },
  muted: { fontSize: 12, color: '#94a3b8' },
  label: { fontSize: 12, color: '#7c3aed', marginBottom: 4, display: 'block' },
};

// ─── Форма добавления клиента ─────────────────────────────────────────────────
function AddClientForm({ onSave, onCancel, authFetch }) {
  const [form, setForm] = useState({ name: '', birth_date: '', birth_time: '', birth_place: '', notes: '' });
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
function ClientCard({ client, authFetch, onBack, onUpdated }) {
  const [chart, setChart] = useState(null);
  const [notes, setNotes] = useState(client.notes || '');
  const [notesLoading, setNotesLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [aiText, setAiText] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [tab, setTab] = useState('chart');

  // Редактирование данных клиента
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: client.name, birth_date: client.birth_date, birth_time: client.birth_time || '', birth_place: client.birth_place, notes: client.notes || '' });
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState('');
  const setEF = (k, v) => setEditForm(p => ({ ...p, [k]: v }));

  const saveEdit = async () => {
    setEditLoading(true); setEditError('');
    try {
      const body = { ...editForm };
      if (!body.birth_time) delete body.birth_time;
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

  const tabs = ['chart', 'transits', 'ai', 'notes'];
  const tabLabels = { chart: 'Карта', transits: 'Транзиты', ai: 'AI-интерпретация', notes: 'Заметки' };

  return (
    <div>
      <div style={{ ...S.row, marginBottom: 16 }}>
        <button style={S.btn()} onClick={onBack}>← Назад</button>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
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
            <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 4 }}>{client.name}</div>
            <div style={S.muted}>{client.birth_date}{client.birth_time ? ` · ${client.birth_time}` : ''} · {client.birth_place}</div>
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
            </div>
            {editError && <p style={{ color: '#f87171', fontSize: 12, margin: '0 0 10px' }}>{editError}</p>}
            <button style={S.btn('primary')} onClick={saveEdit} disabled={editLoading}>
              {editLoading ? 'Сохраняю…' : 'Сохранить'}
            </button>
          </div>
        )}
      </div>

      {/* Вкладки */}
      <div style={{ display: 'flex', gap: 4, background: 'rgba(139,92,246,0.08)', borderRadius: 10, padding: 4, marginBottom: 16 }}>
        {tabs.map(t => (
          <button key={t} onClick={() => {
            setTab(t);
            if (t === 'ai' && !aiText) loadAI();
          }}
            style={{ flex: 1, padding: '8px 12px', borderRadius: 8, border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 500,
              background: tab === t ? '#fff' : 'transparent', color: tab === t ? '#7c3aed' : '#64748b' }}>
            {tabLabels[t]}
          </button>
        ))}
      </div>

      {tab === 'chart' && (
        <div style={S.card}>
          {chart ? (
            <>
              <NatalChart planets={chart.planets} houses={chart.houses} aspects={chart.aspects} ascendant={chart.ascendant} midheaven={chart.midheaven} compact={false} />
              <div style={{ borderTop: '1px solid rgba(139,92,246,0.1)', marginTop: 16, paddingTop: 8 }}>
                <ChartSummary planets={chart.planets} ascendant={chart.ascendant} midheaven={chart.midheaven} houses={chart.houses} timeUnknown={!client.birth_time} plain />
              </div>
              <div style={{ borderTop: '1px solid rgba(139,92,246,0.1)', marginTop: 8 }}>
                <AspectTable aspects={chart.aspects} />
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
                  background: '#fff', border: '1px solid rgba(139,92,246,0.2)', borderRadius: 8,
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
    </div>
  );
}

// ─── Список клиентов ──────────────────────────────────────────────────────────
function ClientList({ clients, allClients, onSelect, onAdd, onDelete, onFilteredClients, authFetch }) {
  const [search, setSearch]           = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [showFilter, setShowFilter]   = useState(false);
  const [filterLoading, setFilterLoading] = useState(false);
  const [isFiltered, setIsFiltered]   = useState(false);

  const emptyFilters = { sun_sign: '', moon_sign: '', asc_sign: '', planet: '', house: '' };
  const [filters, setFilters] = useState(emptyFilters);
  const setF = (k, v) => setFilters(p => ({ ...p, [k]: v }));

  // Локальный поиск по имени/городу работает поверх текущего списка
  const filtered = clients.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.birth_place.toLowerCase().includes(search.toLowerCase())
  );

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
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 3 }}>{client.name}</div>
              <div style={S.muted}>{client.birth_date} · {client.birth_place}</div>
            </div>
            <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
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

// ─── Главный компонент ────────────────────────────────────────────────────────
export default function CRMPage() {
  const { user, authFetch } = useAuth();
  const [clients, setClients] = useState([]);
  const [filteredClients, setFilteredClients] = useState(null); // null = не фильтровано
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('list'); // 'list' | 'add' | 'card'
  const [selected, setSelected] = useState(null);

  const displayedClients = filteredClients ?? clients;

  useEffect(() => {
    authFetch(`${API}/clients`)
      .then(data => setClients(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (user?.tier !== 'premium') {
    return (
      <div style={{ ...S.page, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
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
    <div style={S.page}>
      <div style={S.inner}>
        <div style={{ ...S.row, marginBottom: 24 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>👥 Клиенты</h1>
          <div style={S.muted}>{clients.length} клиентов</div>
        </div>

        {view === 'list' && (
          <ClientList
            clients={displayedClients}
            allClients={clients}
            authFetch={authFetch}
            onFilteredClients={data => setFilteredClients(data)}
            onSelect={c => { setSelected(c); setView('card'); }}
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
