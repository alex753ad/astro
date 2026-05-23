/**
 * AstroCalendar.jsx
 * Редизайн: «Дыхание космоса» — светлая пастельная тема.
 *
 * Изменения:
 * - Все карточки на белом фоне (bg-astro-card / #FFFFFF)
 * - Скругления rounded-3xl / rounded-2xl
 * - Навигация по месяцам — лёгкие кнопки
 * - Фазы луны — пастельные бейджи вместо тёмных
 * - Убраны все var(--color-*) → инлайн пастельная палитра
 */

import React, { useState, useEffect } from 'react';

const MONTHS_RU = [
  'Январь','Февраль','Март','Апрель','Май','Июнь',
  'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь',
];

// Цвета для типов событий
const EVENT_BADGE = {
  new_moon:  { emoji: '🌑', label: 'Новолуние',     bg: '#F0EAF8', color: '#7040A8' },
  full_moon: { emoji: '🌕', label: 'Полнолуние',    bg: '#FFF5D6', color: '#A07010' },
  ingress:   { emoji: '➡️', label: 'Вход в знак',  bg: '#EAF4FF', color: '#2060A0' },
  aspect:    { emoji: '⚡',  label: 'Аспект',        bg: '#FFF0F5', color: '#A03060' },
};

export default function AstroCalendar() {
  const now  = new Date();
  const [year,  setYear]  = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data,  setData]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  useEffect(() => { load(); }, [year, month]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const monthStr = `${year}-${String(month).padStart(2,'0')}`;
      const res = await fetch(
        `https://astro-production-e070.up.railway.app/api/v1/calendar/monthly?month=${monthStr}`
      );
      if (!res.ok) throw new Error(`${res.status}`);
      setData(await res.json());
    } catch(e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function prev() {
    if (month === 1) { setMonth(12); setYear(y => y - 1); }
    else setMonth(m => m - 1);
  }
  function next() {
    if (month === 12) { setMonth(1); setYear(y => y + 1); }
    else setMonth(m => m + 1);
  }

  const overview  = data?.overview;
  const events    = data?.events || [];
  const newMoon   = events.find(e => e.type === 'new_moon');
  const fullMoon  = events.find(e => e.type === 'full_moon');
  const ingresses = events.filter(e => e.type === 'ingress');
  const aspects   = events.filter(e => e.type === 'aspect');

  return (
    <div style={s.root}>

      {/* ── Навигация ──────────────────────────────────────── */}
      <div style={s.nav}>
        <button onClick={prev} style={s.navBtn}>‹</button>
        <h2 style={s.navTitle}>{MONTHS_RU[month - 1]} {year}</h2>
        <button onClick={next} style={s.navBtn}>›</button>
      </div>

      {loading && <p style={s.muted}>Загружаем календарь…</p>}
      {error   && <p style={s.danger}>Ошибка: {error}</p>}

      {!loading && data && (
        <div style={s.content}>

          {/* ── Обзор месяца ─────────────────────────────── */}
          {overview && (
            <section style={s.card}>
              <h3 style={s.cardTitle}>
                {overview.month_title || `${MONTHS_RU[month-1]} ${year}`}
              </h3>
              {overview.month_tagline && (
                <p style={s.tagline}>{overview.month_tagline}</p>
              )}

              {overview.key_themes?.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <p style={s.sectionLabel}>⚡️ Главные темы</p>
                  <ul style={s.themeList}>
                    {overview.key_themes.map((t, i) => (
                      <li key={i} style={s.themeItem}>• {t}</li>
                    ))}
                  </ul>
                </div>
              )}

              {overview.week_by_week?.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <p style={s.sectionLabel}>Неделя за неделей</p>
                  {overview.week_by_week.map((w, i) => (
                    <div key={i} style={s.weekRow}>
                      <span style={s.weekNum}>Нед. {w.week}</span>
                      <span style={s.weekDates}>{w.dates}</span>
                      <span style={s.weekTone}>{w.tone || w.moon_focus}</span>
                    </div>
                  ))}
                </div>
              )}

              {overview.affirmation && (
                <div style={s.affirmation}>✨ {overview.affirmation}</div>
              )}
            </section>
          )}

          {/* ── Новолуние ─────────────────────────────────── */}
          {(newMoon || overview?.new_moon) && (
            <MoonCard type="new_moon" event={newMoon} detail={overview?.new_moon} />
          )}

          {/* ── Полнолуние ────────────────────────────────── */}
          {(fullMoon || overview?.full_moon) && (
            <MoonCard type="full_moon" event={fullMoon} detail={overview?.full_moon} />
          )}

          {/* ── Переходы планет ───────────────────────────── */}
          {ingresses.length > 0 && (
            <section style={s.card}>
              <p style={s.sectionLabel}>➡️ Переходы планет в знаки</p>
              {ingresses.map((ev, i) => (
                <div key={i} style={s.eventRow}>
                  <span style={s.eventDate}>{ev.date?.slice(5)}</span>
                  <span style={s.eventDesc}>{ev.description}</span>
                  {overview?.planet_ingresses?.find(p => p.planet === ev.planet) && (
                    <span style={s.eventMeaning}>
                      {overview.planet_ingresses.find(p => p.planet === ev.planet)?.meaning}
                    </span>
                  )}
                </div>
              ))}
            </section>
          )}

          {/* ── Аспекты ───────────────────────────────────── */}
          {aspects.length > 0 && (
            <section style={s.card}>
              <p style={s.sectionLabel}>⚡ Значимые аспекты</p>
              {aspects.map((ev, i) => (
                <div key={i} style={s.eventRow}>
                  <span style={s.eventDate}>{ev.date?.slice(5)}</span>
                  <span style={s.eventDesc}>{ev.description}</span>
                </div>
              ))}
            </section>
          )}
        </div>
      )}
    </div>
  );
}

// ── Карточка луны ─────────────────────────────────────────

function MoonCard({ type, event, detail }) {
  const cfg   = EVENT_BADGE[type];
  const date  = event?.date?.slice(5) || detail?.date || '';
  const sign  = event?.sign || detail?.sign || '';
  const title = detail?.title || `${cfg.label} в ${sign}`;
  const desc  = detail?.description || '';

  // Цвет левой полосы по типу
  const borderColor = type === 'new_moon' ? '#C0A0E8' : '#E8C040';

  return (
    <section style={{ ...s.card, borderLeft: `3px solid ${borderColor}` }}>
      <div style={s.moonHeader}>
        <span style={{ fontSize: 24 }}>{cfg.emoji}</span>
        <div>
          <p style={{ ...s.cardTitle, margin: 0 }}>{title}</p>
          {date && <p style={s.moonDate}>{date} UTC</p>}
        </div>
      </div>

      {desc && <p style={s.moonDesc}>{desc}</p>}

      {detail?.key_themes?.length > 0 && (
        <ul style={s.themeList}>
          {detail.key_themes.map((t, i) => <li key={i} style={s.themeItem}>• {t}</li>)}
        </ul>
      )}

      {detail?.do && (
        <div style={{ marginTop: 12 }}>
          <p style={s.sectionLabel}>✅ Что делать</p>
          {Object.entries(detail.do).map(([k, items]) =>
            (items || []).map((item, i) => <p key={`${k}${i}`} style={s.listItem}>{item}</p>)
          )}
        </div>
      )}

      {detail?.avoid?.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <p style={s.sectionLabel}>⚠️ Чего избегать</p>
          {detail.avoid.map((item, i) => <p key={i} style={s.listItem}>{item}</p>)}
        </div>
      )}

      {detail?.ritual && (
        <div style={s.ritualBox}>🌑 Ритуал новолуния: {detail.ritual}</div>
      )}
      {detail?.practice && (
        <div style={s.ritualBox}>🌕 Практика на полнолуние: {detail.practice}</div>
      )}
    </section>
  );
}

// ── Стили ─────────────────────────────────────────────────

const s = {
  root: {
    display: 'flex', flexDirection: 'column', gap: 0,
    fontFamily: "'Space Grotesk', 'Inter', system-ui, sans-serif",
  },
  nav: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: 20,
  },
  navBtn: {
    background: 'none',
    border: '1px solid #E2D9F3',
    borderRadius: 12,
    padding: '6px 16px',
    fontSize: 18,
    color: '#9B7DC8',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  navTitle: {
    margin: 0, fontSize: 18, fontWeight: 600, color: '#2D2540',
  },
  content: { display: 'flex', flexDirection: 'column', gap: 16 },

  // Белые карточки с пастельной тенью
  card: {
    background: '#FFFFFF',
    padding: '18px 20px',
    borderRadius: 20,
    boxShadow: '0 4px 16px -4px rgba(224,195,252,0.25)',
    border: '1px solid #F0EAF8',
  },
  cardTitle: {
    fontSize: 16, fontWeight: 600, color: '#2D2540', margin: '0 0 6px',
  },
  tagline: {
    margin: '0 0 12px', fontSize: 14, color: '#7060A0', fontStyle: 'italic',
  },
  sectionLabel: {
    margin: '0 0 6px', fontSize: 11, fontWeight: 600,
    letterSpacing: '0.06em', textTransform: 'uppercase', color: '#A090C0',
  },
  themeList: { margin: 0, padding: 0, listStyle: 'none' },
  themeItem: { fontSize: 13, lineHeight: 1.7, color: '#3D3560' },
  weekRow: {
    display: 'flex', alignItems: 'center', gap: 10,
    padding: '6px 0', borderBottom: '1px solid #F5F0FC',
  },
  weekNum:   { fontSize: 12, fontWeight: 600, color: '#9B7DC8', width: 56, flexShrink: 0 },
  weekDates: { fontSize: 12, color: '#B0A0C8', width: 48, flexShrink: 0 },
  weekTone:  { fontSize: 13, color: '#3D3560' },
  affirmation: {
    marginTop: 14, padding: '10px 14px', borderRadius: 12,
    background: '#F5F0FF',
    fontSize: 14, fontStyle: 'italic', color: '#7040A8', textAlign: 'center',
  },
  moonHeader: {
    display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 10,
  },
  moonDate: { margin: '2px 0 0', fontSize: 12, color: '#B0A0C8' },
  moonDesc: { margin: '0 0 10px', fontSize: 14, lineHeight: 1.6, color: '#3D3560' },
  ritualBox: {
    marginTop: 10, padding: '10px 14px',
    background: '#FAF5FF',
    borderRadius: 12, fontSize: 13, color: '#5A3880',
  },
  eventRow: {
    display: 'flex', alignItems: 'flex-start', gap: 10,
    padding: '6px 0', borderBottom: '1px solid #F5F0FC',
  },
  eventDate:    { fontSize: 12, color: '#B0A0C8', width: 36, flexShrink: 0 },
  eventDesc:    { fontSize: 13, color: '#3D3560', flex: 1 },
  eventMeaning: { fontSize: 12, color: '#9B7DC8', flex: 1 },
  listItem: { margin: '2px 0', fontSize: 13, lineHeight: 1.5, color: '#3D3560' },
  muted:    { color: '#B0A0C8', fontSize: 13 },
  danger:   { color: '#E05070', fontSize: 13 },
};
