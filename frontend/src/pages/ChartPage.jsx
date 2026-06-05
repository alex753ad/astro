/**
 * ChartPage.jsx — вкладки: Карта / Интерпретация / Аспекты / Транзиты / Планировщик
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import NatalChart from '../components/NatalChart';
import ChartSummary from '../components/ChartSummary';
import AspectTableWrapper from '../components/AspectTableWrapper';
import AspectTable from '../components/AspectTable';
import Interpretation from '../components/Interpretation';
import TransitTimeline from '../components/TransitTimeline';
import ExpertModeToggle from '../components/ExpertModeToggle';
import ForecastScale from '../components/ForecastScale';
import AspectGrid from '../components/AspectGrid';
import { useExpertMode } from '../hooks/useExpertMode.js';
import PaywallModal from '../components/PaywallModal';
import OnboardingTooltips from '../components/OnboardingTooltips';
import StreakBadge from '../components/StreakBadge';
import useStreak, { schedulePushReminder } from '../hooks/useStreak';
import RagChat from '../components/RagChat';
import {
  createReportCheckoutSession,
  startPdfGeneration,
  startTransitsAsync,
  pollTask,
} from '../api/client';

const REPORT_OPTIONS = [
  { type: 'basic',    label: 'Базовый натальный отчёт',        price: '$5', desc: 'Карта + интерпретация + главные аспекты' },
  { type: 'extended', label: 'Расширенный отчёт с транзитами', price: '$9', desc: 'Карта + детальный анализ + транзиты на 6 мес' },
  { type: 'synastry', label: 'Отчёт о совместимости',          price: '$9', desc: 'Синастрия двух карт + межаспектная сетка' },
];

function ReportModal({ chartId, onClose }) {
  const [loading, setLoading] = React.useState(null);
  const [error, setError]     = React.useState(null);
  const [pdfStep, setPdfStep] = React.useState('');  // прогресс генерации PDF

  // ── Скачать PDF (sync) ──
  async function handleDownloadFree() {
    setLoading('free');
    setError(null);
    setPdfStep('Генерируем PDF…');
    try {
      const token = localStorage.getItem('astro_access_token');
      const resp = await fetch(`https://astro-production-abcc.up.railway.app/api/v1/chart/${chartId}/pdf`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `natal_chart_${chartId.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      onClose();
    } catch (e) {
      setError('Не удалось сгенерировать PDF: ' + e.message);
    } finally {
      setLoading(null);
      setPdfStep('');
    }
  }

  // ── Купить расширенный PDF через Stripe ──
  async function handleBuy(type) {
    setLoading(type);
    setError(null);
    try {
      const { checkout_url } = await createReportCheckoutSession(type, chartId);
      window.location.href = checkout_url;
    } catch {
      setError('Не удалось открыть страницу оплаты. Попробуйте позже.');
      setLoading(null);
    }
  }

  return (
    <div style={sr.overlay} onClick={onClose}>
      <div style={sr.modal} onClick={e => e.stopPropagation()}>
        <button style={sr.close} onClick={onClose}>✕</button>
        <h2 style={sr.title}>📄 PDF-отчёт</h2>
        <p style={sr.sub}>Скачайте карту или купите расширенный отчёт</p>

        {/* ── Бесплатный PDF ── */}
        <div style={{ ...sr.item, marginBottom: 12, background: 'rgba(124,108,255,0.06)', border: '1px solid rgba(124,108,255,0.2)' }}>
          <div style={{ flex: 1 }}>
            <div style={sr.itemTitle}>Базовый PDF — бесплатно</div>
            <div style={sr.itemDesc}>Натальная карта + позиции планет + аспекты</div>
            {pdfStep && <div style={{ fontSize: 11, color: '#7C6CFF', marginTop: 4 }}>{pdfStep}</div>}
          </div>
          <button
            style={{ ...sr.btn, background: 'linear-gradient(135deg, #7C6CFF, #C060A0)', opacity: loading ? 0.6 : 1 }}
            onClick={handleDownloadFree}
            disabled={!!loading}
          >
            {loading === 'free' ? '…' : '⬇ Скачать'}
          </button>
        </div>

        <div style={sr.list}>
          {REPORT_OPTIONS.map(opt => (
            <div key={opt.type} style={sr.item}>
              <div style={{ flex: 1 }}>
                <div style={sr.itemTitle}>{opt.label}</div>
                <div style={sr.itemDesc}>{opt.desc}</div>
              </div>
              <button
                style={{ ...sr.btn, opacity: loading && loading !== opt.type ? 0.5 : 1 }}
                onClick={() => handleBuy(opt.type)}
                disabled={!!loading}
              >
                {loading === opt.type ? '…' : opt.price}
              </button>
            </div>
          ))}
        </div>
        {error && <p style={sr.error}>{error}</p>}
        <p style={sr.legal}>Платные отчёты — через Stripe. Безопасно.</p>
      </div>
    </div>
  );
}

const sr = {
  overlay: { position: 'fixed', inset: 0, background: 'rgba(30,26,46,0.55)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 },
  modal: { background: '#FFFFFF', borderRadius: 20, border: '0.5px solid #EDE8F5', padding: '32px 28px 24px', maxWidth: 420, width: '100%', position: 'relative', boxShadow: '0 20px 60px rgba(112,96,160,0.15)' },
  close: { position: 'absolute', top: 16, right: 16, background: 'none', border: 'none', color: '#9080B0', fontSize: 16, cursor: 'pointer' },
  title: { margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: '#1E1A2E', textAlign: 'center' },
  sub: { margin: '0 0 20px', fontSize: 13, color: '#7060A0', textAlign: 'center' },
  list: { display: 'flex', flexDirection: 'column', gap: 10 },
  item: { display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 12, border: '1px solid #EDE8F5', background: '#F9F7FD' },
  itemTitle: { fontSize: 13, fontWeight: 500, color: '#1E1A2E', marginBottom: 2 },
  itemDesc: { fontSize: 11, color: '#7060A0' },
  btn: { padding: '8px 16px', background: '#1E1A2E', color: '#fff', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: 'inherit' },
  error: { margin: '12px 0 0', fontSize: 12, color: '#C03030', textAlign: 'center' },
  legal: { margin: '14px 0 0', fontSize: 11, color: '#9080B0', textAlign: 'center' },
};

// Horizontal top tabs (above the 3-column layout)
const TOP_TABS = [
  { key: 'transits', label: 'Транзиты' },
];

// Left sidebar vertical buttons (only for 'chart' top tab)
const LEFT_BTNS = [
  { key: 'build',          label: 'Построить карту',       icon: '✦' },
  { key: 'planets',        label: 'Таблица планет/домов',  icon: '☉' },
  { key: 'aspects',        label: 'Таблица аспектов',      icon: '△' },
  { key: 'interpretation', label: 'AI-интерпретация',      icon: '✦' },
  { key: 'chat',           label: 'AI Астролог Астрея',    icon: '🤖', minTier: 'pro' },
];

const API_BASE = 'https://astro-production-abcc.up.railway.app/api/v1';

// Баннер «Сохраните карту» для анонимного пользователя
function SaveChartBanner({ onLogin }) {
  return (
    <div style={{
      margin: '0 0 16px',
      padding: '18px 24px', borderRadius: 16,
      background: 'linear-gradient(135deg, rgba(124,108,255,0.12), rgba(192,96,160,0.12))',
      border: '1.5px solid rgba(124,108,255,0.3)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 16, flexWrap: 'wrap',
    }}>
      <div>
        <div style={{ fontWeight: 700, fontSize: 14, color: '#1E1A2E', marginBottom: 4 }}>
          ✦ Сохраните свою карту
        </div>
        <div style={{ fontSize: 12, color: '#7060A0', lineHeight: 1.5 }}>
          Войдите или зарегистрируйтесь, чтобы не потерять результат
        </div>
      </div>
      <button
        onClick={onLogin}
        style={{
          padding: '9px 20px', borderRadius: 10, border: 'none',
          background: 'linear-gradient(135deg, #7C6CFF, #C060A0)',
          color: '#fff', fontSize: 13, fontWeight: 700,
          cursor: 'pointer', whiteSpace: 'nowrap',
          boxShadow: '0 4px 12px rgba(124,108,255,0.35)',
        }}
      >
        Войти / Регистрация
      </button>
    </div>
  );
}

// ── Хук тёмной темы перенесён в App.jsx ──

export default function ChartPage({ currentUser, onShowAuth }) {
  const { chartId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const TIER_HIERARCHY = ['free', 'lite', 'pro', 'premium'];
  function tierAllowed(minTier) {
    if (!minTier) return true;
    const userTier = currentUser?.tier || 'free';
    return TIER_HIERARCHY.indexOf(userTier) >= TIER_HIERARCHY.indexOf(minTier);
  }

  const [chart, setChart]                   = useState(null);
  const [transitPlanets, setTransitPlanets] = useState([]);
  const [selectedDate, setSelectedDate]     = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [topTab, setTopTab]         = useState(searchParams.get('tab') || 'chart');
  const [leftPanel, setLeftPanel]   = useState(null); // 'build'|'planets'|'aspects'|'interpretation'|'chat'|null
  const [activeTab, setActiveTab]   = useState('chart'); // kept for transit/planner compat
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);
  const [showPaywall, setShowPaywall] = useState(false);
  const [paywallContext, setPaywallContext] = useState('free_to_lite');
  const [showReport, setShowReport]   = useState(false);
  const [copied, setCopied]           = useState(false);
  const [shareUrl, setShareUrl]        = useState(null);
  const [shareLoading, setShareLoading] = useState(false);

  // Async-транзиты (Celery)
  const [asyncTransits, setAsyncTransits]     = useState(null);   // результат
  const [asyncTransitStep, setAsyncTransitStep] = useState('');   // шаг прогресса
  const [asyncTransitLoading, setAsyncTransitLoading] = useState(false);

  const { expertMode, toggleExpertMode } = useExpertMode(currentUser?.id ?? null);
  const { streak, isNew } = useStreak();

  // D5: запросить разрешение на уведомления + напомнить если давно не заходил
  useEffect(() => {
    if (!chart) return;
    if ('Notification' in window && Notification.permission === 'default') {
      // Запрашиваем только после взаимодействия, не сразу
      const t = setTimeout(() => {
        Notification.requestPermission().then(() => schedulePushReminder());
      }, 5000);
      return () => clearTimeout(t);
    }
    schedulePushReminder();
  }, [chart]);

  // Запустить расчёт транзитов за 12 месяцев через Celery
  async function loadTransitsAsync() {
    const from = new Date().toISOString().slice(0, 10);
    const to   = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    setAsyncTransitLoading(true);
    setAsyncTransitStep('Отправляем запрос…');
    setAsyncTransits(null);
    try {
      const { task_id } = await startTransitsAsync(chartId, from, to);
      const result = await pollTask(
        task_id,
        ({ status, step }) => setAsyncTransitStep(
          step === 'loading_chart' ? 'Загружаем карту…'      :
          step === 'calculating'   ? 'Считаем транзиты…'     :
          step === 'serializing'   ? 'Подготавливаем данные…' :
          'Обрабатываем…'
        ),
        2000,
        180_000,
      );
      setAsyncTransits(result.events);
      setAsyncTransitStep('');
    } catch (e) {
      setAsyncTransitStep('Ошибка: ' + e.message);
    } finally {
      setAsyncTransitLoading(false);
    }
  }

  async function handleShare() {
    const token = localStorage.getItem('astro_access_token');
    if (!token) {
      // анонимный — просто копируем текущий URL
      navigator.clipboard.writeText(window.location.href).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
      return;
    }
    setShareLoading(true);
    try {
      const resp = await fetch(
        `${API_BASE}/charts/${chartId}/share`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}` } }
      );
      if (!resp.ok) throw new Error('Ошибка генерации ссылки');
      const data = await resp.json();
      setShareUrl(data.share_url);
      navigator.clipboard.writeText(data.share_url).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      });
    } catch (e) {
      navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } finally {
      setShareLoading(false);
    }
  }

  async function handleDownloadCard() {
    const token = localStorage.getItem('astro_access_token');
    if (!token) { alert('Войдите, чтобы скачать карточку'); return; }
    // получаем токен если нет
    let url = shareUrl;
    if (!url) {
      const resp = await fetch(
        `${API_BASE}/charts/${chartId}/share`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}` } }
      );
      if (resp.ok) {
        const data = await resp.json();
        setShareUrl(data.share_url);
        url = data.share_url;
      }
    }
    if (!url) return;
    const shareToken = url.split('/').pop();
    const backendBase = API_BASE.replace('/api/v1', '');
    const a = document.createElement('a');
    a.href = `${backendBase}/share/${shareToken}/card.png`;
    a.download = 'astrea-timeline-card.png';
    a.click();
  }

  useEffect(() => {
    if (!chartId) return;
    setLoading(true);

    // Anonymous chart — load from sessionStorage
    if (chartId === 'anonymous') {
      try {
        const raw = sessionStorage.getItem('anonymous_chart_result');
        if (raw) {
          setChart(JSON.parse(raw));
        } else {
          setError('Данные карты не найдены. Рассчитайте карту заново.');
        }
      } catch {
        setError('Ошибка загрузки карты.');
      }
      setLoading(false);
      return;
    }

    const token = localStorage.getItem('astro_access_token');
    fetch(`${API_BASE}/chart/${chartId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => { if (!r.ok) throw new Error('Карта не найдена'); return r.json(); })
      .then(data => {
        setChart(data);
        localStorage.setItem('astro_last_chart_id', chartId);
        if (data.name) localStorage.setItem('astro_last_chart_name', data.name);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [chartId]);

  // Загружаем транзитные позиции при открытии вкладки транзитов
  useEffect(() => {
    if (topTab !== 'transits' || !chart || !chartId || chartId === 'anonymous' || transitPlanets.length > 0) return;
    const token = localStorage.getItem('astro_access_token');
    fetch(`${API_BASE}/chart/${chartId}/transits/positions?on_date=${selectedDate}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.planets?.length) setTransitPlanets(data.planets); })
      .catch(() => {});
  }, [topTab, chart, chartId]);

  useEffect(() => {
    // Не блокируем вкладку транзитов — блюр внутри компонента TransitTimeline
  }, [activeTab, currentUser]);

  function handleTopTabChange(key) {
    setTopTab(key);
    setActiveTab(key); // keep transit/planner logic
    setSearchParams({ tab: key });
  }

  function handleLeftBtn(key) {
    setLeftPanel(prev => prev === key ? null : key);
  }

  function handleTabChange(key, minTier) {
    if (!tierAllowed(minTier)) {
      setShowPaywall(true);
      return;
    }
    handleTopTabChange(key);
  }

  function handleDateSelect(date, dayEvents, positions) {
    setTransitPlanets(positions ?? []);
    if (date) setSelectedDate(date);
  }

  function handleShowAuth() {
    onShowAuth?.();
  }

  if (loading) return <Centered text="Загружаем карту…" />;
  if (error)   return <Centered text={error} danger />;
  if (!chart)  return null;

  const isAnon = !currentUser;

  return (
    <div style={s.page}>

      {/* ── Шапка ── */}
      <header style={s.header}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <h1 style={s.title}>Карта {chart.name ?? currentUser?.email?.split('@')[0] ?? ''}</h1>
            <p style={{ ...s.subtitle, margin: 0 }}>{chart.birth_date} · {chart.birth_place}</p>
            <StreakBadge streak={streak} isNew={isNew} />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {currentUser && (
            <button onClick={handleDownloadCard} style={s.plannerLinkBtn} title="Скачать карточку для Stories">
              🖼 Карточка
            </button>
          )}
          <button onClick={() => setShowReport(true)} style={{ ...s.plannerLinkBtn, background: '#1E1A2E', color: '#fff' }}>
            📄 PDF-отчёт
          </button>
        </div>
      </header>

      {/* ── Горизонтальная группа вкладок ── */}
      <div style={s.topTabBar}>
        {TOP_TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => {
              if (key === 'lunar') { navigate(`/lunar?chartId=${chartId}`); return; }
              if (key === 'planner') { navigate(`/planner/${chartId}`); return; }
              handleTopTabChange(key);
            }}
            style={{ ...s.topTabBtn, ...(topTab === key ? s.topTabActive : {}) }}
          >
            {label}
            {topTab === key && <span style={s.topTabUnderline} />}
          </button>
        ))}
      </div>

      {/* ── Натальная карта: 3 колонки ── */}
      {topTab === 'chart' && (
        <div style={s.threeCol}>

          {/* ── Левая колонка: вертикальные кнопки ── */}
          <div style={s.leftCol}>
            {isAnon && (
              <div style={{ marginBottom: 8 }}>
                <SaveChartBanner onLogin={handleShowAuth} />
              </div>
            )}
            <OnboardingTooltips />
            {LEFT_BTNS.map(({ key, label, icon }) => (
              <button
                key={key}
                onClick={() => handleLeftBtn(key)}
                style={{ ...s.leftBtn, ...(leftPanel === key ? s.leftBtnActive : {}) }}
              >
                <span style={s.leftBtnIcon}>{icon}</span>
                <span style={{ flex: 1 }}>{label}</span>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)', opacity: 0.6 }}>
                  {leftPanel === key ? '‹' : '›'}
                </span>
              </button>
            ))}

            {/* Поделиться — под картой слева */}
            <button
              onClick={handleShare}
              disabled={shareLoading}
              style={{ ...s.leftBtn, marginTop: 8 }}
              title="Скопировать ссылку"
            >
              <span style={s.leftBtnIcon}>🔗</span>
              <span style={{ flex: 1 }}>{shareLoading ? '⏳' : copied ? '✓ Скопировано' : 'Поделиться'}</span>
            </button>
          </div>

          {/* ── Центр: колесо карты ── */}
          <div style={s.centerCol}>
            <div style={s.wheelCard}>
              {/* Интерпретация — поверх карты */}
              {leftPanel === 'interpretation' && (
                <div style={s.wheelOverlay}>
                  {isAnon ? (
                    <div style={s.overlayBlurWrap}>
                      <div style={{ filter: 'blur(5px)', pointerEvents: 'none', userSelect: 'none', maxHeight: 320, overflow: 'hidden' }}>
                        <Interpretation chartId={chartId} userTier="free" onUpgrade={() => {}} />
                      </div>
                      <div style={s.overlayLogin}>
                        <div style={{ fontSize: 15, fontWeight: 700, color: '#fff', textAlign: 'center' }}>✦ Войдите, чтобы прочитать интерпретацию</div>
                        <button onClick={handleShowAuth} style={s.overlayLoginBtn}>Войти / Регистрация</button>
                      </div>
                    </div>
                  ) : currentUser?.tier === 'lite' ? (
                    <Interpretation chartId={chartId} userTier="lite" onUpgrade={() => { setPaywallContext('lite_to_pro'); setShowPaywall(true); }} />
                  ) : (
                    <Interpretation chartId={chartId} userTier={currentUser?.tier || 'free'} onUpgrade={() => { setPaywallContext('free_to_lite'); setShowPaywall(true); }} />
                  )}
                </div>
              )}

              <NatalChart
                planets={chart.planets}
                houses={chart.houses}
                aspects={chart.aspects}
                ascendant={chart.ascendant}
                midheaven={chart.midheaven}
                timeUnknown={chart.time_unknown}
                transitPlanets={[]}
              />
            </div>
          </div>

          {/* ── Правая колонка: панели ── */}
          <div style={s.rightCol}>

            {/* Построить карту */}
            {leftPanel === 'build' && (
              <div style={s.panelCard}>
                <div style={s.panelTitle}>✦ Построить карту</div>
                <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, margin: '8px 0 0' }}>
                  Перейдите на главную страницу, чтобы рассчитать новую карту.
                </p>
                <button
                  onClick={() => navigate('/home')}
                  style={{ marginTop: 12, padding: '8px 16px', borderRadius: 8, background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, fontFamily: 'inherit' }}
                >
                  На главную
                </button>
              </div>
            )}

            {/* Таблица планет/домов */}
            {leftPanel === 'planets' && (
              <div style={s.panelCard}>
                <div style={s.panelTitle}>☉ Позиции планет</div>
                <PlanetTable
                  planets={chart.planets}
                  ascendant={chart.ascendant}
                  midheaven={chart.midheaven}
                  collapsed
                />
                {chart.houses?.length > 0 && (
                  <>
                    <div style={s.panelDivider}>Дома</div>
                    <HouseTable houses={chart.houses} collapsed />
                  </>
                )}
              </div>
            )}

            {/* Таблица аспектов */}
            {leftPanel === 'aspects' && (
              <div style={s.panelCard}>
                <div style={s.panelTitle}>△ Аспекты</div>
                <AspectLegend />
                <div style={{ marginTop: 12 }}>
                  <AspectGrid aspects={chart.aspects} planets={chart.planets} />
                </div>
                <div style={{ marginTop: 12 }}>
                  <AspectTable aspects={chart.aspects} planets={chart.planets} />
                </div>
              </div>
            )}

            {/* AI Чат */}
            {leftPanel === 'chat' && (
              <div style={{ ...s.panelCard, padding: 0, minHeight: 480 }}>
                {tierAllowed('pro') ? (
                  <RagChat
                    chartId={chartId}
                    onPaywall={() => setShowPaywall(true)}
                  />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 480, gap: 12, color: '#64748b' }}>
                    <span style={{ fontSize: 40 }}>🔒</span>
                    <div style={{ fontWeight: 700, fontSize: 16, color: '#1e293b' }}>AI Астролог Астрея</div>
                    <div style={{ fontSize: 13, textAlign: 'center', maxWidth: 260 }}>Доступно на тарифах Pro и Premium</div>
                    <button onClick={() => { setPaywallContext(currentUser?.tier === 'lite' ? 'lite_to_pro' : 'free_to_lite'); setShowPaywall(true); }} style={{ marginTop: 8, padding: '10px 24px', borderRadius: 50, border: 'none', background: 'linear-gradient(135deg, #7C6CFF, #C060A0)', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>
                      Открыть доступ
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Мини-таблица планет (дефолтная правая панель когда ничего не выбрано) */}
            {!leftPanel && (
              <div style={s.miniTableCard}>
                <PlanetTable
                  planets={chart.planets}
                  ascendant={chart.ascendant}
                  midheaven={chart.midheaven}
                />
              </div>
            )}
          </div>

        </div>
      )}

      {/* ── Транзиты ── */}
      {topTab === 'transits' && (
        <div style={{ position: 'relative' }}>
          <div style={showPaywall ? { filter: 'blur(4px)', pointerEvents: 'none', userSelect: 'none' } : {}}>
            <main style={s.main}>
              <section style={s.card}>
                <div style={s.transitDateLabel}>
                  Транзиты на {new Date(selectedDate + 'T00:00:00').toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}
                </div>
                <NatalChart
                  planets={chart.planets}
                  houses={chart.houses}
                  aspects={chart.aspects}
                  ascendant={chart.ascendant}
                  midheaven={chart.midheaven}
                  timeUnknown={chart.time_unknown}
                  transitPlanets={transitPlanets}
                />
              </section>
              <section style={{ ...s.card, padding: 0, overflow: 'hidden' }}>
                <TransitTimeline chartId={chartId} onDateSelect={handleDateSelect} mockMode={false} userTier={currentUser?.tier || 'free'} onUpgrade={(ctx) => { setPaywallContext(ctx || (currentUser?.tier === 'lite' ? 'lite_to_pro' : 'free_to_lite')); setShowPaywall(true); }} />
              </section>
            </main>
          </div>
        </div>
      )}

      {/* ── Планировщик ── */}
      {topTab === 'planner' && (
        <main style={s.main}>
          <section style={s.card}>
            <div style={s.plannerHead}>
              <span style={s.plannerTitle}>Планировщик</span>
              <span style={s.plannerSub}>
                {new Date(selectedDate + 'T00:00:00').toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}
              </span>
            </div>
            <ForecastScale chartId={chartId} selectedDate={selectedDate} />
          </section>
        </main>
      )}

      {showPaywall && (
        <PaywallModal context={paywallContext} chartId={chartId} onClose={() => setShowPaywall(false)} />
      )}

      {showReport && (
        <ReportModal chartId={chartId} onClose={() => setShowReport(false)} />
      )}

    </div>
  );
}

// ── Символы и русские названия планет ──
const PLANET_GLYPHS = {
  Sun: '☉', Moon: '☽', Mercury: '☿', Venus: '♀', Mars: '♂',
  Jupiter: '♃', Saturn: '♄', Uranus: '♅', Neptune: '♆', Pluto: '♇',
  'North Node': '☊', 'South Node': '☋', Chiron: '⚷', Lilith: '⚸',
  'Vertex': 'Vx', 'Part of Fortune': '⊕', 'Ascendant': 'AC', 'Midheaven': 'MC',
};

const PLANET_NAMES_RU = {
  Sun: 'Солнце', Moon: 'Луна', Mercury: 'Меркурий', Venus: 'Венера',
  Mars: 'Марс', Jupiter: 'Юпитер', Saturn: 'Сатурн', Uranus: 'Уран',
  Neptune: 'Нептун', Pluto: 'Плутон', 'North Node': 'Восх. узел',
  'South Node': 'Низх. узел', Chiron: 'Хирон', Lilith: 'Лилит',
  Vertex: 'Вертекс', 'Part of Fortune': 'П.Фортуны',
  Ascendant: 'Асцендент', Midheaven: 'Сер. Неба',
};

const SIGN_GLYPHS = {
  Aries: '♈', Taurus: '♉', Gemini: '♊', Cancer: '♋', Leo: '♌', Virgo: '♍',
  Libra: '♎', Scorpio: '♏', Sagittarius: '♐', Capricorn: '♑', Aquarius: '♒', Pisces: '♓',
};

const SIGN_NAMES_RU = {
  Aries: 'Овен', Taurus: 'Телец', Gemini: 'Близнецы', Cancer: 'Рак',
  Leo: 'Лев', Virgo: 'Дева', Libra: 'Весы', Scorpio: 'Скорпион',
  Sagittarius: 'Стрелец', Capricorn: 'Козерог', Aquarius: 'Водолей', Pisces: 'Рыбы',
};

function formatDeg(deg) {
  if (deg == null) return '';
  const d = Math.floor(deg);
  const rem = (deg - d) * 60;
  const m = Math.floor(rem);
  const s = Math.round((rem - m) * 60);
  return `${d}° ${String(m).padStart(2, '0')}' ${String(s).padStart(2, '0')}''`;
}

function PlanetTable({ planets = [], ascendant, midheaven, collapsed }) {
  const [expanded, setExpanded] = React.useState(false);
  const rows = [
    ...planets,
    ...(ascendant ? [{ name: 'Ascendant', longitude: ascendant.longitude, sign: ascendant.sign, degree_in_sign: ascendant.degree_in_sign, retrograde: false }] : []),
    ...(midheaven ? [{ name: 'Midheaven', longitude: midheaven.longitude, sign: midheaven.sign, degree_in_sign: midheaven.degree_in_sign, retrograde: false }] : []),
  ];

  if (!rows.length) return null;

  const PREVIEW = 5;
  const visible = collapsed && !expanded ? rows.slice(0, PREVIEW) : rows;

  return (
    <div style={sp.wrap}>
      <table style={sp.table}>
        <tbody>
          {visible.map((p) => (
            <tr key={p.name} style={sp.row}>
              <td style={sp.glyph}>{PLANET_GLYPHS[p.name] || ''}</td>
              <td style={sp.nameCell}>{PLANET_NAMES_RU[p.name] || p.name}</td>
              <td style={sp.signGlyph}>{SIGN_GLYPHS[p.sign] || ''}</td>
              <td style={sp.signName}>{SIGN_NAMES_RU[p.sign] || p.sign}</td>
              <td style={sp.deg}>{formatDeg(p.degree_in_sign)}</td>
              <td style={sp.retro}>{p.retrograde ? <span style={sp.retroMark}>R</span> : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {collapsed && rows.length > PREVIEW && (
        <button
          onClick={() => setExpanded(e => !e)}
          style={{ fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', marginTop: 6, padding: 0, fontFamily: 'inherit' }}
        >
          {expanded ? '▲ Свернуть' : `▼ Показать все (${rows.length})`}
        </button>
      )}
    </div>
  );
}

function HouseTable({ houses = [], collapsed }) {
  const [expanded, setExpanded] = React.useState(false);
  if (!houses.length) return null;
  const PREVIEW = 5;
  const visible = collapsed && !expanded ? houses.slice(0, PREVIEW) : houses;
  return (
    <div style={sp.wrap}>
      <table style={sp.table}>
        <tbody>
          {visible.map((h, i) => (
            <tr key={i} style={sp.row}>
              <td style={{ ...sp.glyph, fontWeight: 600 }}>{h.house ?? i + 1}</td>
              <td style={sp.signGlyph}>{SIGN_GLYPHS[h.sign] || ''}</td>
              <td style={sp.signName}>{SIGN_NAMES_RU[h.sign] || h.sign}</td>
              <td style={sp.deg}>{formatDeg(h.degree)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {collapsed && houses.length > PREVIEW && (
        <button
          onClick={() => setExpanded(e => !e)}
          style={{ fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', marginTop: 6, padding: 0, fontFamily: 'inherit' }}
        >
          {expanded ? '▲ Свернуть' : `▼ Показать все 12 домов`}
        </button>
      )}
    </div>
  );
}

const sp = {
  wrap: { overflowX: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '12px' },
  row: { borderBottom: '0.5px solid #EDE8F5' },
  glyph: { padding: '4px 6px 4px 0', color: '#7060A0', fontSize: '14px', width: '20px' },
  nameCell: { padding: '4px 8px 4px 0', color: '#1E1A2E', whiteSpace: 'nowrap' },
  signGlyph: { padding: '4px 4px 4px 0', fontSize: '14px', color: '#7060A0', width: '20px' },
  signName: { padding: '4px 6px 4px 0', color: '#7060A0' },
  deg: { padding: '4px 6px 4px 0', color: '#1E1A2E', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' },
  retro: { padding: '4px 0', width: '16px', textAlign: 'center' },
  retroMark: { color: '#e05050', fontWeight: '700', fontSize: '11px' },
};

const ASPECT_LEGEND = [
  { symbol: '☌', name: 'Соединение 0°',  type: 'harmonic' },
  { symbol: '△', name: 'Трин 120°',       type: 'harmonic' },
  { symbol: '⚹', name: 'Секстиль 60°',   type: 'harmonic' },
  { symbol: '✶', name: 'Квинконс 150°',  type: 'harmonic' },
  { symbol: '□', name: 'Квадрат 90°',    type: 'tense'    },
  { symbol: '☍', name: 'Оппозиция 180°', type: 'tense'    },
];

function AspectLegend() {
  return (
    <div style={sl.wrap}>
      {ASPECT_LEGEND.map(({ symbol, name, type }) => (
        <div key={name} style={sl.row}>
          <span style={{ ...sl.sym, color: type === 'tense' ? '#C84040' : '#2060B0' }}>
            {symbol}
          </span>
          <span style={sl.label}>{name}</span>
          <span style={{ ...sl.tag, color: type === 'tense' ? '#C84040' : '#2060B0' }}>
            {type === 'tense' ? 'Напряж.' : 'Гарм.'}
          </span>
        </div>
      ))}
      <div style={sl.retroRow}>
        <span style={sl.retroR}>R</span>
        <span style={sl.label}>— Ретроградный</span>
      </div>
    </div>
  );
}

const sl = {
  wrap: { display: 'flex', flexDirection: 'column', gap: '3px', marginTop: '8px', borderTop: '0.5px solid #EDE8F5', paddingTop: '10px' },
  row: { display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px' },
  sym: { width: '16px', textAlign: 'center', fontSize: '14px', flexShrink: 0 },
  label: { flex: 1, color: '#7060A0' },
  tag: { fontSize: '10px', opacity: 0.8 },
  retroRow: { display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', marginTop: '4px' },
  retroR: { width: '16px', textAlign: 'center', color: '#e05050', fontWeight: '700', fontSize: '12px', flexShrink: 0 },
};

// ── Астро-глоссарий ──
const TOOLTIPS = {
  ASC: 'Асцендент (ASC) — точка горизонта на востоке в момент рождения. Показывает, как вы воспринимаетесь окружающими.',
  MC:  'Середина Неба (MC) — высшая точка неба в момент рождения. Связана с карьерой и жизненным призванием.',
  'аспекты': 'Аспекты — угловые соотношения между планетами. Трин и секстиль — гармоничные, квадрат и оппозиция — напряжённые.',
  'дома': 'Дома — 12 секторов карты, каждый отвечает за свою сферу жизни: 1-й — личность, 7-й — партнёрство, 10-й — карьера.',
};

function TooltipBadge({ term }) {
  const [visible, setVisible] = React.useState(false);
  return (
    <span style={{ position: 'relative', display: 'inline-block' }}>
      <span
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onClick={() => setVisible(v => !v)}
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 16, height: 16, borderRadius: 8,
          background: 'rgba(112,96,160,0.15)', color: '#7060A0',
          fontSize: 10, fontWeight: 700, cursor: 'help',
          border: '1px solid rgba(112,96,160,0.3)',
          userSelect: 'none',
        }}
      >?</span>
      {visible && (
        <div style={{
          position: 'absolute', bottom: '100%', left: '50%',
          transform: 'translateX(-50%)',
          marginBottom: 6, zIndex: 100,
          background: '#1E1A2E', border: '1px solid rgba(112,96,160,0.3)',
          borderRadius: 10, padding: '10px 14px',
          width: 220, fontSize: 12, lineHeight: 1.6,
          color: '#C8CAD8', boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
          pointerEvents: 'none',
        }}>
          <strong style={{ color: '#A090D0' }}>{term}</strong><br />
          {TOOLTIPS[term]}
        </div>
      )}
    </span>
  );
}

function AstroGlossary() {
  return (
    <>
      <p style={{ fontSize: 12, color: '#9080B0', marginBottom: 12, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        Что означают термины в карте
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
        {Object.keys(TOOLTIPS).map(term => (
          <span key={term} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#1E1A2E' }}>
            {term} <TooltipBadge term={term} />
          </span>
        ))}
      </div>
    </>
  );
}

function Centered({ text, danger }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '300px' }}>
      <p style={{ color: danger ? '#C03030' : '#7060A0', fontSize: '14px' }}>{text}</p>
    </div>
  );
}

// ── Accordion Panel ──
function AccordionPanel({ label, icon, children, defaultOpen = false }) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div style={sa.wrap}>
      <button style={sa.header} onClick={() => setOpen(o => !o)}>
        <span style={sa.icon}>{icon}</span>
        <span style={sa.label}>{label}</span>
        <span style={{ ...sa.arrow, transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}>›</span>
      </button>
      {open && <div style={sa.body}>{children}</div>}
    </div>
  );
}

const sa = {
  wrap: {
    borderRadius: 10,
    border: '0.5px solid var(--border)',
    background: 'var(--bg-card)',
    overflow: 'hidden',
  },
  header: {
    width: '100%',
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '10px 14px',
    background: 'none', border: 'none',
    cursor: 'pointer', fontFamily: 'inherit',
    fontSize: 13, fontWeight: 500,
    color: 'var(--text-primary)',
    textAlign: 'left',
  },
  icon: { fontSize: 14, color: 'var(--accent)', flexShrink: 0 },
  label: { flex: 1 },
  arrow: {
    fontSize: 18, color: 'var(--text-secondary)',
    transition: 'transform 0.2s ease',
    lineHeight: 1,
  },
  body: {
    padding: '0 14px 14px',
    borderTop: '0.5px solid var(--border)',
  },
};

const s = {
  page: { minHeight: '100vh', background: 'var(--bg)', paddingBottom: '60px' },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '18px 24px 14px',
    background: 'var(--bg-card)',
    borderBottom: '0.5px solid var(--border)',
    flexWrap: 'wrap', gap: '10px',
  },
  title:    { margin: 0, fontSize: '18px', fontWeight: '500', color: 'var(--text-primary)' },
  subtitle: { margin: '2px 0 0', fontSize: '12px', color: 'var(--text-secondary)' },

  // ── Горизонтальная группа вкладок ──
  topTabBar: {
    display: 'flex',
    background: 'var(--bg-card)',
    borderBottom: '0.5px solid var(--border)',
    padding: '0 24px',
    gap: 0,
  },
  topTabBtn: {
    position: 'relative',
    padding: '12px 20px',
    background: 'none', border: 'none',
    color: 'var(--text-secondary)',
    fontSize: '14px', fontWeight: '400',
    cursor: 'pointer', fontFamily: 'inherit',
    transition: 'color 0.15s',
    whiteSpace: 'nowrap',
  },
  topTabActive: { color: 'var(--text-primary)', fontWeight: '600' },
  topTabUnderline: {
    position: 'absolute', bottom: -1, left: '20px', right: '20px', height: 2,
    background: 'var(--accent)',
    borderRadius: '2px 2px 0 0',
    display: 'block',
  },

  // ── 3-колоночный layout ──
  threeCol: {
    display: 'flex',
    gap: 0,
    alignItems: 'flex-start',
    padding: '16px',
    maxWidth: '1400px',
    margin: '0 auto',
    flexWrap: 'wrap',
  },
  leftCol: {
    display: 'flex', flexDirection: 'column', gap: 6,
    flex: '0 0 200px', minWidth: 180,
    paddingRight: 12,
  },
  leftBtn: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '10px 14px',
    background: 'var(--bg-card)',
    border: '0.5px solid var(--border)',
    borderRadius: 10,
    cursor: 'pointer', fontFamily: 'inherit',
    fontSize: 13, fontWeight: 500,
    color: 'var(--text-primary)',
    textAlign: 'left',
    transition: 'border-color 0.15s, background 0.15s',
    width: '100%',
  },
  leftBtnActive: {
    background: 'rgba(124,108,255,0.08)',
    borderColor: 'var(--accent)',
    color: 'var(--accent)',
  },
  leftBtnIcon: { fontSize: 14, color: 'var(--accent)', flexShrink: 0 },

  // Центральная колонка — колесо
  centerCol: {
    flex: '1 1 320px',
    minWidth: 280,
    paddingRight: 12,
  },
  wheelCard: {
    position: 'relative',
    background: 'var(--bg-card)',
    borderRadius: 16,
    border: '0.5px solid var(--border)',
    padding: 12,
    overflow: 'hidden',
  },
  wheelOverlay: {
    position: 'absolute', inset: 0, zIndex: 10,
    background: 'var(--bg-card)',
    borderRadius: 16,
    overflowY: 'auto',
    padding: 20,
  },
  overlayBlurWrap: { position: 'relative' },
  overlayLogin: {
    position: 'absolute', inset: 0,
    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    gap: 12, background: 'rgba(30,26,46,0.55)', borderRadius: 16,
  },
  overlayLoginBtn: {
    padding: '10px 24px', borderRadius: 10, border: 'none',
    background: 'linear-gradient(135deg, #7C6CFF, #C060A0)',
    color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer',
  },

  // Правая колонка — панель
  rightCol: {
    flex: '0 0 290px', minWidth: 220,
  },
  panelCard: {
    background: 'var(--bg-card)', borderRadius: 16,
    border: '0.5px solid var(--border)', padding: '16px',
    maxHeight: 'calc(100vh - 200px)', overflowY: 'auto',
  },
  panelTitle: {
    fontSize: 14, fontWeight: 600, color: 'var(--text-primary)',
    marginBottom: 10,
  },
  panelDivider: {
    fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
    textTransform: 'uppercase', letterSpacing: '0.06em',
    margin: '14px 0 8px',
    paddingTop: 10, borderTop: '0.5px solid var(--border)',
  },

  miniTableCard: {
    background: 'var(--bg-card)', borderRadius: 16,
    border: '0.5px solid var(--border)', padding: '14px 16px',
    maxHeight: 'calc(100vh - 200px)', overflowY: 'auto',
  },

  // Прочее (для транзитов / планировщика)
  main: {
    maxWidth: '900px', margin: '0 auto',
    padding: '20px 16px',
    display: 'flex', flexDirection: 'column', gap: '16px',
  },
  transitDateLabel: { fontSize: '13px', fontWeight: '500', color: 'var(--text-secondary)', marginBottom: '14px' },
  card: { background: 'var(--bg-card)', borderRadius: '16px', border: '0.5px solid var(--border)', padding: '20px' },
  plannerHead: { marginBottom: '14px' },
  plannerTitle: { fontSize: '15px', fontWeight: '500', color: 'var(--text-primary)', display: 'block' },
  plannerSub:   { fontSize: '12px', color: 'var(--text-secondary)', display: 'block', marginTop: '2px' },
  plannerLinkBtn: {
    padding: '8px 14px',
    fontSize: '13px',
    fontWeight: '500',
    background: 'var(--bg)',
    color: 'var(--text-primary)',
    border: '0.5px solid var(--border)',
    borderRadius: '8px',
    cursor: 'pointer',
    fontFamily: 'inherit',
    whiteSpace: 'nowrap',
    transition: 'background 0.15s',
  },
};
