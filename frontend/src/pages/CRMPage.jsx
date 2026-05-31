/**
 * CRMPage — управление клиентами для Premium астрологов.
 * Маршрут: /dashboard/clients
 */

import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import NatalChart from '../components/NatalChart';

// ─── Мини-превью карты ────────────────────────────────────────────────────────
function MiniChartPreview({ chartId, authFetch }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!chartId) return;
    setLoading(true);
    authFetch(`/api/v1/clients/${chartId}/chart`)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [chartId]);

  if (!chartId) return null;
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

const S = {
  page: { minHeight: '100vh', background: '#0f172a', color: '#e2e8f0', fontFamily: "'Inter', system-ui, sans-serif", padding: '24px 16px' },
  inner: { maxWidth: 900, margin: '0 auto' },
  card: { background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: '20px 24px', marginBottom: 16 },
  title: { fontSize: 14, fontWeight: 700, margin: '0 0 16px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em' },
  row: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' },
  btn: (v = 'ghost') => ({
    padding: '8px 16px', borderRadius: 8, border: v === 'ghost' ? '1px solid #334155' : 'none', cursor: 'pointer', fontFamily: 'inherit',
    background: v === 'primary' ? 'linear-gradient(135deg,#7C6CFF,#A78BFA)' : v === 'danger' ? '#ef4444' : 'transparent',
    color: v === 'ghost' ? '#94a3b8' : '#fff', fontWeight: 600, fontSize: 13,
  }),
  input: { width: '100%', background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '8px 12px', color: '#e2e8f0', fontSize: 13, fontFamily: 'inherit', boxSizing: 'border-box' },
  muted: { fontSize: 12, color: '#64748b' },
  label: { fontSize: 12, color: '#94a3b8', marginBottom: 4, display: 'block' },
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
  const [transits, setTransits] = useState(null);
  const [notes, setNotes] = useState(client.notes || '');
  const [notesLoading, setNotesLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [tab, setTab] = useState('chart');

  useEffect(() => {
    authFetch(`${API}/clients/${client.id}/chart`).then(setChart).catch(() => {});
  }, [client.id]);

  const loadTransits = () => {
    if (transits) return;
    const today = new Date().toISOString().slice(0, 10);
    const end = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
    authFetch(`${API}/clients/${client.id}/transits?start=${today}&end=${end}`).then(setTransits).catch(() => {});
  };

  const saveNotes = async () => {
    setNotesLoading(true);
    try {
      const updated = await authFetch(`${API}/clients/${client.id}`, { method: 'PATCH', body: JSON.stringify({ notes }) });
      onUpdated(updated);
    } catch {}
    setNotesLoading(false);
  };

  const generateReport = async () => {
    setReportLoading(true);
    try {
      await authFetch(`${API}/clients/${client.id}/report`, { method: 'POST' });
      alert('Отчёт поставлен в очередь — придёт на email.');
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
    setReportLoading(false);
  };

  const tabs = ['chart', 'transits', 'notes'];
  const tabLabels = { chart: '🪐 Карта', transits: '🔮 Транзиты', notes: '📝 Заметки' };

  return (
    <div>
      <div style={{ ...S.row, marginBottom: 16 }}>
        <button style={S.btn()} onClick={onBack}>← Назад</button>
        <button style={S.btn('primary')} onClick={generateReport} disabled={reportLoading}>
          {reportLoading ? 'Создаю…' : '📄 Создать PDF отчёт'}
        </button>
      </div>

      <div style={S.card}>
        <div style={S.row}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 4 }}>{client.name}</div>
            <div style={S.muted}>{client.birth_date}{client.birth_time ? ` · ${client.birth_time}` : ''} · {client.birth_place}</div>
          </div>
        </div>
      </div>

      {/* Вкладки */}
      <div style={{ display: 'flex', gap: 4, background: '#0f172a', borderRadius: 10, padding: 4, marginBottom: 16 }}>
        {tabs.map(t => (
          <button key={t} onClick={() => { setTab(t); if (t === 'transits') loadTransits(); }}
            style={{ flex: 1, padding: '8px 12px', borderRadius: 8, border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 500,
              background: tab === t ? '#1e293b' : 'transparent', color: tab === t ? '#e2e8f0' : '#64748b' }}>
            {tabLabels[t]}
          </button>
        ))}
      </div>

      {tab === 'chart' && (
        <div style={S.card}>
          {chart ? <NatalChart chartData={chart} /> : <div style={S.muted}>Загрузка карты…</div>}
        </div>
      )}

      {tab === 'transits' && (
        <div style={S.card}>
          {!transits ? <div style={S.muted}>Загрузка транзитов…</div> : (
            transits.length === 0
              ? <div style={S.muted}>Нет активных транзитов на ближайшие 30 дней.</div>
              : transits.map((t, i) => (
                <div key={i} style={{ padding: '10px 0', borderBottom: i < transits.length - 1 ? '1px solid #1e293b' : 'none' }}>
                  <div style={{ fontSize: 13, color: '#c4b5fd', fontWeight: 500 }}>{t.planet} {t.aspect} {t.natal_planet}</div>
                  <div style={S.muted}>{t.date} — {t.description}</div>
                </div>
              ))
          )}
        </div>
      )}

      {tab === 'notes' && (
        <div style={S.card}>
          <label style={S.label}>Заметки</label>
          <textarea style={{ ...S.input, minHeight: 120, resize: 'vertical', marginBottom: 12 }}
            value={notes} onChange={e => setNotes(e.target.value)} />
          <button style={S.btn('primary')} onClick={saveNotes} disabled={notesLoading}>
            {notesLoading ? 'Сохраняю…' : 'Сохранить'}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Список клиентов ──────────────────────────────────────────────────────────
function ClientList({ clients, onSelect, onAdd, onDelete, authFetch }) {
  const [search, setSearch] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(null);

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

  return (
    <div>
      <div style={{ ...S.row, marginBottom: 16 }}>
        <input style={{ ...S.input, maxWidth: 300 }} placeholder="Поиск по имени или городу…"
          value={search} onChange={e => setSearch(e.target.value)} />
        <button style={S.btn('primary')} onClick={onAdd}>+ Добавить клиента</button>
      </div>

      {filtered.length === 0 && (
        <div style={{ ...S.card, color: '#64748b', textAlign: 'center', fontSize: 13 }}>
          {clients.length === 0 ? 'Нет клиентов. Добавьте первого.' : 'Ничего не найдено.'}
        </div>
      )}

      {filtered.map(client => (
        <div key={client.id} style={S.card}>
          <div style={S.row}>
            <MiniChartPreview chartId={client.natal_chart_id} authFetch={authFetch} />
            <div style={{ cursor: 'pointer', flex: 1 }} onClick={() => onSelect(client)}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 3 }}>{client.name}</div>
              <div style={S.muted}>{client.birth_date} · {client.birth_place}</div>
            </div>
            <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
              <button style={{ ...S.btn('ghost'), fontSize: 12, padding: '6px 12px', color: '#7C6CFF', border: '1px solid #7C6CFF40' }}
                onClick={() => onSelect(client)}>Открыть</button>
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
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('list'); // 'list' | 'add' | 'card'
  const [selected, setSelected] = useState(null);

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
            clients={clients}
            authFetch={authFetch}
            onSelect={c => { setSelected(c); setView('card'); }}
            onAdd={() => setView('add')}
            onDelete={id => setClients(p => p.filter(c => c.id !== id))}
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
