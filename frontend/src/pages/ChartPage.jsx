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
