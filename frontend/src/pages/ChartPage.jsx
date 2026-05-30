/**
 * ChartPage.jsx — вкладки: Карта / Интерпретация / Аспекты / Транзиты / Планировщик
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import NatalChart from '../components/NatalChart';
import ChartSummary from '../components/ChartSummary';
import AspectTableWrapper from '../components/AspectTableWrapper';
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

  // ── Скачать бесплатный PDF через Celery ──
  async function handleDownloadFree() {
    setLoading('free');
    setError(null);
    setPdfStep('Запускаем генерацию…');
    try {
      const { task_id } = await startPdfGeneration(chartId);
      const result = await pollTask(
        task_id,
        ({ status, step }) => setPdfStep(
          step === 'loading_chart'  ? 'Загружаем данные карты…' :
          step === 'rendering_pdf'  ? 'Рендерим PDF…'           :
          'Обрабатываем…'
        ),
      );
      // Декодируем base64 и скачиваем
      const binary = atob(result.pdf_base64);
      const bytes  = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes], { type: 'application/pdf' });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = result.filename;
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

const TABS = [
  { key: 'chart',          label: 'Карта',          minTier: null },
  { key: 'interpretation', label: 'Интерпретация',  minTier: null },
  { key: 'aspects',        label: 'Аспекты',        minTier: null },
  { key: 'transits',       label: 'Транзиты',       minTier: null },
  { key: 'chat',           label: '💬 Чат',         minTier: 'pro' },
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
  const [activeTab, setActiveTab]     = useState(searchParams.get('tab') || 'chart');
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
      .then(setChart)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [chartId]);

  // Загружаем транзитные позиции при открытии вкладки транзитов
  useEffect(() => {
    if (activeTab !== 'transits' || !chart || !chartId || chartId === 'anonymous' || transitPlanets.length > 0) return;
    const token = localStorage.getItem('astro_access_token');
    fetch(`${API_BASE}/chart/${chartId}/transits/positions?on_date=${selectedDate}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.planets?.length) setTransitPlanets(data.planets); })
      .catch(() => {});
  }, [activeTab, chart, chartId]);

  useEffect(() => {
    // Не блокируем вкладку транзитов — блюр внутри компонента TransitTimeline
  }, [activeTab, currentUser]);

  function handleTabChange(key, minTier) {
    if (!tierAllowed(minTier)) {
      setShowPaywall(true);
      return;
    }
    setActiveTab(key);
    setSearchParams({ tab: key });
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
          <h1 style={s.title}>{chart.name ?? 'Натальная карта'}</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
            <p style={{ ...s.subtitle, margin: 0 }}>{chart.birth_date} · {chart.birth_place}</p>
            <StreakBadge streak={streak} isNew={isNew} />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <button onClick={() => {
            if (!currentUser) { onShowAuth?.(); return; }
            navigate(`/planner/${chartId}`);
          }} style={s.plannerLinkBtn}>
            📅 Планер
          </button>
          <button onClick={() => navigate(`/lunar?chartId=${chartId}`)} style={s.plannerLinkBtn}>
            🌙 Луна
          </button>
          <button onClick={handleShare} style={s.plannerLinkBtn} title="Скопировать ссылку" disabled={shareLoading}>
            {shareLoading ? '⏳' : copied ? '✓ Скопировано' : '🔗 Поделиться'}
          </button>
          {currentUser && (
            <button onClick={handleDownloadCard} style={s.plannerLinkBtn} title="Скачать карточку для Stories">
              🖼 Карточка
            </button>
          )}
          <button onClick={() => setShowReport(true)} style={{ ...s.plannerLinkBtn, background: '#1E1A2E', color: '#fff' }}>
            📄 PDF-отчёт
          </button>
          {/* ExpertModeToggle hidden */}
        </div>
      </header>

      {/* ── Вкладки ── */}
      <div style={s.tabBar}>
        {TABS.map(({ key, label, minTier }) => (
          <button
            key={key}
            onClick={() => handleTabChange(key, minTier)}
            style={{ ...s.tabBtn, ...(activeTab === key ? s.tabBtnActive : {}) }}
          >
            {label}
            {!tierAllowed(minTier) && <span style={{ marginLeft: 4, fontSize: 10 }}>🔒</span>}
            {activeTab === key && <span style={s.tabUnderline} />}
          </button>
        ))}
      </div>

      {/* ── Вкладка: Натальная карта ── */}
      {activeTab === 'chart' && (
        <main style={s.main}>

          {/* D1: Онбординг-тултипы для новых пользователей */}
          <OnboardingTooltips />

          {/* Баннер сохранения для анонима */}
          {isAnon && (
            <SaveChartBanner onLogin={handleShowAuth} />
          )}

          <section style={s.card}>
            <NatalChart
              planets={chart.planets}
              houses={chart.houses}
              aspects={chart.aspects}
              ascendant={chart.ascendant}
              midheaven={chart.midheaven}
              timeUnknown={chart.time_unknown}
              transitPlanets={[]}
            />
          </section>

          <section style={s.card}>
            <PlanetTable
              planets={chart.planets}
              ascendant={chart.ascendant}
              midheaven={chart.midheaven}
              northNode={chart.north_node}
              extra={chart.extra_points}
            />
          </section>

          <section style={s.card}>
            <AspectLegend />
          </section>

          <section style={s.card}>
            <ChartSummary planets={chart.planets} houses={chart.houses} />
          </section>

        </main>
      )}

      {/* ── Вкладка: Интерпретация ── */}
      {activeTab === 'interpretation' && (
        <main style={s.main}>
          {isAnon && <SaveChartBanner onLogin={handleShowAuth} />}
          <section style={s.card}>
            {isAnon ? (
              <div style={{ position: 'relative' }}>
                <div style={{ filter: 'blur(5px)', pointerEvents: 'none', userSelect: 'none', maxHeight: 320, overflow: 'hidden' }}>
                  <Interpretation chartId={chartId} userTier="free" onUpgrade={() => {}} />
                </div>
                <div style={{
                  position: 'absolute', inset: 0,
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  gap: 12, background: 'rgba(30,26,46,0.45)', borderRadius: 16,
                }}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: '#fff', textAlign: 'center' }}>
                    ✦ Войдите, чтобы прочитать интерпретацию
                  </div>
                  <button
                    onClick={handleShowAuth}
                    style={{ padding: '10px 24px', borderRadius: 10, border: 'none', background: 'linear-gradient(135deg, #7C6CFF, #C060A0)', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}
                  >
                    Войти / Регистрация
                  </button>
                </div>
              </div>
            ) : currentUser?.tier === 'lite' ? (
              <div style={{ position: 'relative' }}>
                <div style={{ pointerEvents: 'none', userSelect: 'none', maxHeight: 340, overflow: 'hidden' }}>
                  <Interpretation chartId={chartId} userTier="lite" onUpgrade={() => {}} />
                </div>
                <div style={{
                  position: 'absolute', bottom: 0, left: 0, right: 0,
                  background: 'linear-gradient(to bottom, transparent 0%, rgba(15,17,23,0.97) 60%)',
                  borderRadius: '0 0 16px 16px',
                  padding: '80px 0 24px',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
                  textAlign: 'center',
                }}>
                  <p style={{ fontSize: 13, color: '#8B8FA3', margin: 0, lineHeight: 1.6 }}>
                    Доступен только первый раздел.<br />
                    <strong style={{ color: '#E8EAF0' }}>Pro — полная AI-интерпретация 2500 слов</strong>
                  </p>
                  <button
                    onClick={() => { setPaywallContext('lite_to_pro'); setShowPaywall(true); }}
                    style={{ padding: '11px 28px', borderRadius: 12, border: 'none', background: 'linear-gradient(135deg, #7C6CFF, #C060A0)', color: '#fff', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}
                  >
                    ✦ Перейти на Pro
                  </button>
                </div>
              </div>
            ) : (
              <Interpretation chartId={chartId} userTier={currentUser?.tier || 'free'} onUpgrade={() => { setPaywallContext('free_to_lite'); setShowPaywall(true); }} />
            )}
          </section>
        </main>
      )}

      {/* ── Вкладка: Аспекты ── */}
      {activeTab === 'aspects' && (
        <main style={s.main}>
          <section style={s.card}>
            <AspectGrid aspects={chart.aspects} planets={chart.planets} />
          </section>
          <section style={s.card}>
            <AspectTableWrapper
              expertMode={expertMode}
              aspects={chart.aspects}
              planets={chart.planets}
            />
          </section>
          <section style={s.card}>
            <AstroGlossary />
          </section>
        </main>
      )}

      {/* ── Вкладка: Транзиты ── */}
      {activeTab === 'transits' && (
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

      {/* ── Вкладка: RAG Чат ── */}
      {activeTab === 'chat' && (
        <main style={s.main}>
          <RagChat
            chartId={chartId}
            onPaywall={(ctx) => {
              setShowPaywall(true);
            }}
          />
        </main>
      )}

      {/* ── Вкладка: Планировщик ── */}
      {activeTab === 'planner' && (
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

function PlanetTable({ planets = [], ascendant, midheaven }) {
  const rows = [
    ...planets,
    ...(ascendant ? [{ name: 'Ascendant', longitude: ascendant.longitude, sign: ascendant.sign, degree_in_sign: ascendant.degree_in_sign, retrograde: false }] : []),
    ...(midheaven ? [{ name: 'Midheaven', longitude: midheaven.longitude, sign: midheaven.sign, degree_in_sign: midheaven.degree_in_sign, retrograde: false }] : []),
  ];

  if (!rows.length) return null;

  return (
    <div style={sp.wrap}>
      <table style={sp.table}>
        <tbody>
          {rows.map((p) => (
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
  tabBar: {
    display: 'flex',
    background: 'var(--bg-card)',
    borderBottom: '0.5px solid var(--border)',
    padding: '0 24px',
    gap: '0',
  },
  tabBtn: {
    position: 'relative',
    padding: '12px 20px',
    background: 'none', border: 'none',
    color: 'var(--text-secondary)',
    fontSize: '14px', fontWeight: '400',
    cursor: 'pointer', fontFamily: 'inherit',
    transition: 'color 0.15s',
    whiteSpace: 'nowrap',
  },
  tabBtnActive: { color: 'var(--text-primary)', fontWeight: '500' },
  tabUnderline: {
    position: 'absolute', bottom: -1, left: '20px', right: '20px', height: 2,
    background: 'var(--text-primary)',
    borderRadius: '2px 2px 0 0',
    display: 'block',
  },
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
  chartWithData: { display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'flex-start' },
  chartSidePanel: { flex: '1 1 260px', minWidth: '220px', display: 'flex', flexDirection: 'column', gap: '16px' },
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
