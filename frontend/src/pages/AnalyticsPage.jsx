/**
 * AnalyticsPage.jsx
 * Маршрут: /dashboard/analytics  (Premium only)
 * Данные: GET /api/v1/clients/analytics
 */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import useAuth from '../hooks/useAuth';

// ── Константы ────────────────────────────────────────────────────────────────

const SIGN_EMOJI = {
  'Овен': '♈', 'Телец': '♉', 'Близнецы': '♊', 'Рак': '♋',
  'Лев': '♌', 'Дева': '♍', 'Весы': '♎', 'Скорпион': '♏',
  'Стрелец': '♐', 'Козерог': '♑', 'Водолей': '♒', 'Рыбы': '♓',
};

const MONTH_SHORT = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];

// ── Стили (палитра CRMPage) ──────────────────────────────────────────────────

const S = {
  page:    { minHeight: '100vh', background: 'transparent', color: '#1e293b', fontFamily: "'Inter', system-ui, sans-serif", padding: '24px 16px' },
  inner:   { maxWidth: 900, margin: '0 auto' },
  grid:    { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))', gap: 16, marginTop: 24 },
  card:    { background: 'rgba(255,255,255,0.85)', border: '1px solid rgba(139,92,246,0.15)', borderRadius: 12, padding: '20px 24px' },
  label:   { fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: '#7c3aed', marginBottom: 8 },
  bigNum:  { fontSize: 48, fontWeight: 800, lineHeight: 1, color: '#1e293b', margin: '8px 0 4px' },
  sub:     { fontSize: 13, color: '#7C6CFF' },
  muted:   { fontSize: 12, color: '#94a3b8' },
  row:     { display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
};

// ── Горизонтальный бар ───────────────────────────────────────────────────────

function Bar({ label, count, max, emoji }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ ...S.row, marginBottom: 4 }}>
        <span style={{ fontSize: 13, color: '#1e293b' }}>
          {emoji ? `${emoji} ` : ''}{label}
        </span>
        <span style={{ fontSize: 13, fontWeight: 600, color: '#a78bfa' }}>{count}</span>
      </div>
      <div style={{ height: 6, background: '#e9d5ff', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: 'linear-gradient(90deg, #7C6CFF, #A78BFA)',
          borderRadius: 3, transition: 'width 0.5s ease',
        }} />
      </div>
    </div>
  );
}

// ── SVG-спарклайн ────────────────────────────────────────────────────────────

function Sparkline({ data }) {
  if (!data?.length) return null;

  const W = 340, H = 80, PAD = 12;
  const counts = data.map(d => d.count);
  const maxVal = Math.max(...counts, 1);
  const minVal = Math.min(...counts);

  const points = data.map((d, i) => {
    const x = PAD + (i / (data.length - 1 || 1)) * (W - PAD * 2);
    const y = PAD + (1 - (d.count - minVal) / (maxVal - minVal || 1)) * (H - PAD * 2 - 18);
    return { x, y, ...d };
  });

  const polyline = points.map(p => `${p.x},${p.y}`).join(' ');

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible' }}>
      {/* Залитая область */}
      <defs>
        <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#7C6CFF" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#7C6CFF" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={`${points[0].x},${H - 18} ${polyline} ${points[points.length - 1].x},${H - 18}`}
        fill="url(#spark-fill)"
      />
      {/* Линия */}
      <polyline
        points={polyline}
        fill="none"
        stroke="#7C6CFF"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Точки */}
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3" fill="#A78BFA" />
      ))}
      {/* Метки месяцев */}
      {points.map((p, i) => {
        const mo = parseInt(p.month.split('-')[1], 10) - 1;
        return (
          <text key={i} x={p.x} y={H - 2} textAnchor="middle"
            fontSize="9" fill="#64748b">{MONTH_SHORT[mo]}</text>
        );
      })}
    </svg>
  );
}

// ── Карточка-число ───────────────────────────────────────────────────────────

function StatCard({ title, value, sub }) {
  return (
    <div style={S.card}>
      <div style={S.label}>{title}</div>
      <div style={S.bigNum}>{value ?? '—'}</div>
      {sub && <div style={S.sub}>{sub}</div>}
    </div>
  );
}

// ── Главный компонент ────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const { user, authFetch } = useAuth();
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  useEffect(() => {
    authFetch('/api/v1/clients/analytics')
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (user?.tier !== 'premium') {
    return (
      <div style={{ ...S.page, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ ...S.card, textAlign: 'center', maxWidth: 400 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🔒</div>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Аналитика доступна на Premium</div>
          <Link to="/upgrade" style={{ color: '#7C6CFF' }}>Перейти на Premium →</Link>
        </div>
      </div>
    );
  }

  if (loading) return (
    <div style={{ ...S.page, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
      Загрузка…
    </div>
  );

  if (error) return (
    <div style={{ ...S.page, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#f87171' }}>
      Ошибка: {error}
    </div>
  );

  const maxSun  = Math.max(...(data?.top_sun_signs  || []).map(s => s.count), 1);
  const maxCity = Math.max(...(data?.top_cities     || []).map(c => c.count), 1);

  return (
    <div style={S.page}>
      <div style={S.inner}>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>📊 Аналитика</h1>
          <Link to="/dashboard/clients" style={{ fontSize: 13, color: '#64748b', textDecoration: 'none' }}>
            ← Клиенты
          </Link>
        </div>

        <div style={S.grid}>

          {/* Карточка 1 — Всего клиентов */}
          <StatCard
            title="Всего клиентов"
            value={data?.total_clients}
            sub={data?.added_this_month ? `+${data.added_this_month} в этом месяце` : 'нет новых в этом месяце'}
          />

          {/* Карточка 2 — Отчётов создано */}
          <StatCard
            title="Отчётов создано"
            value={data?.reports_generated}
          />

          {/* Карточка 3 — Консультации */}
          <StatCard
            title="Консультаций в этом месяце"
            value={data?.bookings_this_month}
          />

          {/* Карточка 4 — Топ знаков */}
          <div style={S.card}>
            <div style={S.label}>Топ знаков зодиака</div>
            {data?.top_sun_signs?.length
              ? data.top_sun_signs.map(s => (
                  <Bar key={s.sign} label={s.sign} count={s.count} max={maxSun} emoji={SIGN_EMOJI[s.sign]} />
                ))
              : <div style={S.muted}>Нет данных</div>
            }
          </div>

          {/* Карточка 5 — Спарклайн */}
          <div style={S.card}>
            <div style={S.label}>Рост базы клиентов</div>
            <Sparkline data={data?.clients_by_month} />
          </div>

          {/* Карточка 6 — Топ городов */}
          <div style={S.card}>
            <div style={S.label}>Топ городов</div>
            {data?.top_cities?.length
              ? data.top_cities.map(c => (
                  <Bar key={c.city} label={c.city} count={c.count} max={maxCity} />
                ))
              : <div style={S.muted}>Нет данных</div>
            }
          </div>

        </div>
      </div>
    </div>
  );
}
