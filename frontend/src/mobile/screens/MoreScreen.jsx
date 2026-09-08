/**
 * MoreScreen.jsx — экран «Ещё» (SPEC_MORE_SCREEN.md).
 *
 * Три запроса при открытии, параллельно, без зависимости друг от друга
 * (§2): auth/me (шапка), profile/subscription (тариф), profile/charts
 * (мои карты). Одна упавшая — весь экран уходит в состояние ошибки, не
 * только свой блок (§8): частично собранный экран хуже явного отказа.
 *
 * Разделы меню (История, Друзья, Уведомления, Настройки) переключаются
 * локальным состоянием `view` — отдельного роутера у приложения нет,
 * это просто подмена содержимого внутри той же вкладки.
 *
 * «Скачать мои данные» здесь нет намеренно — SPEC_MORE_SCREEN.md §6.2.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import ThemeToggle from '../components/ThemeToggle';
import MoreCenteredNotice from '../components/MoreCenteredNotice';
import MoreTierCard from '../components/MoreTierCard';
import MoreCardsList from '../components/MoreCardsList';
import MoreMenuList from '../components/MoreMenuList';
import MoreSubScreen from '../components/MoreSubScreen';
import MoreHistoryView from '../components/MoreHistoryView';
import MoreReferralView from '../components/MoreReferralView';
import MoreNotificationsView from '../components/MoreNotificationsView';
import MoreSettingsView from '../components/MoreSettingsView';
import { fetchMe, fetchSubscription, fetchCharts } from '../lib/moreApi';
import useAuth from '../../hooks/useAuth.jsx';

const SUB_TITLES = {
  history: 'История разборов',
  referral: 'Друзья',
  notifications: 'Уведомления',
  settings: 'Настройки',
};

/** Скелет: строка шапки, прямоугольник тарифа, 2 плейсхолдера карт, 5 строк меню (§8). */
function MoreLoading() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 20, padding: '20px 16px 0' }}>
      <div className="mobile-skeleton" style={{ height: 40, width: '60%', borderRadius: 8, background: 'var(--bg-deeper)' }} />
      <div className="mobile-skeleton" style={{ height: 130, borderRadius: 16, background: 'var(--bg-deeper)' }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {[0, 1].map((i) => (
          <div key={i} className="mobile-skeleton" style={{ height: 60, borderRadius: 14, background: 'var(--bg-deeper)' }} />
        ))}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="mobile-skeleton" style={{ height: 16, borderRadius: 8, background: 'var(--bg-deeper)' }} />
        ))}
      </div>
    </div>
  );
}

export default function MoreScreen() {
  const [status, setStatus] = useState('loading');
  const [me, setMe] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [charts, setCharts] = useState([]);
  const [error, setError] = useState('');
  const { logout } = useAuth();
  const [view, setView] = useState('root');

  // Подтверждение перед выходом — тем же приёмом, что уже принят в проекте
  // для необратимых действий (AdminPage, CRMPage): системный
  // window.confirm, не своя модалка (ChartPage.jsx: «Готового диалога
  // подтверждения в проекте нет»). В Capacitor его показывает
  // BridgeWebChromeClient.onJsConfirm — нативный AlertDialog, ничего
  // отдельно ставить не нужно.
  const handleLogout = useCallback(() => {
    if (window.confirm('Выйти из аккаунта?')) logout();
  }, [logout]);

  // Подсветка блока тарифа: сюда переключает FAB чата на free/Веге
  // (AristeaFab.jsx), а не своя кнопка апгрейда — вести к оплате должна
  // одна дверь. `location.state.highlightTier` — одноразовый флаг с
  // каждого такого перехода (свежий объект state на каждый navigate, даже
  // при повторном переходе с тем же значением), поэтому держим его как
  // отдельное состояние компонента и сразу же чистим из истории, чтобы
  // «Назад»/повторный рендер не перезапускали подсветку.
  const location = useLocation();
  const navigate = useNavigate();
  const [highlightTier, setHighlightTier] = useState(false);

  useEffect(() => {
    if (location.state?.highlightTier) {
      setHighlightTier(true);
      navigate(location.pathname, { replace: true, state: {} });
      const t = setTimeout(() => setHighlightTier(false), 2200);
      return () => clearTimeout(t);
    }
  }, [location.state, location.pathname, navigate]);

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      const [meData, subData, chartsData] = await Promise.all([
        fetchMe(),
        fetchSubscription(),
        fetchCharts(),
      ]);
      setMe(meData);
      setSubscription(subData);
      setCharts(chartsData.charts || []);
      setStatus('ready');
    } catch (err) {
      setError(err?.message || 'Не удалось загрузить профиль.');
      setStatus('error');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const chartsById = useMemo(() => new Map(charts.map((c) => [c.id, c])), [charts]);

  if (status === 'loading') return <MoreLoading />;

  if (status === 'error') {
    return (
      <MoreCenteredNotice
        title="Не удалось загрузить профиль"
        text={error}
        action="Повторить"
        onAction={load}
        secondary="Войти заново"
        onSecondary={logout}
      />
    );
  }

  if (view !== 'root') {
    const back = () => setView('root');
    return (
      <MoreSubScreen title={SUB_TITLES[view]} onBack={back}>
        {view === 'history' && <MoreHistoryView chartsById={chartsById} />}
        {view === 'referral' && <MoreReferralView />}
        {view === 'notifications' && <MoreNotificationsView />}
        {view === 'settings' && <MoreSettingsView />}
      </MoreSubScreen>
    );
  }

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '20px 16px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <header>
        {/* /auth/me.name приходит null, если имя не задано (UserProfileResponse,
            без фолбэка на бэкенде, backend/auth/router.py:713) — выдумывать
            имя из почты нельзя, показываем только почту в этом случае. */}
        {me.name && (
          <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>
            {me.name}
          </h1>
        )}
        <p style={{ margin: me.name ? '2px 0 0' : 0, fontSize: me.name ? 13 : 20, fontWeight: me.name ? 400 : 700, fontFamily: me.name ? 'var(--font-body)' : 'var(--font-display)', color: me.name ? 'var(--text-secondary)' : 'var(--text-primary)' }}>
          {me.email}
        </p>
      </header>

      <MoreTierCard tier={subscription.tier} highlight={highlightTier} />

      <MoreCardsList charts={charts} />

      <MoreMenuList onOpen={setView} />

      <ThemeToggle />

      {/* Отдельно от блока тарифа и от пунктов меню выше — это не
          настройка и не раздел, а необратимое действие (SPEC_MORE_SCREEN.md
          §6.3). Подтверждение — см. handleLogout. */}
      <button
        type="button"
        onClick={handleLogout}
        style={{
          width: '100%',
          textAlign: 'left',
          background: 'transparent',
          border: 'none',
          borderTop: '1px solid var(--border)',
          padding: '15px 0 4px',
          marginTop: 4,
          fontFamily: 'var(--font-body)',
          fontSize: 15,
          color: 'var(--color-danger)',
        }}
      >
        Выйти из аккаунта
      </button>
    </div>
  );
}
