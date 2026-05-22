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
import { useExpertMode } from '../hooks/useExpertMode.js';

const TABS = [
  { key: 'chart',    label: 'Натальная карта' },
  { key: 'transits', label: 'Транзиты'        },
  { key: 'planner',  label: 'Планировщик'     },
];

const API_BASE = 'https://astro-production-e070.up.railway.app/api/v1';

export default function ChartPage({ currentUser }) {
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

  const handleDateSelect = (date, dayEvents, positions) => {
    setTransitPlanets(positions ?? []);
    if (date) setSelectedDate(date);
  };

  if (loading) return <Centered text="Загружаем карту…" />;
  if (error)   return <Centered text={error} danger />;
  if (!chart)  return null;

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
            onClick={() => setActiveTab(key)}
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
            <AspectTableWrapper
              expertMode={expertMode}
              aspects={chart.aspects}
              planets={chart.planets}
            />
          </section>

          <section style={s.card}>
            <Interpretation chartId={chartId} />
          </section>
        </main>
      )}

      {/* ── Вкладка: Транзиты ── */}
      {activeTab === 'transits' && (
        <div style={s.tabContent}>
          <TransitTimeline chartId={chartId} onDateSelect={handleDateSelect} />
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
  Aries: 'Ове', Taurus: 'Тел', Gemini: 'Бли', Cancer: 'Рак',
  Leo: 'Лев', Virgo: 'Дев', Libra: 'Вес', Scorpio: 'Ско',
  Sagittarius: 'Стр', Capricorn: 'Коз', Aquarius: 'Вод', Pisces: 'Рыб',
};

function formatDeg(deg) {
  if (deg == null) return '';
  const d = Math.floor(deg);
  const mTotal = Math.round((deg - d) * 60);
  const m = String(mTotal).padStart(2, '0');
  return `${d}° ${m}'`;
}

function PlanetTable({ planets = [], ascendant, midheaven }) {
  // Build rows: planets first, then ascendant and midheaven
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
  wrap: {
    overflowX: 'auto',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '12px',
  },
  row: {
    borderBottom: '0.5px solid var(--color-border-tertiary)',
  },
  glyph: {
    padding: '4px 6px 4px 0',
    color: 'var(--color-text-secondary)',
    fontSize: '14px',
    width: '20px',
  },
  nameCell: {
    padding: '4px 8px 4px 0',
    color: 'var(--color-text-primary)',
    whiteSpace: 'nowrap',
  },
  signGlyph: {
    padding: '4px 4px 4px 0',
    fontSize: '14px',
    color: 'var(--color-text-secondary)',
    width: '20px',
  },
  signName: {
    padding: '4px 6px 4px 0',
    color: 'var(--color-text-secondary)',
  },
  deg: {
    padding: '4px 6px 4px 0',
    color: 'var(--color-text-primary)',
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
  },
  retro: {
    padding: '4px 0',
    width: '16px',
    textAlign: 'center',
  },
  retroMark: {
    color: '#e05050',
    fontWeight: '700',
    fontSize: '11px',
  },
};

const ASPECT_LEGEND = [
  { symbol: '☌', name: 'Соединение 0°',   type: 'harmonic', deg: 0   },
  { symbol: '△', name: 'Трин 120°',        type: 'harmonic', deg: 120 },
  { symbol: '⚹', name: 'Секстиль 60°',    type: 'harmonic', deg: 60  },
  { symbol: '✶', name: 'Квинконс 150°',   type: 'harmonic', deg: 150 },
  { symbol: '□', name: 'Квадрат 90°',     type: 'tense',    deg: 90  },
  { symbol: '☍', name: 'Оппозиция 180°',  type: 'tense',    deg: 180 },
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
  wrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
    marginTop: '8px',
    borderTop: '0.5px solid var(--color-border-tertiary)',
    paddingTop: '10px',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '11px',
  },
  sym: {
    width: '16px',
    textAlign: 'center',
    fontSize: '14px',
    flexShrink: 0,
  },
  label: {
    flex: 1,
    color: 'var(--color-text-secondary)',
  },
  tag: {
    fontSize: '10px',
    opacity: 0.8,
  },
  retroRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '11px',
    marginTop: '4px',
  },
  retroR: {
    width: '16px',
    textAlign: 'center',
    color: '#e05050',
    fontWeight: '700',
    fontSize: '12px',
    flexShrink: 0,
  },
};

function Centered({ text, danger }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '300px' }}>
      <p style={{ color: danger ? 'var(--color-text-danger)' : 'var(--color-text-secondary)', fontSize: '14px' }}>
        {text}
      </p>
    </div>
  );
}

const s = {
  page: {
    minHeight: '100vh',
    background: 'var(--color-background-tertiary)',
    paddingBottom: '60px',
  },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '18px 24px 14px',
    background: 'var(--color-background-primary)',
    borderBottom: '0.5px solid var(--color-border-tertiary)',
    flexWrap: 'wrap', gap: '10px',
  },
  title:    { margin: 0, fontSize: '18px', fontWeight: '500', color: 'var(--color-text-primary)' },
  subtitle: { margin: '2px 0 0', fontSize: '12px', color: 'var(--color-text-secondary)' },

  // Вкладки
  tabBar: {
    display: 'flex',
    background: 'var(--color-background-primary)',
    borderBottom: '0.5px solid var(--color-border-tertiary)',
    padding: '0 24px',
    gap: '0',
  },
  tabBtn: {
    position: 'relative',
    padding: '12px 20px',
    background: 'none', border: 'none',
    color: 'var(--color-text-secondary)',
    fontSize: '14px', fontWeight: '400',
    cursor: 'pointer', fontFamily: 'inherit',
    transition: 'color 0.15s',
    whiteSpace: 'nowrap',
  },
  tabBtnActive: {
    color: 'var(--color-text-primary)',
    fontWeight: '500',
  },
  tabUnderline: {
    position: 'absolute', bottom: -1, left: '20px', right: '20px', height: 2,
    background: 'var(--color-text-primary)',
    borderRadius: '2px 2px 0 0',
    display: 'block',
  },

  main: {
    maxWidth: '900px', margin: '0 auto',
    padding: '20px 16px',
    display: 'flex', flexDirection: 'column', gap: '16px',
  },
  tabContent: {
    maxWidth: '900px', margin: '0 auto',
  },
  card: {
    background: 'var(--color-background-primary)',
    borderRadius: 'var(--border-radius-lg)',
    border: '0.5px solid var(--color-border-tertiary)',
    padding: '20px',
  },

  plannerHead: { marginBottom: '14px' },
  plannerTitle: { fontSize: '15px', fontWeight: '500', color: 'var(--color-text-primary)', display: 'block' },
  plannerSub:   { fontSize: '12px', color: 'var(--color-text-tertiary)', display: 'block', marginTop: '2px' },

  chartWithData: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '16px',
    alignItems: 'flex-start',
  },
  chartSidePanel: {
    flex: '1 1 260px',
    minWidth: '220px',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },

  plannerLinkBtn: {
    padding: '8px 14px',
    fontSize: '13px',
    fontWeight: '500',
    background: 'var(--color-background-tertiary, #1e293b)',
    color: 'var(--color-text-primary, #e2e8f0)',
    border: '0.5px solid var(--color-border-tertiary, #334155)',
    borderRadius: 'var(--border-radius-md, 8px)',
    cursor: 'pointer',
    fontFamily: 'inherit',
    whiteSpace: 'nowrap',
    transition: 'background 0.15s',
  },
};
