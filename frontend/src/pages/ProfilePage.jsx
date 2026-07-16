/**
 * ProfilePage — личный кабинет пользователя.
 *
 * Копировать в: frontend/src/pages/ProfilePage.jsx
 *
 * Вкладки:
 *   1. Профиль      — email, тариф, кнопка выйти
 *   2. Мои карты    — список карт, открыть / планер / удалить
 *   3. История      — история интерпретаций и планеров
 *   4. Подписка     — тариф, фичи, управление через Stripe
 *   5. Уведомления  — тогглы (localStorage, до появления API)
 */

import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import { enablePush, pushSupported } from '../push';

// ─── Тёмная тема ──────────────────────────────────────────────────────────────
const PROF_THEME_CSS = `
  .prof-scope { --prof-text:var(--text-primary); --prof-card:rgba(255,255,255,0.85); --prof-title:var(--accent); --prof-muted:var(--text-secondary); --prof-tab-active:var(--bg-card); --prof-tab-color:var(--accent); --prof-tab-muted:var(--text-secondary); --prof-input:var(--accent-muted); --prof-divider:rgba(139,92,246,0.12); --prof-toggle-off:var(--border); --prof-sub:var(--text-secondary); --prof-bar-bg:rgba(139,92,246,0.1); }
  .dark .prof-scope { --prof-card:rgba(26,18,48,0.55); --prof-tab-active:rgba(139,92,246,0.2); --prof-divider:rgba(139,92,246,0.2); --prof-toggle-off:rgba(148,163,184,0.15); }
`;

// ─── Мини-превью натальной карты ─────────────────────────────────────────────
function MiniChartPreview({ chartId, authFetch }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!chartId || !authFetch) return;
    authFetch(`/api/v1/chart/${chartId}`)
      .then(setData)
      .catch(() => {});
  }, [chartId]);

  if (!data) return null;

  const cx = 40, cy = 40, r = 36;
  const planets = data.planets || [];
  const ascLon = data.ascendant?.longitude ?? 0;

  const toXY = (lon) => {
    const a = (180 + (lon - ascLon)) * Math.PI / 180;
    return { x: cx + r * 0.6 * Math.cos(a), y: cy - r * 0.6 * Math.sin(a) };
  };

  /* zodiac data-color, intentional */
  const COLORS = { Sun: '#D4840A', Moon: '#7A8BA0', Mercury: '#7060C0', Venus: '#C04870', Mars: '#B83030', Jupiter: '#3868B0', Saturn: '#6A6050', Uranus: '#2090A8', Neptune: '#6050B8', Pluto: '#902020', 'North Node': '#308858' };
  const GLYPHS = { Sun: '☉', Moon: '☽', Mercury: '☿', Venus: '♀', Mars: '♂', Jupiter: '♃', Saturn: '♄', Uranus: '♅', Neptune: '♆', Pluto: '♇' };
  /* zodiac data-color, intentional */
  const ELEM = ['#FCCFBE','#D4E8C8','#FAF0D0','#C8DCF0','#FCCFBE','#D4E8C8','#FAF0D0','#C8DCF0','#FCCFBE','#D4E8C8','#FAF0D0','#C8DCF0'];

  return (
    <svg viewBox="0 0 80 80" width={80} height={80} style={{ flexShrink: 0 }}>
      {[...Array(12)].map((_, i) => {
        const a1 = (180 + (i * 30 - ascLon)) * Math.PI / 180;
        const a2 = (180 + ((i + 1) * 30 - ascLon)) * Math.PI / 180;
        const x1 = cx + r * Math.cos(a1), y1 = cy - r * Math.sin(a1);
        const x2 = cx + r * Math.cos(a2), y2 = cy - r * Math.sin(a2);
        const ix1 = cx + r * 0.75 * Math.cos(a1), iy1 = cy - r * 0.75 * Math.sin(a1);
        const ix2 = cx + r * 0.75 * Math.cos(a2), iy2 = cy - r * 0.75 * Math.sin(a2);
        return <path key={i} d={`M ${x1} ${y1} A ${r} ${r} 0 0 0 ${x2} ${y2} L ${ix2} ${iy2} A ${r*0.75} ${r*0.75} 0 0 1 ${ix1} ${iy1} Z`} fill={ELEM[i]} stroke="var(--border)" strokeWidth={0.5} />;
      })}
      <circle cx={cx} cy={cy} r={r * 0.75} fill="var(--bg)" stroke="var(--border)" /* zodiac data-color, intentional */ strokeWidth={0.5} />
      <circle cx={cx} cy={cy} r={r * 0.5} fill="var(--bg-card)" stroke="var(--border)" strokeWidth={0.5} />
      {planets.slice(0, 10).map(p => {
        const pos = toXY(p.longitude);
        return (
          <text key={p.name} x={pos.x} y={pos.y} textAnchor="middle" dominantBaseline="central" fontSize={7} fill={COLORS[p.name] || 'var(--text-secondary)'}>
            {GLYPHS[p.name] || '•'}
          </text>
        );
      })}
    </svg>
  );
}

const API_BASE = '/api/v1';

// ─── Цвета тарифов ───────────────────────────────────────────────────────────
const TIER_LABELS = { free: 'Бесплатный', lite: 'Lite', pro: 'Pro', premium: 'Premium' };
/* tier data-color, intentional */
const TIER_COLORS = { free: 'var(--text-secondary)', lite: 'var(--color-air)', pro: 'var(--accent)', premium: 'var(--color-warning)' };

// ─── Стили (светлая и тёмная тема через CSS-переменные) ─────────────────────
const S = {
  page: {
    minHeight: '100vh',
    background: 'transparent',
    color: 'var(--prof-text)',
    fontFamily: "'Inter', system-ui, sans-serif",
    padding: '24px 16px',
  },
  inner: { maxWidth: 680, margin: '0 auto' },
  card: {
    background: 'var(--prof-card)',
    border: '1px solid rgba(139,92,246,0.15)',
    borderRadius: 12,
    padding: '20px 24px',
    marginBottom: 16,
  },
  cardTitle: { fontSize: 14, fontWeight: 700, margin: '0 0 16px', color: 'var(--prof-title)', textTransform: 'uppercase', letterSpacing: '0.06em' },
  tabBar: {
    display: 'flex',
    gap: 2,
    background: 'var(--prof-input)',
    borderRadius: 10,
    padding: 4,
    marginBottom: 24,
    overflowX: 'auto',
  },
  tabBtn: (active) => ({
    flex: '1 0 auto',
    padding: '8px 14px',
    borderRadius: 8,
    border: 'none',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    whiteSpace: 'nowrap',
    fontFamily: 'inherit',
    transition: 'all 0.15s',
    background: active ? 'var(--prof-tab-active)' : 'transparent',
    color: active ? 'var(--prof-tab-color)' : 'var(--prof-tab-muted)',
  }),
  btn: (variant = 'ghost') => ({
    padding: '8px 16px',
    borderRadius: 8,
    border: variant === 'ghost' ? '1px solid var(--border)' : 'none',
    background: variant === 'primary' ? 'var(--accent)'
              : variant === 'danger'  ? 'var(--color-danger)'
              : 'transparent',
    color: variant === 'ghost' ? 'var(--accent)' : '#fff',
    fontWeight: 600,
    fontSize: 13,
    cursor: 'pointer',
    fontFamily: 'inherit',
  }),
  row: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' },
  muted: { fontSize: 12, color: 'var(--prof-muted)' },
  badge: (tier) => ({
    display: 'inline-block',
    padding: '3px 12px',
    borderRadius: 20,
    background: `${TIER_COLORS[tier] || 'var(--text-secondary)'}18`,
    color: TIER_COLORS[tier] || 'var(--text-secondary)',
    fontSize: 12,
    fontWeight: 700,
  }),
};

// ─── Хук: данные профиля ──────────────────────────────────────────────────────
function useProfileData(authFetch) {
  const [charts,          setCharts]          = useState([]);
  const [primaryChartId,  setPrimaryChartId]  = useState(null);
  const [history,         setHistory]         = useState([]);
  const [subscription,    setSubscription]    = useState(null);
  const [loading,         setLoading]         = useState({ charts: true, history: true, sub: true });

  useEffect(() => {
    authFetch(`${API_BASE}/profile/charts`)
      .then(d => {
        setCharts(d.charts || []);
        setPrimaryChartId(d.primary_chart_id || null);
      })
      .catch(() => {})
      .finally(() => setLoading(p => ({ ...p, charts: false })));

    authFetch(`${API_BASE}/profile/history`)
      .then(d => setHistory(d.history || []))
      .catch(() => {})
      .finally(() => setLoading(p => ({ ...p, history: false })));

    authFetch(`${API_BASE}/profile/subscription`)
      .then(d => setSubscription(d))
      .catch(() => {})
      .finally(() => setLoading(p => ({ ...p, sub: false })));
  }, [authFetch]);

  return { charts, setCharts, primaryChartId, setPrimaryChartId, history, subscription, loading };
}

// ─── Уведомления теперь на сервере (см. TabNotifications ниже) ─────────────────

// ─── Toggle компонент ─────────────────────────────────────────────────────────
function Toggle({ checked, onChange }) {
  return (
    <div
      onClick={onChange}
      style={{
        width: 40, height: 22, borderRadius: 11, cursor: 'pointer',
        background: checked ? 'var(--accent)' : 'var(--prof-toggle-off)',
        position: 'relative', transition: 'background 0.2s', flexShrink: 0,
      }}
    >
      <div style={{
        position: 'absolute', top: 3,
        left: checked ? 21 : 3,
        width: 16, height: 16, borderRadius: '50%',
        background: 'var(--bg-card)', transition: 'left 0.2s',
      }} />
    </div>
  );
}

// ─── Вкладка: Профиль ─────────────────────────────────────────────────────────
function TabProfile({ user, logout, authFetch }) {
  const [switching, setSwitching] = useState(null);

  const setTier = async (tier) => {
    setSwitching(tier);
    try {
      await authFetch(`${API_BASE}/payments/admin/set-tier`, {
        method: 'POST',
        body: JSON.stringify({ tier }),
      });
      // обновляем user в localStorage чтобы tier подхватился после reload
      const stored = JSON.parse(localStorage.getItem('astro_user') || 'null');
      if (stored) {
        stored.tier = tier;
        localStorage.setItem('astro_user', JSON.stringify(stored));
      }
      window.location.reload();
    } catch (e) {
      alert('Ошибка: ' + e.message);
      setSwitching(null);
    }
  };

  const isAdmin = ['e.onosov@mail.ru', 'lycoris77@ya.ru'].includes(user?.email?.toLowerCase());

  return (
    <div style={S.card}>
      <p style={S.cardTitle}>Аккаунт</p>
      <div style={S.row}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6 }}>{user?.email}</div>
          <span style={S.badge(user?.tier)}>{TIER_LABELS[user?.tier] || user?.tier}</span>
          {user?.google_sub && (
            <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--prof-muted)' }}>Google</span>
          )}
        </div>
        <button style={S.btn('ghost')} onClick={logout}>Выйти</button>
      </div>

      {isAdmin && (
        <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--prof-divider)' }}>
          <div style={{ fontSize: 11, color: 'var(--prof-muted)', marginBottom: 8 }}>🔧 Тестовый тариф</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {['free', 'lite', 'pro', 'premium'].map(t => (
              <button
                key={t}
                onClick={() => setTier(t)}
                disabled={!!switching || user?.tier === t}
                style={{
                  ...S.btn(user?.tier === t ? 'primary' : 'ghost'),
                  fontSize: 12,
                  padding: '5px 12px',
                  opacity: switching && switching !== t ? 0.5 : 1,
                }}
              >
                {switching === t ? '...' : t}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Вкладка: Мои карты ───────────────────────────────────────────────────────
function TabCharts({ charts, setCharts, primaryChartId, setPrimaryChartId, loading, authFetch, subscription, user }) {
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [settingPrimary, setSettingPrimary] = useState(null);
  const [addingToClients, setAddingToClients] = useState(null); // chart.id в процессе
  const [addedToClients, setAddedToClients] = useState({}); // chart.id -> true

  const handleAddToClients = async (chart) => {
    setAddingToClients(chart.id);
    try {
      await authFetch(`${API_BASE}/clients`, {
        method: 'POST',
        body: JSON.stringify({
          name: chart.name || chart.birth_place,
          birth_date: chart.birth_date,
          birth_time: chart.birth_time || null,
          birth_place: chart.birth_place,
          natal_chart_id: chart.id,
        }),
      });
      setAddedToClients(prev => ({ ...prev, [chart.id]: true }));
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setAddingToClients(null);
    }
  };

  // Счётчик карт для free
  const isFree = !user?.tier || user?.tier === 'free';
  const chartsLimit = subscription?.limits?.charts_per_month ?? null;
  const chartsUsed = subscription?.usage?.charts_this_month ?? 0;
  const chartsLeft = isFree && chartsLimit !== null ? Math.max(0, chartsLimit - chartsUsed) : null;

  const handleDelete = async (id) => {
    try {
      await authFetch(`${API_BASE}/profile/charts/${id}`, { method: 'DELETE' });
      setCharts(prev => prev.filter(c => c.id !== id));
      if (primaryChartId === id) setPrimaryChartId(null);
      setDeleteConfirm(null);
    } catch (e) {
      alert('Не удалось удалить: ' + e.message);
    }
  };

  const handleSetPrimary = async (id) => {
    setSettingPrimary(id);
    try {
      await authFetch(`${API_BASE}/profile/primary-chart`, {
        method: 'PATCH',
        body: JSON.stringify({ chart_id: id }),
      });
      setPrimaryChartId(id);
    } catch (e) {
      alert('Не удалось сменить главную карту: ' + e.message);
    } finally {
      setSettingPrimary(null);
    }
  };

  const LimitBanner = () => isFree && chartsLeft !== null ? (
    <div style={{
      padding: '12px 16px', borderRadius: 12,
      background: chartsLeft === 0 ? 'rgba(220,38,38,0.08)' : 'var(--accent-muted)',
      border: `1px solid ${chartsLeft === 0 ? 'rgba(220,38,38,0.2)' : 'rgba(139,92,246,0.2)'}`,
      fontSize: 13, color: chartsLeft === 0 ? 'var(--color-danger)' : 'var(--accent)', fontWeight: 600,
      display: 'flex', alignItems: 'center', gap: 8,
    }}>
      <span>{chartsLeft === 0 ? '🔒' : '🗂'}</span>
      {chartsLeft === 0
        ? 'Лимит карт на этот месяц исчерпан. Обновится 1-го числа.'
        : `Осталось карт в этом месяце: ${chartsLeft} из ${chartsLimit}`}
    </div>
  ) : null;

  if (loading) return <div style={{ color: 'var(--prof-muted)', fontSize: 13 }}>Загрузка…</div>;
  if (!charts.length) return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <LimitBanner />
      <div style={{ ...S.card, textAlign: 'center', color: 'var(--prof-muted)', fontSize: 13 }}>
        Нет сохранённых карт.<br />
        <Link to="/home" style={{ color: 'var(--prof-title)', marginTop: 8, display: 'inline-block' }}>
          Создать карту →
        </Link>
      </div>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <LimitBanner />
      {[...charts].sort((a, b) => (b.id === primaryChartId ? 1 : 0) - (a.id === primaryChartId ? 1 : 0)).map(chart => {
        const isPrimary = chart.id === primaryChartId;
        return (
          <div
            key={chart.id}
            style={{
              ...S.card,
              border: isPrimary
                ? '1px solid rgba(124,108,255,0.5)'
                : '1px solid rgba(139,92,246,0.15)',
            }}
          >
            {/* Шапка карточки: булавка у главной */}
            {isPrimary && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                marginBottom: 10,
                fontSize: 11, fontWeight: 700,
                color: 'var(--prof-title)', letterSpacing: '0.05em', textTransform: 'uppercase',
              }}>
                <span style={{ fontSize: 14 }}>📌</span> Главная карта
              </div>
            )}

            <div style={S.row}>
              <Link to={`/chart/${chart.id}`} style={{ flexShrink: 0, display: 'block' }}>
                <MiniChartPreview chartId={chart.id} authFetch={authFetch} />
              </Link>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 3 }}>{chart.birth_place}</div>
                <div style={S.muted}>
                  {chart.birth_date}
                  {chart.birth_time ? ` · ${chart.birth_time}` : ' · время неизвестно'}
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0, alignItems: 'flex-end' }}>
                <div style={{ display: 'flex', gap: 6 }}>
                  <Link
                    to={`/planner/${chart.id}`}
                    style={{ ...S.btn('ghost'), textDecoration: 'none', fontSize: 12, padding: '6px 12px', color: 'var(--accent-glow)', border: '1px solid var(--border)' }}
                  >
                    Планер
                  </Link>
                  {user?.tier === 'premium' && (
                    <button
                      disabled={addingToClients === chart.id || addedToClients[chart.id]}
                      onClick={() => handleAddToClients(chart)}
                      style={{ ...S.btn('ghost'), fontSize: 12, padding: '6px 12px', color: 'var(--color-warning)', border: '1px solid var(--border)' }}
                    >
                      {addingToClients === chart.id ? '…' : addedToClients[chart.id] ? 'Добавлено' : 'в Клиенты'}
                    </button>
                  )}
                  {deleteConfirm === chart.id ? (
                    <>
                      <button style={{ ...S.btn('danger'), fontSize: 12, padding: '6px 10px' }} onClick={() => handleDelete(chart.id)}>Удалить</button>
                      <button style={{ ...S.btn('ghost'), fontSize: 12, padding: '6px 10px' }} onClick={() => setDeleteConfirm(null)}>Отмена</button>
                    </>
                  ) : (
                    <button style={{ ...S.btn('ghost'), fontSize: 12, padding: '6px 10px' }} onClick={() => setDeleteConfirm(chart.id)}>✕</button>
                  )}
                </div>
                {/* Кнопка "Сделать главной" — только для не-главных карт */}
                {!isPrimary && charts.length > 1 && (
                  <button
                    disabled={settingPrimary === chart.id}
                    onClick={() => handleSetPrimary(chart.id)}
                    style={{
                      ...S.btn('ghost'),
                      fontSize: 11,
                      padding: '4px 10px',
                      color: 'var(--prof-muted)',
                      border: '1px solid rgba(148,163,184,0.25)',
                      opacity: settingPrimary === chart.id ? 0.6 : 1,
                    }}
                  >
                    {settingPrimary === chart.id ? '…' : 'Сделать главной'}
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Вкладка: История ─────────────────────────────────────────────────────────
function TabHistory({ history, loading }) {
  if (loading) return <div style={{ color: 'var(--prof-muted)', fontSize: 13 }}>Загрузка…</div>;
  if (!history.length) return (
    <div style={{ ...S.card, color: 'var(--prof-muted)', fontSize: 13, textAlign: 'center' }}>
      История пуста — прогнозы появятся здесь после генерации.
    </div>
  );

  const ENGINE_LABEL = { gpt4o: 'GPT-4o', deepseek: 'DeepSeek', anthropic: 'Claude', template: 'Шаблон' };
  const ENGINE_COLOR = { gpt4o: 'var(--color-success)', deepseek: 'var(--color-air)', anthropic: 'var(--accent-glow)', template: 'var(--text-secondary)' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {history.map(item => (
        <div key={item.id} style={S.card}>
          <div style={S.row}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, color: 'var(--prof-sub)', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.preview || '—'}
              </div>
              <div style={S.muted}>
                {item.created_at ? new Date(item.created_at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              {item.engine && (
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, background: `${ENGINE_COLOR[item.engine] || 'var(--text-secondary)'}20`, color: ENGINE_COLOR[item.engine] || 'var(--text-secondary)' }}>
                  {ENGINE_LABEL[item.engine] || item.engine}
                </span>
              )}
              <Link
                to={`/chart/${item.chart_id}`}
                style={{ fontSize: 12, color: 'var(--prof-title)', textDecoration: 'none' }}
              >
                К карте →
              </Link>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Вкладка: Подписка ────────────────────────────────────────────────────────
const TIERS = [
  { id: 'lite',    label: 'Lite',    price: '790 ₽/мес',   desc: 'Интерпретации, транзиты, лунный календарь' },
  { id: 'pro',     label: 'Pro',     price: '1 990 ₽/мес', desc: 'AI-транзиты, RAG-чат, PDF-отчёты' },
  { id: 'premium', label: 'Premium', price: '7 990 ₽/мес', desc: 'Всё включено + брендирование астролога' },
];

const TIER_ORDER = ['free', 'lite', 'pro', 'premium'];

function UsageBar({ label, used, limit, tierColor = 'var(--accent)' }) {
  // limit === null / undefined → безлимит
  const unlimited = limit === null || limit === undefined;
  const pct = unlimited ? 0 : Math.min(100, Math.round((used / Math.max(1, limit)) * 100));
  const exhausted = !unlimited && used >= limit;
  const barColor = exhausted ? 'var(--color-danger)' : (pct >= 80 ? 'var(--color-warning)' : tierColor);

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
        <span style={{ fontSize: 12, color: 'var(--accent-glow)' }}>{label}</span>
        <span style={{ fontSize: 12, color: exhausted ? 'var(--color-danger)' : 'var(--text-secondary)', fontWeight: 600 }}>
          {unlimited ? `${used} · безлимит` : `${used} / ${limit}`}
        </span>
      </div>
      <div style={{ height: 6, borderRadius: 4, background: 'var(--prof-bar-bg)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: unlimited ? '100%' : `${pct}%`,
          background: unlimited ? `${tierColor}40` : barColor,
          borderRadius: 4, transition: 'width 0.3s',
        }} />
      </div>
    </div>
  );
}

function TabSubscription({ user, subscription, loading, authFetch }) {
  const [portalLoading, setPortalLoading] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState(null);
  const [checkoutError, setCheckoutError] = useState(null);

  const handlePortal = async () => {
    setPortalLoading(true);
    try {
      const data = await authFetch(`${API_BASE}/payments/portal`, {
        method: 'POST',
        body: JSON.stringify({ return_url: window.location.href }),
      });
      window.location.href = data.url || data.portal_url;
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setPortalLoading(false);
    }
  };

  const handleCheckout = async (tier) => {
    setCheckoutLoading(tier);
    setCheckoutError(null);
    try {
      const data = await authFetch(`${API_BASE}/payments/checkout`, {
        method: 'POST',
        body: JSON.stringify({
          tier,
          billing_period: 'monthly',
          success_url: window.location.origin + '/profile',
          cancel_url: window.location.href,
        }),
      });
      window.location.href = data.checkout_url;
    } catch (e) {
      setCheckoutError(e.message);
      setCheckoutLoading(null);
    }
  };

  const features = [
    { label: 'Транзиты',              key: 'transits' },
    { label: 'Безлим. интерпретации', key: 'unlimited_interpretations' },
    { label: 'История',               key: 'history' },
    { label: 'PDF-отчёты',            key: 'pdf_reports' },
    { label: 'Синастрия',             key: 'synastry' },
  ];

  if (loading) return <div style={{ color: 'var(--prof-muted)', fontSize: 13 }}>Загрузка…</div>;

  const currentTierIdx = TIER_ORDER.indexOf(user?.tier || 'free');
  const availableTiers = TIERS.filter(t => TIER_ORDER.indexOf(t.id) > currentTierIdx);

  return (
    <div>
      {/* Текущий тариф */}
      <div style={S.card}>
        <p style={S.cardTitle}>Текущий тариф</p>
        <div style={S.row}>
          <div>
            <span style={S.badge(user?.tier)}>{TIER_LABELS[user?.tier] || user?.tier}</span>
            {subscription?.current_period_end && (
              <div style={{ ...S.muted, marginTop: 6 }}>
                Следующее списание: {new Date(subscription.current_period_end).toLocaleDateString('ru-RU')}
              </div>
            )}
          </div>
          {subscription?.status && subscription.status !== 'free' && (
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, background: 'rgba(52,211,153,0.12)', color: 'var(--color-success)' }}>
              {subscription.status === 'active' ? 'Активна' : subscription.status}
            </span>
          )}
        </div>
      </div>

      {/* Фичи */}
      <div style={S.card}>
        <p style={S.cardTitle}>Что включено</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8 }}>
          {features.map(f => {
            const ok = subscription?.features?.[f.key];
            return (
              <div key={f.key} style={{ padding: '10px 12px', borderRadius: 8, border: `1px solid ${ok ? 'var(--border)' : 'var(--border)'}`, textAlign: 'center', opacity: ok ? 1 : 0.5 }}>
                <div style={{ fontSize: 16, marginBottom: 4 }}>{ok ? '✓' : '✗'}</div>
                <div style={{ fontSize: 11, color: ok ? 'var(--accent-glow)' : 'var(--text-secondary)' }}>{f.label}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Использование в этом месяце */}
      {subscription && (() => {
        const lim = subscription.limits || {};
        const use = subscription.usage || {};
        const feat = subscription.features || {};
        const tier = user?.tier || 'free';
        const tierColor = TIER_COLORS[tier] || 'var(--accent)';

        const interpLimit = lim.interpretations_per_month;   // 0 у free, число у lite, 15/100 pro/premium
        const interpUsed = use.ai_interpretations_this_month ?? 0;
        const chartsLimit = lim.charts_per_month;             // null = безлимит
        const chartsUsed = use.charts_this_month ?? 0;
        const transitAiLimit = lim.transits_ai_per_month;     // 3 у lite, null у pro/premium, 0 у free
        const transitAiUsed = use.transit_ai_this_month ?? 0;

        // Free: показываем статус бесплатной интерпретации отдельно
        const freeInterpAvailable = feat.first_interpretation_available;

        // Pro/Premium — интерпретации безлимитны
        const interpUnlimited = feat.unlimited_interpretations;

        return (
          <div style={S.card}>
            <p style={S.cardTitle}>Использование в этом месяце</p>

            {tier === 'free' ? (
              <div style={{ fontSize: 13, color: 'var(--accent-glow)', marginBottom: 12 }}>
                {freeInterpAvailable
                  ? '🎁 У вас есть 1 бесплатная интерпретация карты'
                  : '✓ Бесплатная интерпретация использована'}
              </div>
            ) : (
              <UsageBar
                label="AI-интерпретации"
                used={interpUsed}
                limit={interpUnlimited ? null : interpLimit}
                tierColor={tierColor}
              />
            )}

            {/* AI-транзиты показываем только там, где есть квота (lite) или безлимит (pro/premium) */}
            {(transitAiLimit === null || transitAiLimit > 0) && (
              <UsageBar
                label="AI-расшифровки транзитов"
                used={transitAiUsed}
                limit={transitAiLimit}
                tierColor={tierColor}
              />
            )}

            <UsageBar
              label="Построение карт"
              used={chartsUsed}
              limit={chartsLimit}
              tierColor={tierColor}
            />

            {/* Мягкий апсейл при исчерпании */}
            {tier !== 'premium' && !interpUnlimited && interpLimit > 0 && interpUsed >= interpLimit && (
              <div style={{ fontSize: 12, color: 'var(--color-warning)', marginTop: 4 }}>
                Лимит интерпретаций исчерпан — перейдите на тариф выше, чтобы продолжить.
              </div>
            )}
          </div>
        );
      })()}

      {/* Доступные тарифы для апгрейда */}
      {availableTiers.length > 0 && (
        <div style={S.card}>
          <p style={S.cardTitle}>Перейти на тариф</p>
          {checkoutError && (
            <div style={{ fontSize: 12, color: 'var(--color-danger)', marginBottom: 12 }}>Ошибка: {checkoutError}</div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {availableTiers.map(t => (
              <div key={t.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '12px 14px', borderRadius: 8, border: `1px solid ${TIER_COLORS[t.id]}30`, background: `${TIER_COLORS[t.id]}08` }}>
                <div>
                  <span style={{ ...S.badge(t.id), marginRight: 8 }}>{t.label}</span>
                  <span style={{ fontSize: 13, color: 'var(--prof-muted)' }}>{t.price}</span>
                  <div style={{ fontSize: 11, color: 'var(--prof-muted)', marginTop: 3 }}>{t.desc}</div>
                </div>
                <button
                  onClick={() => handleCheckout(t.id)}
                  disabled={!!checkoutLoading}
                  style={{ ...S.btn('primary'), whiteSpace: 'nowrap', opacity: checkoutLoading && checkoutLoading !== t.id ? 0.5 : 1 }}
                >
                  {checkoutLoading === t.id ? 'Открываю…' : `Перейти →`}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Управление подпиской через Stripe Portal */}
      {user?.tier !== 'free' && (
        <div style={S.card}>
          <button onClick={handlePortal} disabled={portalLoading} style={S.btn('ghost')}>
            {portalLoading ? 'Открываю…' : 'Управление подпиской (Stripe) →'}
          </button>
        </div>
      )}

      {/* CRM для premium */}
      {user?.tier === 'premium' && (
        <div style={{ ...S.card, border: '1px solid rgba(217,119,6,0.3)', background: 'rgba(217,119,6,0.05)' }}>
          <p style={S.cardTitle}>👥 CRM — Управление клиентами</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8, marginBottom: 16 }}>
            {[
              { icon: '➕', label: 'Добавить клиента' },
              { icon: '🪐', label: 'Натальная карта' },
              { icon: '🔮', label: 'Транзиты клиента' },
              { icon: '📄', label: 'PDF-отчёт' },
              { icon: '📝', label: 'Заметки' },
              { icon: '🔍', label: 'Поиск по базе' },
            ].map(f => (
              <div key={f.label} style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border)', textAlign: 'center' }}>
                <div style={{ fontSize: 18, marginBottom: 4 }}>{f.icon}</div>
                <div style={{ fontSize: 11, color: 'var(--color-warning)' }}>{f.label}</div>
              </div>
            ))}
          </div>
          <Link to="/dashboard/clients" style={{ ...S.btn('primary'), textDecoration: 'none', display: 'inline-block', background: 'var(--color-warning)' }}>
            Открыть CRM →
          </Link>
        </div>
      )}
    </div>
  );
}

// ─── Вкладка: Пригласи друга ─────────────────────────────────────────────────
function TabReferral({ authFetch }) {
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    authFetch(`${API_BASE}/profile/referral`)
      .then(setData)
      .catch(() => {});
  }, [authFetch]);

  const copy = () => {
    if (!data?.ref_url) return;
    navigator.clipboard.writeText(data.ref_url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!data) return <div style={{ color: 'var(--prof-muted)', fontSize: 13 }}>Загрузка…</div>;

  return (
    <div>
      <div style={S.card}>
        <p style={S.cardTitle}>Пригласи друга</p>
        <p style={{ fontSize: 13, color: 'var(--prof-muted)', marginBottom: 16 }}>
          Когда приглашённый оплатит подписку — ты получишь <strong style={{ color: 'var(--accent-glow)' }}>2 недели Pro бесплатно</strong>.
        </p>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--prof-muted)', marginBottom: 6 }}>Твоя реферальная ссылка</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              readOnly
              value={data.ref_url || '—'}
              style={{ flex: 1, background: 'var(--bg-deeper)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit' }}
            />
            <button style={S.btn('primary')} onClick={copy}>
              {copied ? '✓ Скопировано' : 'Копировать'}
            </button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ background: 'var(--bg-deeper)', borderRadius: 10, padding: '14px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--accent-glow)' }}>{data.referrals_count ?? 0}</div>
            <div style={{ fontSize: 12, color: 'var(--prof-muted)', marginTop: 4 }}>Приглашено</div>
          </div>
          <div style={{ background: 'var(--bg-deeper)', borderRadius: 10, padding: '14px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--color-success)' }}>{data.reward_weeks_earned ?? 0} нед.</div>
            <div style={{ fontSize: 12, color: 'var(--prof-muted)', marginTop: 4 }}>Бонус получено</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Вкладка: Уведомления ────────────────────────────────────────────────────
function TabNotifications({ authFetch }) {
  const [settings, setSettings] = useState(null);
  const [msg, setMsg] = useState('');
  const [permStatus, setPermStatus] = useState(() => {
    if (typeof Notification === 'undefined') return 'unsupported';
    return Notification.permission;
  });

  useEffect(() => {
    if (!authFetch) return;
    authFetch(`${API_BASE}/push/settings`)
      .then(setSettings)
      .catch(() => setSettings({
        daily_forecast: true, daily_time: '08:00', planner: true, key_transits: true,
      }));
  }, [authFetch]);

  const patch = async (partial) => {
    setSettings(prev => ({ ...prev, ...partial }));
    try {
      const saved = await authFetch(`${API_BASE}/push/settings`, {
        method: 'PATCH',
        body: JSON.stringify(partial),
      });
      setSettings(saved);
    } catch (_) { /* тихо */ }
  };

  const toggle = async (key) => {
    const turningOn = !settings[key];
    patch({ [key]: turningOn });
    if (!turningOn) return;
    if (permStatus === 'denied') return;
    try {
      await enablePush(authFetch);
      setPermStatus('granted');
    } catch (_) {
      const p = typeof Notification !== 'undefined' ? Notification.permission : 'unsupported';
      setPermStatus(p);
    }
  };

  if (!settings) {
    return (
      <div style={S.card}>
        <p style={S.cardTitle}>Push-уведомления</p>
        <div style={S.muted}>Загрузка…</div>
      </div>
    );
  }

  const items = [
    { key: 'daily_forecast', label: 'Ежедневный прогноз', desc: `Каждый день в ${settings.daily_time || '08:00'}`, time: true },
    { key: 'planner',        label: 'Планер',             desc: 'При старте нового периода планеты' },
    { key: 'key_transits',   label: 'Важные транзиты',    desc: 'Когда начинается значимый транзит' },
    { key: 'moon_phases',    label: 'Новолуние и полнолуние', desc: 'Напоминание за день' },
  ];

  return (
    <div style={S.card}>
      <p style={S.cardTitle}>Push-уведомления</p>
      {!pushSupported() && (
        <div style={{ ...S.muted, marginBottom: 12 }}>
          ⚠️ Этот браузер не поддерживает push-уведомления.
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {items.map((item, i) => (
          <div key={item.key}>
            <div style={{ ...S.row, padding: '12px 0' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>{item.label}</div>
                <div style={S.muted}>{item.desc}</div>
                {item.time && settings.daily_forecast && (
                  <input
                    type="time"
                    value={settings.daily_time || '08:00'}
                    onChange={(e) => patch({ daily_time: e.target.value })}
                    style={{
                      marginTop: 8, background: 'var(--bg-deeper)', color: 'var(--text-primary)',
                      border: '1px solid var(--border)', borderRadius: 8, padding: '6px 10px', fontSize: 14,
                    }}
                  />
                )}
              </div>
              <Toggle checked={!!settings[item.key]} onChange={() => toggle(item.key)} />
            </div>
            <div style={{ borderBottom: '1px solid var(--border)' }} />
          </div>
        ))}
      </div>

      {permStatus === 'denied' && (
        <div style={{ ...S.muted, marginTop: 12, fontSize: 12 }}>
          Уведомления отключены в настройках браузера. Разрешите их там — и тумблеры заработают.
        </div>
      )}
      <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <button
          onClick={async () => {
            try {
              setMsg('');
              await enablePush(authFetch);
              setPermStatus('granted');
              await authFetch(`${API_BASE}/push/test`, { method: 'POST' });
              setMsg('Тестовое уведомление отправлено');
            } catch (e) {
              setMsg(e.message || 'Не удалось отправить тест');
            }
          }}
          style={{ background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 14px', fontSize: 13, cursor: 'pointer' }}
        >
          Отправить тест
        </button>
        {msg && <span style={S.muted}>{msg}</span>}
      </div>
    </div>
  );
}

// ─── Зона опасности ───────────────────────────────────────────────────────────
function DangerZone({ authFetch, logout, navigate }) {
  const [gdprConfirm, setGdprConfirm] = useState(false);

  const handleGDPR = async () => {
    try {
      await authFetch(`${API_BASE}/profile/data`, { method: 'DELETE' });
      logout();
      navigate('/', { replace: true });
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  };

  return (
    <div style={{ ...S.card, border: '1px solid rgba(239,68,68,0.2)', marginTop: 8 }}>
      <p style={{ ...S.cardTitle, color: 'var(--color-danger)' }}>Удаление данных (GDPR)</p>
      <p style={{ ...S.muted, marginBottom: 14 }}>
        Удалит все карты, интерпретации и данные подписки. Аккаунт (email) сохраняется. Необратимо.
      </p>
      {gdprConfirm ? (
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={S.btn('danger')} onClick={handleGDPR}>Да, удалить все данные</button>
          <button style={S.btn('ghost')} onClick={() => setGdprConfirm(false)}>Отмена</button>
        </div>
      ) : (
        <button
          onClick={() => setGdprConfirm(true)}
          style={{ ...S.btn('ghost'), color: 'var(--color-danger)', border: '1px solid rgba(220,38,38,0.4)' }}
        >
          Удалить все данные
        </button>
      )}
    </div>
  );
}

// ─── Главный компонент ────────────────────────────────────────────────────────
export default function ProfilePage() {
  const { user, authFetch, logout } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('charts');

  const { charts, setCharts, primaryChartId, setPrimaryChartId, history, subscription, loading } = useProfileData(authFetch);

  const tabs = [
    { key: 'charts',        label: '✦ Карты'         },
    { key: 'history',       label: '✦ История'       },
    { key: 'subscription',  label: '✦ Подписка'      },
    { key: 'referral',      label: '✦ Друзья'        },
    { key: 'notifications', label: '✦ Уведомления'   },
    ...(user?.tier === 'premium' ? [{ key: 'crm', label: '✦ Клиенты' }] : []),
  ];

  return (
    <div className="prof-scope" style={S.page}>
      <style>{PROF_THEME_CSS}</style>
      <div style={S.inner}>

        {/* Шапка */}
        <TabProfile user={user} logout={logout} authFetch={authFetch} />

        {/* Вкладки */}
        <div style={S.tabBar}>
          {tabs.map(t => (
            <button key={t.key} style={S.tabBtn(tab === t.key)} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Контент */}
        {tab === 'charts'        && <TabCharts       charts={charts} setCharts={setCharts} primaryChartId={primaryChartId} setPrimaryChartId={setPrimaryChartId} loading={loading.charts} authFetch={authFetch} subscription={subscription} user={user} />}
        {tab === 'history'       && <TabHistory      history={history} loading={loading.history} />}
        {tab === 'subscription'  && <TabSubscription user={user} subscription={subscription} loading={loading.sub} authFetch={authFetch} />}
        {tab === 'referral'      && <TabReferral     authFetch={authFetch} />}
        {tab === 'notifications' && <TabNotifications authFetch={authFetch} />}
        {tab === 'crm' && user?.tier === 'premium' && (
          <div style={{ ...S.card, textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>👥</div>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>CRM-база клиентов</div>
            <div style={{ ...S.muted, marginBottom: 16 }}>Управляйте клиентами, стройте их карты и создавайте PDF-отчёты.</div>
            <Link to="/dashboard/clients" style={{ ...S.btn('primary'), textDecoration: 'none', display: 'inline-block', background: 'var(--color-warning)' }}>
              Открыть CRM →
            </Link>
          </div>
        )}

        {/* Зона опасности — всегда снизу */}
        <DangerZone authFetch={authFetch} logout={logout} navigate={navigate} />

      </div>
    </div>
  );
}
