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
import MotionButton from '../components/MotionButton';
import { TIER_NAMES, TIERS } from '../constants';

// ─── Тёмная тема ──────────────────────────────────────────────────────────────
const PROF_THEME_CSS = `
  /* Осталось четыре: остальные восемь были псевдонимами глобальных токенов
     и сняты 15.09.2026.

     --prof-card ПОЛУПРОЗРАЧНА В СВЕТЛОЙ ТЕМЕ НАМЕРЕННО, это не отклонение.
     Значение rgba(255,255,255,0.85) появилось 05.06.2026 коммитом 3348462
     (fix: ProfilePage light theme to match app style) — ТЕМ ЖЕ коммитом фон
     страницы стал transparent, то есть карточку сделали прозрачной ровно
     тогда, когда поставили её на сиренево-розовый градиент App.jsx.
     85% белого пропускают градиент снизу; это ответ на фон, а не случайность.
     ⚠️ Приём остался ЕДИНСТВЕННЫМ в вебе — больше ни одна карточка так не
     сделана, поэтому выглядит как забытый эксперимент и просится к сведению
     в --bg-card. Не сводить: пока градиент на месте, основание живое.
     ⚠️ При отказе от градиента основание исчезает — тогда пересмотреть
     вместе с фоном, а не раньше и не отдельно. */
  .prof-scope { --prof-card:rgba(255,255,255,0.85); --prof-tab-active:var(--bg-card); --prof-divider:rgba(var(--accent-rgb), 0.12); --prof-toggle-off:var(--border); }
  .dark .prof-scope { --prof-card:rgba(26,18,48,0.55); --prof-tab-active:rgba(var(--accent-rgb), 0.2); --prof-divider:rgba(var(--accent-rgb), 0.2); --prof-toggle-off:rgba(148,163,184,0.15); }
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
const TIER_LABELS = TIER_NAMES;
/* tier data-color, intentional */
/**
 * ⚠️ Значения — `var(...)`, и приписать к ним hex-альфу НЕЛЬЗЯ.
 *
 * Так и было до 16.09.2026: `${TIER_COLORS[t.id]}60` давало строку
 * `var(--accent)60`, которую браузер не разбирает вовсе — `getComputedStyle`
 * отдавал `border: 0px none` и прозрачный фон, то есть КАРТОЧКИ ТАРИФОВ В
 * ПРОФИЛЕ НЕ РИСОВАЛИСЬ. «Рекомендуем» держалось на одной мелкой надписи.
 * В PlannerPage тот же приём работал, потому что там PLANET_COLORS — сырые
 * hex; здесь токены, и это не взаимозаменяемо.
 *
 * Прозрачность берётся через color-mix, который принимает var() как значение.
 * ⚠️ Правка ПЕРЕЖИЛА откат визуального языка 17.09.2026 намеренно: откатывался
 * вид, а это дефект — цвета тарифов остались прежними, веб-овскими.
 */
const TIER_COLORS = { free: 'var(--text-secondary)', lite: 'var(--color-air)', pro: 'var(--accent)', premium: 'var(--color-warning)' };
const TIER_TINT = (tier, pct) => `color-mix(in srgb, ${TIER_COLORS[tier] || 'var(--text-secondary)'} ${pct}%, transparent)`;

// ─── Стили (светлая и тёмная тема через CSS-переменные) ─────────────────────
const S = {
  page: {
    minHeight: '100vh',
    background: 'transparent',
    color: 'var(--text-primary)',
    fontFamily: "var(--font-body)",
    padding: '24px 16px',
  },
  inner: { maxWidth: 680, margin: '0 auto' },
  card: {
    background: 'var(--prof-card)',
    border: '1px solid rgba(var(--accent-rgb), 0.15)',
    borderRadius: 'var(--radius-md)',
    padding: '20px 24px',
    marginBottom: 16,
  },
  cardTitle: { fontSize: 14, fontWeight: 700, margin: '0 0 16px', color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.06em' },
  tabBar: {
    display: 'flex',
    gap: 2,
    background: 'var(--accent-muted)',
    borderRadius: 'var(--radius-md)',
    padding: 4,
    marginBottom: 24,
    overflowX: 'auto',
  },
  tabBtn: (active) => ({
    flex: '1 0 auto',
    padding: '8px 14px',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    whiteSpace: 'nowrap',
    fontFamily: 'inherit',
    transition: 'all 0.15s',
    background: active ? 'var(--prof-tab-active)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-secondary)',
  }),
  btn: (variant = 'ghost') => ({
    padding: '8px 16px',
    borderRadius: 'var(--radius-sm)',
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
  muted: { fontSize: 12, color: 'var(--text-secondary)' },
  badge: (tier) => ({
    display: 'inline-block',
    padding: '3px 12px',
    borderRadius: 'var(--radius-xl)',
    background: TIER_TINT(tier, 10),
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
            <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--text-secondary)' }}>Google</span>
          )}
        </div>
        <MotionButton level="ghost" style={S.btn('ghost')} onClick={logout}>Выйти</MotionButton>
      </div>

      {isAdmin && (
        <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--prof-divider)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>🔧 Тестовый тариф</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {['free', 'lite', 'pro', 'premium'].map(t => (
              <MotionButton
                key={t}
                level={user?.tier === t ? 'primary' : 'ghost'}
                onClick={() => setTier(t)}
                disabled={!!switching || user?.tier === t}
                style={{
                  ...S.btn(user?.tier === t ? 'primary' : 'ghost'),
                  fontSize: 12,
                  padding: '5px 12px',
                  opacity: switching && switching !== t ? 0.5 : 1,
                }}
              >
                {switching === t ? '...' : TIER_NAMES[t]}
              </MotionButton>
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

  // Счётчик карт для free — слотовая модель (profiles_limit): сколько карт
  // сохранено СЕЙЧАС. Удаление карты освобождает слот, источник —
  // charts.length (то, что реально отрисовано), не серверная сводка.
  const isFree = !user?.tier || user?.tier === 'free';
  const chartsLimit = subscription?.limits?.profiles_limit ?? null;
  const chartsUsed = charts.length;
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
      padding: '12px 16px', borderRadius: 'var(--radius-md)',
      background: chartsLeft === 0 ? 'rgba(220,38,38,0.08)' : 'var(--accent-muted)',
      border: `1px solid ${chartsLeft === 0 ? 'rgba(220,38,38,0.2)' : 'rgba(var(--accent-rgb), 0.2)'}`,
      fontSize: 13, color: chartsLeft === 0 ? 'var(--color-danger)' : 'var(--accent)', fontWeight: 600,
      display: 'flex', alignItems: 'center', gap: 8,
    }}>
      <span>{chartsLeft === 0 ? '🔒' : '🗂'}</span>
      {chartsLeft === 0
        ? 'Достигнут лимит сохранённых карт. Удали ненужную карту, чтобы освободить место, или перейди на старший тариф.'
        : `Сохранено карт: ${chartsUsed} из ${chartsLimit}`}
    </div>
  ) : null;

  if (loading) return <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Загрузка…</div>;
  if (!charts.length) return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <LimitBanner />
      <div style={{ ...S.card, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 13 }}>
        Нет сохранённых карт.<br />
        <Link to="/home" style={{ color: 'var(--accent)', marginTop: 8, display: 'inline-block' }}>
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
                ? '1px solid rgba(var(--accent-rgb), 0.5)'
                : '1px solid rgba(var(--accent-rgb), 0.15)',
            }}
          >
            {/* Шапка карточки: булавка у главной */}
            {isPrimary && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                marginBottom: 10,
                fontSize: 11, fontWeight: 700,
                color: 'var(--accent)', letterSpacing: '0.05em', textTransform: 'uppercase',
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
                    <MotionButton
                      level="ghost"
                      disabled={addingToClients === chart.id || addedToClients[chart.id]}
                      onClick={() => handleAddToClients(chart)}
                      style={{ ...S.btn('ghost'), fontSize: 12, padding: '6px 12px', color: 'var(--color-warning)', border: '1px solid var(--border)' }}
                    >
                      {addingToClients === chart.id ? '…' : addedToClients[chart.id] ? 'Добавлено' : 'в Клиенты'}
                    </MotionButton>
                  )}
                  {deleteConfirm === chart.id ? (
                    <>
                      <MotionButton level="primary" style={{ ...S.btn('danger'), fontSize: 12, padding: '6px 10px' }} onClick={() => handleDelete(chart.id)}>Удалить</MotionButton>
                      <MotionButton level="ghost" style={{ ...S.btn('ghost'), fontSize: 12, padding: '6px 10px' }} onClick={() => setDeleteConfirm(null)}>Отмена</MotionButton>
                    </>
                  ) : (
                    <button style={{ ...S.btn('ghost'), fontSize: 12, padding: '6px 10px' }} onClick={() => setDeleteConfirm(chart.id)}>✕</button>
                  )}
                </div>
                {/* Кнопка "Сделать главной" — только для не-главных карт */}
                {!isPrimary && charts.length > 1 && (
                  <MotionButton
                    level="ghost"
                    disabled={settingPrimary === chart.id}
                    onClick={() => handleSetPrimary(chart.id)}
                    style={{
                      ...S.btn('ghost'),
                      fontSize: 11,
                      padding: '4px 10px',
                      color: 'var(--text-secondary)',
                      border: '1px solid rgba(148,163,184,0.25)',
                      opacity: settingPrimary === chart.id ? 0.6 : 1,
                    }}
                  >
                    {settingPrimary === chart.id ? '…' : 'Сделать главной'}
                  </MotionButton>
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
  if (loading) return <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Загрузка…</div>;
  if (!history.length) return (
    <div style={{ ...S.card, color: 'var(--text-secondary)', fontSize: 13, textAlign: 'center' }}>
      История пуста — прогнозы появятся здесь после генерации.
    </div>
  );

  const cleanPreview = (text) => (text || '').replace(/<\/?section[^>]*>/gi, '').trim();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {history.map(item => (
        <div key={item.id} style={S.card}>
          <div style={S.row}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {cleanPreview(item.preview) || '—'}
              </div>
              <div style={S.muted}>
                {item.created_at ? new Date(item.created_at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              <Link
                to={`/chart/${item.chart_id}`}
                style={{ fontSize: 12, color: 'var(--accent)', textDecoration: 'none' }}
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
// Состав и цены тарифов — из constants.js (единый источник с /pricing).

const TIER_ORDER = ['free', 'lite', 'pro', 'premium'];

// planner_months → подпись горизонта планера
const PLANNER_LABELS = { 0: 'текущий период', 3: 'месяц', 12: 'долгосрочно' };

// Строит 9 строк «Что включено» из subscription.features / subscription.limits.
function buildFeatureRows(feat = {}, lim = {}) {
  const plannerMonths = lim.planner_months ?? feat.planner_months;
  const transitsMonths = lim.transits_months ?? feat.transits_months;
  const profilesLimit = lim.profiles_limit !== undefined ? lim.profiles_limit : feat.profiles_limit;
  // null здесь означает «безлимит» (Орион) — не «нет данных», поэтому строгая
  // проверка на undefined вместо `??`, который принял бы null за отсутствие
  // значения и увёл бы к дефолту 0 (нашли на правке сетки 19.08.2026).
  const lunarMonths = lim.lunar_months !== undefined ? lim.lunar_months : feat.lunar_months;
  return [
    {
      label: 'Планер',
      ok: true,
      value: PLANNER_LABELS[plannerMonths] ?? (plannerMonths ? `${plannerMonths} мес` : '—'),
    },
    {
      // До 08.09.2026 здесь стоял обход для free: feat.transits приходил с
      // бэкенда как transits_months > 0, а у free флаг был нулём при живой
      // витрине на 3 месяца — строка врала «транзитов нет», хотя в таймлайне
      // они есть. Обход снят вместе с причиной: у free transits_months = 3,
      // и признак с сервера стал правдой. Не возвращать его — расхождение
      // теперь означало бы настоящую поломку, а не известную ложь флага.
      label: 'Транзиты',
      ok: !!feat.transits,
      value: feat.transits ? `${transitsMonths} мес${feat.transits_ai ? ' + разбор' : ''}` : null,
    },
    { label: 'Лунный календарь', ok: lunarMonths === null || lunarMonths === undefined || lunarMonths > 0 },
    { label: 'Google Calendar', ok: !!feat.google_calendar },
    {
      label: 'Карты',
      ok: true,
      value: (profilesLimit === null || profilesLimit === undefined) ? '∞' : `${profilesLimit}`,
    },
    { label: 'RAG-чат', ok: !!feat.rag_chat },
    { label: 'PDF', ok: !!feat.pdf_reports },
    { label: 'CRM', ok: !!feat.crm },
    { label: 'Безлим. интерпретации', ok: !!feat.unlimited_interpretations },
  ];
}

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
      <div style={{ height: 6, borderRadius: 4, background: 'rgba(var(--accent-rgb), 0.1)', overflow: 'hidden' }}>
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
  const [checkoutLoading, setCheckoutLoading] = useState(null);
  const [checkoutError, setCheckoutError] = useState(null);

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

  const features = buildFeatureRows(subscription?.features, subscription?.limits);

  if (loading) return <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Загрузка…</div>;

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
                Доступ до: {new Date(subscription.current_period_end).toLocaleDateString('ru-RU')}
              </div>
            )}
          </div>
          {subscription?.status && subscription.status !== 'free' && (
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 'var(--radius-md)', background: 'rgba(52,211,153,0.12)', color: 'var(--color-success)' }}>
              {subscription.status === 'active' ? 'Активна' : subscription.status}
            </span>
          )}
        </div>
      </div>

      {/* Фичи */}
      <div style={S.card}>
        <p style={S.cardTitle}>Что включено</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8 }}>
          {features.map(f => (
            <div key={f.label} style={{ padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', textAlign: 'center', opacity: f.ok ? 1 : 0.5 }}>
              <div style={{ fontSize: 16, marginBottom: 4 }}>{f.ok ? '✓' : '✗'}</div>
              <div style={{ fontSize: 11, color: f.ok ? 'var(--accent-glow)' : 'var(--text-secondary)' }}>{f.label}</div>
              {f.value && (
                <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>{f.value}</div>
              )}
            </div>
          ))}
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
        const transitAiLimit = lim.transits_ai_per_month;     // 3 у lite, null у pro/premium, 0 у free
        const transitAiUsed = use.transit_ai_this_month ?? 0;
        const pdfLimit = lim.pdf_per_month;                   // 1 у free, 5/15, null у premium
        const pdfUsed = use.pdf_this_month ?? 0;

        // Pro/Premium — интерпретации безлимитны
        const interpUnlimited = feat.unlimited_interpretations;

        return (
          <div style={S.card}>
            <p style={S.cardTitle}>Использование в этом месяце</p>

            {/* У Free строки о бесплатной интерпретации больше нет. Она читала
                features.first_interpretation_available — флаг на АККАУНТЕ, а с
                048 право считается по каждой карте отдельно: после разбора
                первой карты флаг гас, и строка сообщала «использована», хотя по
                второй карте разбор оставался доступен. Показывать неверное
                состояние хуже, чем не показывать ничего, а счётчик вида
                «осталась 1 из 2» здесь не нужен по решению владельца: вторая
                интерпретация просто открывается. Сам флаг в API остался — он
                отвечает на вопрос «разбирал ли пользователь хоть раз». */}
            {tier !== 'free' && (
              <UsageBar
                label="Интерпретации"
                used={interpUsed}
                limit={interpUnlimited ? null : interpLimit}
                tierColor={tierColor}
              />
            )}

            {/* AI-транзиты показываем только там, где есть квота (lite) или безлимит (pro/premium) */}
            {(transitAiLimit === null || transitAiLimit > 0) && (
              <UsageBar
                label="Расшифровки транзитов"
                used={transitAiUsed}
                limit={transitAiLimit}
                tierColor={tierColor}
              />
            )}

            {/* PDF: условие показа как у транзитов — есть квота или безлимит.
                У free с 30.08.2026 квота 1, значит полосу он видит, и это
                намеренно: она показывает, потрачен ли бесплатный PDF. */}
            {(pdfLimit === null || pdfLimit > 0) && (
              <UsageBar
                label="PDF-отчёты"
                used={pdfUsed}
                limit={pdfLimit}
                tierColor={tierColor}
              />
            )}

            {/* Мягкий апсейл при исчерпании */}
            {tier !== 'premium' && !interpUnlimited && interpLimit > 0 && interpUsed >= interpLimit && (
              <div style={{ fontSize: 12, color: 'var(--color-warning)', marginTop: 4 }}>
                Лимит интерпретаций исчерпан — перейди на тариф выше, чтобы продолжить.
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
              <div key={t.id} style={{
                display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12,
                padding: '14px 16px', borderRadius: 'var(--radius-sm)',
                border: `1px solid ${TIER_TINT(t.id, t.recommended ? 38 : 19)}`,
                background: TIER_TINT(t.id, 5),
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                    <span style={S.badge(t.id)}>{t.label}</span>
                    <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{t.price}</span>
                    {t.recommended && (
                      <span style={{ fontSize: 10, fontWeight: 700, color: TIER_COLORS[t.id], letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                        Рекомендуем
                      </span>
                    )}
                  </div>
                  {t.upsellFrom && (
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>{t.upsellFrom}</div>
                  )}
                  <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {t.features.map((f, i) => (
                      <li key={i} style={{ display: 'flex', gap: 6, fontSize: 11.5, lineHeight: 1.4, color: 'var(--text-secondary)' }}>
                        <span style={{ color: TIER_COLORS[t.id], flexShrink: 0 }}>·</span>{f}
                      </li>
                    ))}
                  </ul>
                </div>
                <MotionButton
                  level="primary"
                  onClick={t.id === 'premium' ? undefined : () => handleCheckout(t.id)}
                  disabled={t.id === 'premium' ? true : !!checkoutLoading}
                  style={{
                    ...S.btn('primary'),
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                    opacity: t.id === 'premium' ? 0.6 : (checkoutLoading && checkoutLoading !== t.id ? 0.5 : 1),
                    ...(t.id === 'premium' ? { cursor: 'default' } : {}),
                  }}
                >
                  {t.id === 'premium' ? 'Скоро' : checkoutLoading === t.id ? 'Открываю…' : `Перейти →`}
                </MotionButton>
              </div>
            ))}
          </div>
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

  if (!data) return <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Загрузка…</div>;

  return (
    <div>
      <div style={S.card}>
        <p style={S.cardTitle}>Пригласи друга</p>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
          Когда приглашённый оплатит подписку — ты получишь <strong style={{ color: 'var(--accent-glow)' }}>2 недели {TIER_NAMES.pro} бесплатно</strong>.
        </p>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Твоя реферальная ссылка</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              readOnly
              value={data.ref_url || '—'}
              style={{ flex: 1, background: 'var(--bg-deeper)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit' }}
            />
            <MotionButton level="primary" style={S.btn('primary')} onClick={copy}>
              {copied ? '✓ Скопировано' : 'Копировать'}
            </MotionButton>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ background: 'var(--bg-deeper)', borderRadius: 'var(--radius-md)', padding: '14px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--accent-glow)' }}>{data.referrals_count ?? 0}</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>Приглашено</div>
          </div>
          <div style={{ background: 'var(--bg-deeper)', borderRadius: 'var(--radius-md)', padding: '14px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--color-success)' }}>{data.reward_weeks_earned ?? 0} нед.</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>Бонус получено</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Вкладка: Кабинет партнёра ─────────────────────────────────────────────────
// Заменяет «Друзья» у пользователей с is_partner=true (ProfilePage.tabs ниже) —
// две программы одновременно одному человеку не показываются. Данные — только
// агрегаты (backend/partners/router.py): ни email, ни имена, ни отдельные
// даты регистрации приглашённых сюда не попадают.
function TabPartner({ authFetch }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    authFetch(`${API_BASE}/partners/dashboard`)
      .then(setData)
      .catch(() => setError(true));
  }, [authFetch]);

  const money = (n) => Math.round(n || 0).toLocaleString('ru-RU') + ' ₽';

  if (error) {
    return <div style={S.card}><p style={S.muted}>Не удалось загрузить данные партнёрки. Попробуй чуть позже.</p></div>;
  }
  if (!data) {
    return <div style={S.card}><div style={S.muted}>Загрузка…</div></div>;
  }

  const { totals, monthly } = data;
  const stats = [
    { label: 'Переходов по ссылке', value: totals.visits },
    { label: 'Зарегистрировалось', value: totals.registered },
    { label: 'Оплатило', value: totals.paid },
    { label: 'Сумма их платежей', value: money(totals.revenue) },
    { label: `Начислено (${Math.round(totals.rate * 100)}%)`, value: money(totals.commission_earned) },
    { label: 'Выплачено', value: money(totals.paid_out) },
  ];

  return (
    <div>
      <div style={S.card}>
        <p style={S.cardTitle}>Партнёрская программа</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 16 }}>
          {stats.map(s => (
            <div key={s.label} style={{ background: 'var(--bg-deeper)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>{s.value}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{s.label}</div>
            </div>
          ))}
          <div style={{ background: 'var(--accent-muted)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--accent-glow)' }}>{money(totals.owed)}</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>К выплате</div>
          </div>
        </div>

        {Object.keys(totals.by_tier).length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Оплатившие по тарифам</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {Object.entries(totals.by_tier).map(([tier, count]) => (
                <span key={tier} style={{
                  fontSize: 12, padding: '4px 10px', borderRadius: 'var(--radius-full)',
                  background: 'var(--bg-deeper)', color: 'var(--text-primary)',
                }}>
                  {TIER_NAMES[tier] || tier}: {count}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div style={S.card}>
        <p style={S.cardTitle}>По месяцам</p>
        {monthly.length === 0 ? (
          <p style={S.muted}>Пока нет данных.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Месяц', 'Переходов', 'Регистр.', 'Оплатило', 'Платежи', 'Комиссия'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-secondary)', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {monthly.map(m => (
                  <tr key={m.month} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '6px 8px' }}>{m.month}</td>
                    <td style={{ padding: '6px 8px' }}>{m.visits}</td>
                    <td style={{ padding: '6px 8px' }}>{m.registered}</td>
                    <td style={{ padding: '6px 8px' }}>{m.paid}</td>
                    <td style={{ padding: '6px 8px' }}>{money(m.revenue)}</td>
                    <td style={{ padding: '6px 8px' }}>{money(m.commission)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
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
        daily_forecast: true, daily_time: '08:00', quiet_from: '22:00',
        planner: true, key_transits: true, moon_phases: false,
      }));
  }, [authFetch]);

  // ⚠️ Отказ сервера обязан откатывать оптимистичное значение.
  //
  // Раньше здесь стояло `catch (_) { /* тихо */ }`: значение ставилось до
  // запроса и при ошибке ОСТАВАЛОСЬ на экране. Пока сервер принимал любое
  // время, это было почти незаметно. С 10.09.2026 у границ окна появилась
  // парная проверка (`quiet_from` не раньше `daily_time`, 422), и молчаливый
  // вариант стал прямой ложью: человек видел бы выставленное им время, а на
  // сервере лежало прежнее.
  const patch = async (partial) => {
    const before = settings;
    setSettings(prev => ({ ...prev, ...partial }));
    setMsg('');
    try {
      const saved = await authFetch(`${API_BASE}/push/settings`, {
        method: 'PATCH',
        body: JSON.stringify(partial),
      });
      setSettings(saved);
    } catch (e) {
      setSettings(before);
      setMsg(e?.message || 'Не удалось сохранить настройку');
    }
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

  const quietFrom = settings.quiet_from || '22:00';
  const dailyTime = settings.daily_time || '08:00';

  const items = [
    { key: 'daily_forecast', label: 'Ежедневный прогноз', desc: `Каждый день в ${dailyTime}`, time: true },
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
                      border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '6px 10px', fontSize: 14,
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

      {/* Верхняя граница окна. Нижняя — это время ежедневного прогноза выше:
          две границы одной пары, поэтому и живут рядом, а не в разных местах.
          Сервер отбивает 422, если верхняя оказывается не позже нижней. */}
      <div style={{ ...S.row, padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>Не беспокоить после</div>
          <div style={S.muted}>{`Уведомления приходят с ${dailyTime} до ${quietFrom}`}</div>
        </div>
        <input
          type="time"
          value={quietFrom}
          onChange={(e) => patch({ quiet_from: e.target.value })}
          style={{
            background: 'var(--bg-deeper)', color: 'var(--text-primary)',
            border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '6px 10px', fontSize: 14,
          }}
        />
      </div>

      {permStatus === 'denied' && (
        <div style={{ ...S.muted, marginTop: 12, fontSize: 12 }}>
          Уведомления отключены в настройках браузера. Разреши их там — и тумблеры заработают.
        </div>
      )}
      <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <MotionButton
          level="primary"
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
          style={{ background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 'var(--radius-sm)', padding: '8px 14px', fontSize: 13, cursor: 'pointer' }}
        >
          Отправить тест
        </MotionButton>
        {msg && <span style={S.muted}>{msg}</span>}
      </div>
    </div>
  );
}

// ─── Мои данные (152-ФЗ) ────────────────────────────────────────────────────
function DataExport({ authFetch }) {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');

  const handleExport = async () => {
    setLoading(true);
    setErr('');
    try {
      const data = await authFetch(`${API_BASE}/profile/export`);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `aristea-data-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e.message || 'Не удалось скачать данные');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ ...S.card, marginTop: 8 }}>
      <p style={S.cardTitle}>Мои данные</p>
      <p style={{ ...S.muted, marginBottom: 14 }}>
        Скачай все данные, которые мы храним о тебе: карты, интерпретации, историю платежей и согласий.
      </p>
      <MotionButton level="ghost" style={S.btn('ghost')} onClick={handleExport} disabled={loading}>
        {loading ? 'Формируем файл…' : 'Скачать мои данные'}
      </MotionButton>
      {err && <p style={{ ...S.muted, color: 'var(--color-danger)', marginTop: 8 }}>{err}</p>}
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
          <MotionButton level="primary" style={S.btn('danger')} onClick={handleGDPR}>Да, удалить все данные</MotionButton>
          <MotionButton level="ghost" style={S.btn('ghost')} onClick={() => setGdprConfirm(false)}>Отмена</MotionButton>
        </div>
      ) : (
        <MotionButton
          level="ghost"
          onClick={() => setGdprConfirm(true)}
          style={{ ...S.btn('ghost'), color: 'var(--color-danger)', border: '1px solid rgba(220,38,38,0.4)' }}
        >
          Удалить все данные
        </MotionButton>
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
    { key: 'charts',        label: 'Карты'         },
    { key: 'history',       label: 'История'       },
    { key: 'subscription',  label: 'Подписка'      },
    // Один слот на обе программы — партнёру вкладка «Друзья» не показывается.
    { key: 'referral',      label: user?.is_partner ? 'Партнёрка' : 'Друзья' },
    { key: 'notifications', label: 'Уведомления'   },
    ...(user?.tier === 'premium' ? [{ key: 'crm', label: 'Клиенты' }] : []),
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
        {tab === 'referral'      && (user?.is_partner
          ? <TabPartner  authFetch={authFetch} />
          : <TabReferral authFetch={authFetch} />)}
        {tab === 'notifications' && <TabNotifications authFetch={authFetch} />}
        {tab === 'crm' && user?.tier === 'premium' && (
          <div style={{ ...S.card, textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>👥</div>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>CRM-база клиентов</div>
            <div style={{ ...S.muted, marginBottom: 16 }}>Управляй клиентами, строй их карты и создавай PDF-отчёты.</div>
            <Link to="/dashboard/clients" style={{ ...S.btn('primary'), textDecoration: 'none', display: 'inline-block', background: 'var(--color-warning)' }}>
              Открыть CRM →
            </Link>
          </div>
        )}

        <DataExport authFetch={authFetch} />

        {/* Зона опасности — всегда снизу */}
        <DangerZone authFetch={authFetch} logout={logout} navigate={navigate} />

      </div>
    </div>
  );
}
