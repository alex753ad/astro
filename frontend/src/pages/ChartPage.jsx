/**
 * ChartPage.jsx — три вкладки: Натальная карта / Транзиты / Планировщик
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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

const TABS = [
  { key: 'chart',    label: 'Натальная карта' },
  { key: 'transits', label: 'Транзиты'        },
  { key: 'planner',  label: 'Планировщик'     },
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

export default function ChartPage({ currentUser, onShowAuth }) {
  const { chartId } = useParams();
  const navigate = useNavigate();

  const [chart, setChart]                   = useState(null);
  const [transitPlanets, setTransitPlanets] = useState([]);
  const [selectedDate, setSelectedDate]     = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [activeTab, setActiveTab] = useState('chart');
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [showPaywall, setShowPaywall] = useState(false);

  const { expertMode, toggleExpertMode } = useExpertMode(currentUser?.id ?? null);

  useEffect(() => {
    if (!chartId) return;
    setLoading(true);
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
    if (activeTab !== 'transits' || !chart || !chartId || transitPlanets.length > 0) return;
    const token = localStorage.getItem('astro_access_token');
    fetch(`${API_BASE}/chart/${chartId}/transits/positions?on_date=${selectedDate}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.planets?.length) setTransitPlanets(data.planets); })
      .catch(() => {});
  }, [activeTab, chart, chartId]);

  useEffect(() => {
    if (activeTab === 'transits' && (!currentUser || currentUser.tier === 'free')) {
      setShowPaywall(true);
    }
  }, [activeTab, currentUser]);

  function handleTabChange(key) {
    if (key === 'transits' && (!currentUser || currentUser.tier === 'free')) {
      setActiveTab(key);
      setShowPaywall(true);
      return;
    }
    setActiveTab(key);
  }

  function handleDateSelect(positions, date) {
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
          <p style={s.subtitle}>{chart.birth_date} · {chart.birth_place}</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            onClick={() => navigate(`/planner/${chartId}`)}
            style={s.plannerLinkBtn}
          >
            📅 Планер на месяц
          </button>
          <button
            onClick={() => navigate(`/lunar?chartId=${chartId}`)}
            style={s.plannerLinkBtn}
          >
            🌙 Лунный календарь
          </button>
          {activeTab === 'chart' && (
            <ExpertModeToggle enabled={expertMode} onToggle={toggleExpertMode} />
          )}
        </div>
      </header>

      {/* ── Вкладки ── */}
      <div style={s.tabBar}>
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => handleTabChange(key)}
            style={{ ...s.tabBtn, ...(activeTab === key ? s.tabBtnActive : {}) }}
          >
            {label}
            {activeTab === key && <span style={s.tabUnderline} />}
          </button>
        ))}
      </div>

      {/* ── Вкладка: Натальная карта ── */}
      {activeTab === 'chart' && (
        <main style={s.main}>

          {/* Баннер сохранения для анонима */}
          {isAnon && (
            <SaveChartBanner onLogin={handleShowAuth} />
          )}

          <section style={s.card}>
            <div style={s.chartWithData}>
              <NatalChart
                planets={chart.planets}
                houses={chart.houses}
                aspects={chart.aspects}
                ascendant={chart.ascendant}
                midheaven={chart.midheaven}
                timeUnknown={chart.time_unknown}
                transitPlanets={transitPlanets}
              />
              <div style={s.chartSidePanel}>
                <PlanetTable
                  planets={chart.planets}
                  ascendant={chart.ascendant}
                  midheaven={chart.midheaven}
                  northNode={chart.north_node}
                  extra={chart.extra_points}
                />
                <AspectLegend />
              </div>
            </div>
          </section>

          <section style={s.card}>
            <ChartSummary planets={chart.planets} houses={chart.houses} />
          </section>

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
            <Interpretation chartId={chartId} userTier={currentUser?.tier || 'free'} onUpgrade={() => setShowPaywall(true)} />
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
                <TransitTimeline chartId={chartId} onDateSelect={handleDateSelect} mockMode={!currentUser || currentUser.tier === 'free'} userTier={currentUser?.tier || 'free'} onUpgrade={() => setShowPaywall(true)} />
              </section>
            </main>
          </div>
        </div>
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
        <PaywallModal
          chartId={chartId}
          onClose={() => setShowPaywall(false)}
        />
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

function Centered({ text, danger }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '300px' }}>
      <p style={{ color: danger ? '#C03030' : '#7060A0', fontSize: '14px' }}>{text}</p>
    </div>
  );
}

const s = {
  page: { minHeight: '100vh', background: '#F4F0FA', paddingBottom: '60px' },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '18px 24px 14px',
    background: '#FFFFFF',
    borderBottom: '0.5px solid #EDE8F5',
    flexWrap: 'wrap', gap: '10px',
  },
  title:    { margin: 0, fontSize: '18px', fontWeight: '500', color: '#1E1A2E' },
  subtitle: { margin: '2px 0 0', fontSize: '12px', color: '#7060A0' },
  tabBar: {
    display: 'flex',
    background: '#FFFFFF',
    borderBottom: '0.5px solid #EDE8F5',
    padding: '0 24px',
    gap: '0',
  },
  tabBtn: {
    position: 'relative',
    padding: '12px 20px',
    background: 'none', border: 'none',
    color: '#7060A0',
    fontSize: '14px', fontWeight: '400',
    cursor: 'pointer', fontFamily: 'inherit',
    transition: 'color 0.15s',
    whiteSpace: 'nowrap',
  },
  tabBtnActive: { color: '#1E1A2E', fontWeight: '500' },
  tabUnderline: {
    position: 'absolute', bottom: -1, left: '20px', right: '20px', height: 2,
    background: '#1E1A2E',
    borderRadius: '2px 2px 0 0',
    display: 'block',
  },
  main: {
    maxWidth: '900px', margin: '0 auto',
    padding: '20px 16px',
    display: 'flex', flexDirection: 'column', gap: '16px',
  },
  transitDateLabel: { fontSize: '13px', fontWeight: '500', color: '#7060A0', marginBottom: '14px' },
  card: { background: '#FFFFFF', borderRadius: '16px', border: '0.5px solid #EDE8F5', padding: '20px' },
  plannerHead: { marginBottom: '14px' },
  plannerTitle: { fontSize: '15px', fontWeight: '500', color: '#1E1A2E', display: 'block' },
  plannerSub:   { fontSize: '12px', color: '#9080B0', display: 'block', marginTop: '2px' },
  chartWithData: { display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'flex-start' },
  chartSidePanel: { flex: '1 1 260px', minWidth: '220px', display: 'flex', flexDirection: 'column', gap: '16px' },
  plannerLinkBtn: {
    padding: '8px 14px',
    fontSize: '13px',
    fontWeight: '500',
    background: '#F4F0FA',
    color: '#1E1A2E',
    border: '0.5px solid #EDE8F5',
    borderRadius: '8px',
    cursor: 'pointer',
    fontFamily: 'inherit',
    whiteSpace: 'nowrap',
    transition: 'background 0.15s',
  },
};
