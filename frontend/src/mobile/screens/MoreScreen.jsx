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

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import PullIndicator from '../components/PullIndicator';
import usePullToRefresh from '../lib/usePullToRefresh';
import { deleteChart, fetchMe, fetchSubscription, fetchCharts, setPrimaryChart } from '../lib/moreApi';
import { birthDateWords } from '../lib/chartFormat';
import { pickPrimaryChartId } from '../lib/feedApi';
import { openInBrowser } from '../lib/openInBrowser';
import { BIRTH_FORM_URL, WEB_CHART_URL } from '../lib/onboardingCopy';
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

export default function MoreScreen({ onChartsChanged }) {
  const [status, setStatus] = useState('loading');
  const [me, setMe] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [charts, setCharts] = useState([]);
  const [error, setError] = useState('');
  // Какая карта сейчас в работе (удаление или закрепление) — строка на это
  // время гаснет и её кнопки блокируются. Один идентификатор, не множество:
  // два действия над списком карт одновременно человеку не нужны, а
  // множество завело бы состояние, которое нечем проверить.
  const [chartBusyId, setChartBusyId] = useState(null);
  const [chartsError, setChartsError] = useState('');
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

  /**
   * Удаление карты. Подтверждение — тем же системным `window.confirm`, что и
   * выход выше: действие необратимо, а второго диалога в проекте нет.
   *
   * ⚠️ Список правится на месте, без перезапроса `/profile/charts`: состав
   * после удаления известен точно. Флаг основной карты при этом СНИМАЕТСЯ
   * локально, если удалили именно её, — бэкенд сбрасывает `primary_chart_id`
   * сам (`profile/router.py:180-181`), и оставить звезду висеть на пустом
   * месте значило бы показывать неправду до следующего обновления.
   *
   * ⚠️ Толчок соседним вкладкам обязателен и после удаления, и после
   * закрепления: «Лента» и «Карта» смонтированы всегда и сами о смене
   * состава не узнают (SPEC_CHART_CREATE.md §6).
   */
  const handleDeleteChart = useCallback(async (chart) => {
    const label = chart.name || birthDateWords(chart.birth_date);
    if (!window.confirm(`Удалить карту «${label}»? Это действие необратимо.`)) return;
    setChartBusyId(chart.id);
    setChartsError('');
    try {
      await deleteChart(chart.id);
      setCharts((prev) => prev.filter((c) => c.id !== chart.id));
      onChartsChanged?.();
    } catch (err) {
      setChartsError(err?.message || 'Не удалось удалить карту.');
    } finally {
      setChartBusyId(null);
    }
  }, [onChartsChanged]);

  /** Закрепление основной карты. Подтверждения не требует — действие обратимо. */
  const handleSetPrimary = useCallback(async (chart) => {
    setChartBusyId(chart.id);
    setChartsError('');
    try {
      await setPrimaryChart(chart.id);
      setCharts((prev) => prev.map((c) => ({ ...c, is_primary: c.id === chart.id })));
      onChartsChanged?.();
    } catch (err) {
      setChartsError(err?.message || 'Не удалось сделать карту основной.');
    } finally {
      setChartBusyId(null);
    }
  }, [onChartsChanged]);

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

  /**
   * `silent` — обновление жестом, без смены состояния на 'loading'.
   * Полное «почему» — в шапке lib/usePullToRefresh.js; здесь то, что
   * ломается именно на этой вкладке:
   *
   * ⚠️ Ветка `status === 'loading'` возвращает скелет ВМЕСТО экрана:
   * тариф, карты и меню мигают на месте уже показанных данных, а
   * прокрутка длинного экрана сбрасывается к верху.
   *
   * Ошибка при `silent` обязана улететь наверх: увести экран в 'error'
   * нельзя (за полноэкранным отказом спрячется уже загруженный профиль),
   * проглотить молча — тем более. Её показывает полоска жеста.
   */
  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setStatus('loading');
      setError('');
    }
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
      if (silent) throw err;
      setError(err?.message || 'Не удалось загрузить профиль.');
      setStatus('error');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Жест обновления — на собственном скроллере экрана (в отличие от
  // «Ленты», которая делит скроллер с TabShell). Только в корневом виде:
  // под-разделы (История, Друзья, Уведомления, Настройки) монтируются при
  // каждом заходе и грузят себя сами — устаревать им негде.
  const scrollRef = useRef(null);
  const refresh = useCallback(() => load({ silent: true }), [load]);
  const pull = usePullToRefresh(scrollRef, refresh, status === 'ready' && view === 'root');

  const chartsById = useMemo(() => new Map(charts.map((c) => [c.id, c])), [charts]);

  // Карта для ссылки на веб-отчёт — см. комментарий у самой ссылки ниже.
  const pdfChartId = useMemo(() => pickPrimaryChartId(charts), [charts]);

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
    <div ref={scrollRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '20px 16px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* ⚠️ Отрицательный отступ гасит `gap: 20` родителя. Полоска в покое
          нулевой высоты, но флекс-разрыв ей всё равно достаётся — без этого
          над шапкой «Ещё» постоянно висели бы лишние 20px пустоты. У двух
          других экранов родитель без gap, там компенсировать нечего. */}
      <PullIndicator
        state={pull.state}
        ready={pull.ready}
        innerRef={pull.indicatorRef}
        style={{ marginBottom: -20 }}
      />
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

      {/* PDF-отчёт по карте — ссылкой на сайт, а не своей кнопкой.

          ⚠️ Это дешёвая половина, и она выбрана осознанно. Ручка PDF
          (`POST /api/v1/chart/{id}/pdf`, backend/main.py:2310) требует
          заголовок Authorization и отдаёт файл вложением, поэтому
          `openInBrowser` открыть её НЕ может — Browser.open умеет только
          GET без заголовков. Полноценный «Скачать PDF» в приложении — это
          fetch с токеном, запись файла через @capacitor/filesystem и
          открытие его нативно, то есть новые плагины и пересборка проекта.
          Отдельная задача; здесь человек уходит на веб, где кнопка уже
          работает.

          ⚠️ Числа тарифа тут НЕ называем (ни «один в месяц», ни «с Веги») —
          единственный источник сетки на этом экране статический, а живые
          лимиты в блок тарифа не подставляются вовсе (MoreTierCard.jsx).
          Гейт и текст отказа живут на бэкенде (check_pdf_limit) и человек
          увидит их на сайте.

          Ведёт на КОНКРЕТНУЮ карту — ту же, что показывают «Лента» и
          «Карта» (pickPrimaryChartId, один на приложение). Списка карт нет
          (аккаунт без карт — реальное состояние, §8) — уводим на /home,
          где карту сначала строят. */}
      <button
        type="button"
        onClick={() => openInBrowser(
          pdfChartId ? `${WEB_CHART_URL}/${pdfChartId}` : BIRTH_FORM_URL,
        )}
        style={{
          width: '100%',
          textAlign: 'left',
          background: 'transparent',
          border: 'none',
          padding: 0,
          marginTop: -8,
          fontFamily: 'var(--font-body)',
          fontSize: 13,
          color: 'var(--text-secondary)',
        }}
      >
        PDF-отчёт по карте — на сайте →
      </button>

      <MoreCardsList
        charts={charts}
        busyId={chartBusyId}
        onSetPrimary={handleSetPrimary}
        onDelete={handleDeleteChart}
      />
      {/* Отказ действия показывается рядом со списком, а не уводит весь
          экран в состояние ошибки: тариф, профиль и меню рядом исправны и
          прятать их за полноэкранным отказом нельзя. */}
      {chartsError && (
        <p style={{ margin: '-4px 0 0', fontSize: 12.5, color: 'var(--color-danger)' }} role="alert">
          {chartsError}
        </p>
      )}

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
