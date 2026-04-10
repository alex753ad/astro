/**
 * ProfilePage — user profile, saved charts, subscription management.
 *
 * Route: /profile
 * Requires auth.
 */

import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth';

const API_BASE = '/api/v1';

export default function ProfilePage() {
  const { user, authFetch, logout, features } = useAuth();
  const navigate = useNavigate();

  const [charts,       setCharts]       = useState([]);
  const [subscription, setSubscription] = useState(null);
  const [loadingCharts, setLoadingCharts] = useState(true);
  const [loadingSub,    setLoadingSub]    = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState(null); // chart id to confirm
  const [portalLoading, setPortalLoading] = useState(false);
  const [gdprConfirm,   setGdprConfirm]   = useState(false);

  // Load charts
  useEffect(() => {
    authFetch(`${API_BASE}/profile/charts`)
      .then(data => setCharts(data.charts || []))
      .catch(() => {})
      .finally(() => setLoadingCharts(false));
  }, [authFetch]);

  // Load subscription
  useEffect(() => {
    authFetch(`${API_BASE}/profile/subscription`)
      .then(data => setSubscription(data))
      .catch(() => {})
      .finally(() => setLoadingSub(false));
  }, [authFetch]);

  const handleDeleteChart = async (chartId) => {
    try {
      await authFetch(`${API_BASE}/profile/charts/${chartId}`, { method: 'DELETE' });
      setCharts(prev => prev.filter(c => c.id !== chartId));
      setDeleteConfirm(null);
    } catch (err) {
      alert('Не удалось удалить карту: ' + err.message);
    }
  };

  const handlePortal = async () => {
    setPortalLoading(true);
    try {
      const data = await authFetch(`${API_BASE}/payments/portal`, {
        method: 'POST',
        body: JSON.stringify({ return_url: window.location.href }),
      });
      window.location.href = data.url;
    } catch (err) {
      alert('Ошибка: ' + err.message);
    } finally {
      setPortalLoading(false);
    }
  };

  const handleGDPR = async () => {
    try {
      await authFetch(`${API_BASE}/profile/data`, { method: 'DELETE' });
      logout();
      navigate('/', { replace: true });
    } catch (err) {
      alert('Ошибка удаления данных: ' + err.message);
    }
  };

  const TIER_LABELS = { free: 'Бесплатный', pro: 'Pro', premium: 'Premium' };
  const TIER_COLORS = { free: '#8B8FA3', pro: '#7C6CFF', premium: '#F59E0B' };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="font-display text-2xl font-bold mb-8">Профиль</h1>

      {/* User info */}
      <div className="glass-card p-6 mb-6">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <p style={{ margin: 0, fontWeight: 600, fontSize: 15 }}>{user?.email}</p>
            <span style={{
              display: 'inline-block', marginTop: 6,
              padding: '3px 12px', borderRadius: 20,
              background: `${TIER_COLORS[user?.tier] || '#888'}18`,
              color: TIER_COLORS[user?.tier] || '#888',
              fontSize: 12, fontWeight: 700,
            }}>
              {TIER_LABELS[user?.tier] || user?.tier}
            </span>
          </div>
          <button
            onClick={logout}
            style={{
              padding: '8px 16px', borderRadius: 8,
              border: '1px solid var(--border, #1E2235)',
              background: 'transparent', color: 'var(--text-secondary)',
              fontSize: 13, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            Выйти
          </button>
        </div>
      </div>

      {/* Subscription */}
      <div className="glass-card p-6 mb-6">
        <h2 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 14px', display: 'flex', alignItems: 'center', gap: 8 }}>
          ✦ Подписка
        </h2>
        {loadingSub ? (
          <p className="text-brand-muted text-sm">Загрузка…</p>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 10, marginBottom: 16 }}>
              {[
                { label: 'Транзиты',             ok: subscription?.features?.transits },
                { label: 'Безлим. интерпретации', ok: subscription?.features?.unlimitedInterpretations },
                { label: 'История карт',          ok: subscription?.features?.history },
                { label: 'PDF-отчёты',            ok: subscription?.features?.pdfReports },
                { label: 'Синастрия',             ok: subscription?.features?.synastry },
              ].map(f => (
                <div key={f.label} style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border, #1E2235)', textAlign: 'center' }}>
                  <div style={{ fontSize: 18 }}>{f.ok ? '✓' : '✗'}</div>
                  <div style={{ fontSize: 11, color: f.ok ? 'var(--text-primary)' : 'var(--text-secondary)', marginTop: 4 }}>{f.label}</div>
                </div>
              ))}
            </div>

            {user?.tier === 'free' ? (
              <Link
                to="/upgrade"
                style={{
                  display: 'inline-block', padding: '10px 20px', borderRadius: 10,
                  background: 'linear-gradient(135deg, #7C6CFF, #A78BFA)',
                  color: '#fff', fontWeight: 700, fontSize: 14, textDecoration: 'none',
                }}
              >
                Перейти на Pro — €7.99/мес →
              </Link>
            ) : (
              <button
                onClick={handlePortal}
                disabled={portalLoading}
                style={{
                  padding: '10px 20px', borderRadius: 10,
                  border: '1px solid var(--border, #1E2235)',
                  background: 'transparent', color: 'var(--text-primary)',
                  fontWeight: 600, fontSize: 14, cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                {portalLoading ? 'Открываю…' : 'Управление подпиской →'}
              </button>
            )}
          </>
        )}
      </div>

      {/* Saved charts */}
      <div className="glass-card p-6 mb-6">
        <h2 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 14px' }}>
          Сохранённые карты
        </h2>
        {loadingCharts ? (
          <p className="text-brand-muted text-sm">Загрузка…</p>
        ) : charts.length === 0 ? (
          <p className="text-brand-muted text-sm">Нет сохранённых карт.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {charts.map(chart => (
              <div key={chart.id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 14px', borderRadius: 10,
                border: '1px solid var(--border, #1E2235)',
                background: 'var(--card-inner, rgba(255,255,255,0.02))',
              }}>
                <div>
                  <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>{chart.birth_place}</p>
                  <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
                    {chart.birth_date}{chart.birth_time ? ` · ${chart.birth_time}` : ' · время неизвестно'}
                  </p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Link
                    to={`/chart/${chart.id}`}
                    style={{
                      padding: '6px 12px', borderRadius: 8,
                      border: '1px solid var(--border)',
                      color: 'var(--accent, #7C6CFF)', fontSize: 12,
                      fontWeight: 600, textDecoration: 'none',
                    }}
                  >
                    Открыть
                  </Link>
                  {deleteConfirm === chart.id ? (
                    <div style={{ display: 'flex', gap: 4 }}>
                      <button onClick={() => handleDeleteChart(chart.id)} style={{ padding: '6px 10px', borderRadius: 8, border: 'none', background: '#EF4444', color: '#fff', fontSize: 12, cursor: 'pointer' }}>Удалить</button>
                      <button onClick={() => setDeleteConfirm(null)} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-secondary)', fontSize: 12, cursor: 'pointer' }}>Отмена</button>
                    </div>
                  ) : (
                    <button onClick={() => setDeleteConfirm(chart.id)} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-secondary)', fontSize: 12, cursor: 'pointer' }}>✕</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Danger zone */}
      <div className="glass-card p-6" style={{ border: '1px solid rgba(239,68,68,0.2)' }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 8px', color: '#FCA5A5' }}>
          Удаление данных (GDPR)
        </h2>
        <p className="text-brand-muted text-sm mb-4">
          Удалит все карты, интерпретации и данные подписки. Аккаунт (email) сохраняется.
          Это действие необратимо.
        </p>
        {gdprConfirm ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={handleGDPR} style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: '#EF4444', color: '#fff', fontWeight: 600, fontSize: 13, cursor: 'pointer' }}>
              Да, удалить все мои данные
            </button>
            <button onClick={() => setGdprConfirm(false)} style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-secondary)', fontSize: 13, cursor: 'pointer' }}>
              Отмена
            </button>
          </div>
        ) : (
          <button onClick={() => setGdprConfirm(true)} style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid rgba(239,68,68,0.4)', background: 'transparent', color: '#FCA5A5', fontWeight: 600, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>
            Удалить все данные
          </button>
        )}
      </div>
    </div>
  );
}
