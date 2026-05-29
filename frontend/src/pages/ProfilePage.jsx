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

const API_BASE = '/api/v1';

// ─── Цвета тарифов ───────────────────────────────────────────────────────────
const TIER_LABELS = { free: 'Бесплатный', lite: 'Lite', pro: 'Pro', premium: 'Premium' };
const TIER_COLORS = { free: '#8B8FA3', lite: '#38bdf8', pro: '#7C6CFF', premium: '#F59E0B' };

// ─── Стили (тёмная тема в стиле существующего приложения) ────────────────────
const S = {
  page: {
    minHeight: '100vh',
    background: '#0f172a',
    color: '#e2e8f0',
    fontFamily: "'Inter', system-ui, sans-serif",
    padding: '24px 16px',
  },
  inner: { maxWidth: 680, margin: '0 auto' },
  card: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 12,
    padding: '20px 24px',
    marginBottom: 16,
  },
  cardTitle: { fontSize: 14, fontWeight: 700, margin: '0 0 16px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em' },
  tabBar: {
    display: 'flex',
    gap: 2,
    background: '#0f172a',
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
    background: active ? '#1e293b' : 'transparent',
    color: active ? '#e2e8f0' : '#64748b',
  }),
  btn: (variant = 'ghost') => ({
    padding: '8px 16px',
    borderRadius: 8,
    border: variant === 'ghost' ? '1px solid #334155' : 'none',
    background: variant === 'primary' ? 'linear-gradient(135deg, #7C6CFF, #A78BFA)'
              : variant === 'danger'  ? '#ef4444'
              : 'transparent',
    color: variant === 'ghost' ? '#94a3b8' : '#fff',
    fontWeight: 600,
    fontSize: 13,
    cursor: 'pointer',
    fontFamily: 'inherit',
  }),
  row: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' },
  muted: { fontSize: 12, color: '#64748b' },
  badge: (tier) => ({
    display: 'inline-block',
    padding: '3px 12px',
    borderRadius: 20,
    background: `${TIER_COLORS[tier] || '#888'}18`,
    color: TIER_COLORS[tier] || '#888',
    fontSize: 12,
    fontWeight: 700,
  }),
};

// ─── Хук: данные профиля ──────────────────────────────────────────────────────
function useProfileData(authFetch) {
  const [charts,       setCharts]       = useState([]);
  const [history,      setHistory]      = useState([]);
  const [subscription, setSubscription] = useState(null);
  const [loading,      setLoading]      = useState({ charts: true, history: true, sub: true });

  useEffect(() => {
    authFetch(`${API_BASE}/profile/charts`)
      .then(d => setCharts(d.charts || []))
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

  return { charts, setCharts, history, subscription, loading };
}

// ─── Хук: уведомления в localStorage ─────────────────────────────────────────
const NOTIF_KEY = 'astro_notifications';
const NOTIF_DEFAULTS = {
  daily_forecast:  true,
  weekly_planner:  true,
  key_transits:    true,
  moon_phases:     false,
};
function useNotifications() {
  const [notifs, setNotifs] = useState(() => {
    try { return { ...NOTIF_DEFAULTS, ...JSON.parse(localStorage.getItem(NOTIF_KEY) || '{}') }; }
    catch { return NOTIF_DEFAULTS; }
  });
  const toggle = (key) => setNotifs(prev => {
    const next = { ...prev, [key]: !prev[key] };
    localStorage.setItem(NOTIF_KEY, JSON.stringify(next));
    return next;
  });
  return { notifs, toggle };
}

// ─── Toggle компонент ─────────────────────────────────────────────────────────
function Toggle({ checked, onChange }) {
  return (
    <div
      onClick={onChange}
      style={{
        width: 40, height: 22, borderRadius: 11, cursor: 'pointer',
        background: checked ? '#7C6CFF' : '#334155',
        position: 'relative', transition: 'background 0.2s', flexShrink: 0,
      }}
    >
      <div style={{
        position: 'absolute', top: 3,
        left: checked ? 21 : 3,
        width: 16, height: 16, borderRadius: '50%',
        background: '#fff', transition: 'left 0.2s',
      }} />
    </div>
  );
}

// ─── Вкладка: Профиль ─────────────────────────────────────────────────────────
function TabProfile({ user, logout }) {
  return (
    <div style={S.card}>
      <p style={S.cardTitle}>Аккаунт</p>
      <div style={S.row}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6 }}>{user?.email}</div>
          <span style={S.badge(user?.tier)}>{TIER_LABELS[user?.tier] || user?.tier}</span>
          {user?.google_sub && (
            <span style={{ marginLeft: 8, fontSize: 11, color: '#64748b' }}>Google</span>
          )}
        </div>
        <button style={S.btn('ghost')} onClick={logout}>Выйти</button>
      </div>
    </div>
  );
}

// ─── Вкладка: Мои карты ───────────────────────────────────────────────────────
function TabCharts({ charts, setCharts, loading, authFetch }) {
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const handleDelete = async (id) => {
    try {
      await authFetch(`${API_BASE}/profile/charts/${id}`, { method: 'DELETE' });
      setCharts(prev => prev.filter(c => c.id !== id));
      setDeleteConfirm(null);
    } catch (e) {
      alert('Не удалось удалить: ' + e.message);
    }
  };

  if (loading) return <div style={{ color: '#64748b', fontSize: 13 }}>Загрузка…</div>;
  if (!charts.length) return (
    <div style={{ ...S.card, textAlign: 'center', color: '#64748b', fontSize: 13 }}>
      Нет сохранённых карт.<br />
      <Link to="/" style={{ color: '#7C6CFF', marginTop: 8, display: 'inline-block' }}>
        Создать карту →
      </Link>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {charts.map(chart => (
        <div key={chart.id} style={S.card}>
          <div style={S.row}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 3 }}>{chart.birth_place}</div>
              <div style={S.muted}>
                {chart.birth_date}
                {chart.birth_time ? ` · ${chart.birth_time}` : ' · время неизвестно'}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
              <Link
                to={`/chart/${chart.id}`}
                style={{ ...S.btn('ghost'), textDecoration: 'none', fontSize: 12, padding: '6px 12px', color: '#7C6CFF', border: '1px solid #7C6CFF40' }}
              >
                Карта
              </Link>
              <Link
                to={`/planner/${chart.id}`}
                style={{ ...S.btn('ghost'), textDecoration: 'none', fontSize: 12, padding: '6px 12px', color: '#a78bfa', border: '1px solid #a78bfa40' }}
              >
                📅 Планер
              </Link>
              {deleteConfirm === chart.id ? (
                <>
                  <button style={{ ...S.btn('danger'), fontSize: 12, padding: '6px 10px' }} onClick={() => handleDelete(chart.id)}>Удалить</button>
                  <button style={{ ...S.btn('ghost'), fontSize: 12, padding: '6px 10px' }} onClick={() => setDeleteConfirm(null)}>Отмена</button>
                </>
              ) : (
                <button style={{ ...S.btn('ghost'), fontSize: 12, padding: '6px 10px' }} onClick={() => setDeleteConfirm(chart.id)}>✕</button>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Вкладка: История ─────────────────────────────────────────────────────────
function TabHistory({ history, loading }) {
  if (loading) return <div style={{ color: '#64748b', fontSize: 13 }}>Загрузка…</div>;
  if (!history.length) return (
    <div style={{ ...S.card, color: '#64748b', fontSize: 13, textAlign: 'center' }}>
      История пуста — прогнозы появятся здесь после генерации.
    </div>
  );

  const ENGINE_LABEL = { gpt4o: 'GPT-4o', deepseek: 'DeepSeek', anthropic: 'Claude', template: 'Шаблон' };
  const ENGINE_COLOR = { gpt4o: '#10b981', deepseek: '#3b82f6', anthropic: '#a78bfa', template: '#64748b' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {history.map(item => (
        <div key={item.id} style={S.card}>
          <div style={S.row}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, color: '#cbd5e1', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.preview || '—'}
              </div>
              <div style={S.muted}>
                {item.created_at ? new Date(item.created_at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              {item.engine && (
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, background: `${ENGINE_COLOR[item.engine] || '#64748b'}20`, color: ENGINE_COLOR[item.engine] || '#64748b' }}>
                  {ENGINE_LABEL[item.engine] || item.engine}
                </span>
              )}
              <Link
                to={`/chart/${item.chart_id}`}
                style={{ fontSize: 12, color: '#7C6CFF', textDecoration: 'none' }}
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
function TabSubscription({ user, subscription, loading, authFetch }) {
  const [portalLoading, setPortalLoading] = useState(false);

  const handlePortal = async () => {
    setPortalLoading(true);
    try {
      const data = await authFetch(`${API_BASE}/payments/portal`, {
        method: 'POST',
        body: JSON.stringify({ return_url: window.location.href }),
      });
      window.location.href = data.url;
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      setPortalLoading(false);
    }
  };

  const features = [
    { label: 'Транзиты',              key: 'transits' },
    { label: 'Безлим. интерпретации', key: 'unlimited_interpretations' },
    { label: 'История',               key: 'history' },
    { label: 'PDF-отчёты',            key: 'pdf_reports' },
    { label: 'Синастрия',             key: 'synastry' },
  ];

  if (loading) return <div style={{ color: '#64748b', fontSize: 13 }}>Загрузка…</div>;

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
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, background: '#10b98120', color: '#10b981' }}>
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
              <div key={f.key} style={{ padding: '10px 12px', borderRadius: 8, border: `1px solid ${ok ? '#7C6CFF40' : '#33415540'}`, textAlign: 'center' }}>
                <div style={{ fontSize: 16, marginBottom: 4 }}>{ok ? '✓' : '✗'}</div>
                <div style={{ fontSize: 11, color: ok ? '#c4b5fd' : '#64748b' }}>{f.label}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Кнопки */}
      <div style={S.card}>
        {user?.tier === 'free' ? (
          <div>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 14 }}>
              Перейдите на Lite чтобы разблокировать полную интерпретацию, транзиты и лунный календарь на год.
            </div>
            <Link
              to="/upgrade"
              style={{ ...S.btn('primary'), textDecoration: 'none', display: 'inline-block' }}
            >
              Перейти на Lite — 790 ₽/мес →
            </Link>
          </div>
        ) : user?.tier === 'lite' ? (
          <div>
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 14 }}>
              Перейдите на Pro чтобы разблокировать AI-транзиты, RAG-чат и PDF-отчёты.
            </div>
            <Link
              to="/upgrade"
              style={{ ...S.btn('primary'), textDecoration: 'none', display: 'inline-block' }}
            >
              Перейти на Pro — 1 990 ₽/мес →
            </Link>
          </div>
        ) : (
          <button onClick={handlePortal} disabled={portalLoading} style={S.btn('ghost')}>
            {portalLoading ? 'Открываю…' : 'Управление подпиской (Stripe) →'}
          </button>
        )}
      </div>
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

  if (!data) return <div style={{ color: '#64748b', fontSize: 13 }}>Загрузка…</div>;

  return (
    <div>
      <div style={S.card}>
        <p style={S.cardTitle}>Пригласи друга</p>
        <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16 }}>
          Когда приглашённый оплатит подписку — ты получишь <strong style={{ color: '#a78bfa' }}>2 недели Pro бесплатно</strong>.
        </p>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: '#64748b', marginBottom: 6 }}>Твоя реферальная ссылка</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              readOnly
              value={data.ref_url || '—'}
              style={{ flex: 1, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '8px 12px', color: '#e2e8f0', fontSize: 13, fontFamily: 'inherit' }}
            />
            <button style={S.btn('primary')} onClick={copy}>
              {copied ? '✓ Скопировано' : 'Копировать'}
            </button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ background: '#0f172a', borderRadius: 10, padding: '14px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#a78bfa' }}>{data.referrals_count ?? 0}</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>Приглашено</div>
          </div>
          <div style={{ background: '#0f172a', borderRadius: 10, padding: '14px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#34d399' }}>{data.reward_weeks_earned ?? 0} нед.</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>Бонус получено</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Вкладка: Уведомления ────────────────────────────────────────────────────
function TabNotifications() {
  const { notifs, toggle } = useNotifications();

  const items = [
    { key: 'daily_forecast',  label: 'Ежедневный прогноз',     desc: 'Каждое утро в 8:00' },
    { key: 'weekly_planner',  label: 'Планер на неделю',        desc: 'По понедельникам' },
    { key: 'key_transits',    label: 'Важные транзиты',         desc: 'Когда начинается значимый транзит' },
    { key: 'moon_phases',     label: 'Новолуние и полнолуние',  desc: 'Напоминание за день' },
  ];

  return (
    <div style={S.card}>
      <p style={S.cardTitle}>Push-уведомления</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {items.map((item, i) => (
          <div key={item.key}>
            <div style={{ ...S.row, padding: '12px 0' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 500, color: '#e2e8f0' }}>{item.label}</div>
                <div style={S.muted}>{item.desc}</div>
              </div>
              <Toggle checked={notifs[item.key]} onChange={() => toggle(item.key)} />
            </div>
            {i < items.length - 1 && <div style={{ borderBottom: '1px solid #1e293b' }} />}
          </div>
        ))}
      </div>
      <div style={{ ...S.muted, marginTop: 16 }}>
        ⚠️ Уведомления в разработке — настройки сохранятся когда функция будет запущена.
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
      <p style={{ ...S.cardTitle, color: '#fca5a5' }}>Удаление данных (GDPR)</p>
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
          style={{ ...S.btn('ghost'), color: '#fca5a5', border: '1px solid rgba(239,68,68,0.4)' }}
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

  const { charts, setCharts, history, subscription, loading } = useProfileData(authFetch);

  const tabs = [
    { key: 'charts',        label: '🗂 Карты'         },
    { key: 'history',       label: '📋 История'       },
    { key: 'subscription',  label: '✦ Подписка'       },
    { key: 'referral',      label: '🎁 Друзья'        },
    { key: 'notifications', label: '🔔 Уведомления'   },
  ];

  return (
    <div style={S.page}>
      <div style={S.inner}>

        {/* Шапка */}
        <TabProfile user={user} logout={logout} />

        {/* Вкладки */}
        <div style={S.tabBar}>
          {tabs.map(t => (
            <button key={t.key} style={S.tabBtn(tab === t.key)} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Контент */}
        {tab === 'charts'        && <TabCharts       charts={charts} setCharts={setCharts} loading={loading.charts} authFetch={authFetch} />}
        {tab === 'history'       && <TabHistory      history={history} loading={loading.history} />}
        {tab === 'subscription'  && <TabSubscription user={user} subscription={subscription} loading={loading.sub} authFetch={authFetch} />}
        {tab === 'referral'      && <TabReferral     authFetch={authFetch} />}
        {tab === 'notifications' && <TabNotifications />}

        {/* Зона опасности — всегда снизу */}
        <DangerZone authFetch={authFetch} logout={logout} navigate={navigate} />

      </div>
    </div>
  );
}
