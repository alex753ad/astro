/**
 * AstroCalendar.jsx
 *
 * Общий астро-календарь (бесплатный уровень).
 * Загружает /api/v1/calendar/monthly?month=YYYY-MM
 * Отображает: обзор месяца, новолуние/полнолуние, события, по неделям.
 *
 * Props: нет (месяц выбирается внутри)
 */

import React, { useState, useEffect } from 'react';

const MONTHS_RU = [
  'Январь','Февраль','Март','Апрель','Май','Июнь',
  'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь',
];

const EVENT_STYLES = {
  new_moon:  { emoji: '🌑', label: 'Новолуние',  bg: '#1a1a2e', color: '#a78bfa' },
  full_moon: { emoji: '🌕', label: 'Полнолуние', bg: '#1a1a2e', color: '#fbbf24' },
  ingress:   { emoji: '➡️', label: 'Вход в знак', bg: 'var(--color-background-secondary)', color: 'var(--color-text-primary)' },
  aspect:    { emoji: '⚡',  label: 'Аспект',     bg: 'var(--color-background-secondary)', color: 'var(--color-text-primary)' },
};

export default function AstroCalendar() {
  const now  = new Date();
  const [year,  setYear]  = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data,  setData]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    load();
  }, [year, month]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const monthStr = `${year}-${String(month).padStart(2,'0')}`;
      const res = await fetch(`/api/v1/calendar/monthly?month=${monthStr}`);
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

  const overview = data?.overview;
  const events   = data?.events || [];
  const newMoon  = events.find(e => e.type === 'new_moon');
  const fullMoon = events.find(e => e.type === 'full_moon');
  const ingresses = events.filter(e => e.type === 'ingress');
  const aspects   = events.filter(e => e.type === 'aspect');

  return (
    <div style={s.root}>
      {/* Навигация по месяцам */}
      <div style={s.nav}>
        <button onClick={prev} style={s.navBtn}>‹</button>
        <h2 style={s.navTitle}>{MONTHS_RU[month-1]} {year}</h2>
        <button onClick={next} style={s.navBtn}>›</button>
      </div>

      {loading && <p style={s.muted}>Загружаем календарь…</p>}
      {error   && <p style={s.danger}>Ошибка: {error}</p>}

      {!loading && data && (
        <div style={s.content}>

          {/* Обзор месяца от AI */}
          {overview && (
            <section style={s.card}>
              <h3 style={s.cardTitle}>{overview.month_title || `${MONTHS_RU[month-1]} ${year}`}</h3>
              {overview.month_tagline && (
                <p style={s.tagline}>{overview.month_tagline}</p>
              )}

              {/* Ключевые темы */}
              {overview.key_themes?.length > 0 && (
                <div style={s.themes}>
                  <p style={s.sectionLabel}>⚡️ Главные темы</p>
                  <ul style={s.themeList}>
                    {overview.key_themes.map((t, i) => (
                      <li key={i} style={s.themeItem}>• {t}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* По неделям */}
              {overview.week_by_week?.length > 0 && (
                <div style={{ marginTop: '16px' }}>
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

              {/* Аффирмация */}
              {overview.affirmation && (
                <div style={s.affirmation}>✨ {overview.affirmation}</div>
              )}
            </section>
          )}

          {/* Новолуние */}
          {(newMoon || overview?.new_moon) && (
            <MoonCard
              type="new_moon"
              event={newMoon}
              detail={overview?.new_moon}
            />
          )}

          {/* Полнолуние */}
          {(fullMoon || overview?.full_moon) && (
            <MoonCard
              type="full_moon"
              event={fullMoon}
              detail={overview?.full_moon}
            />
          )}

          {/* Смена знаков планетами */}
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

          {/* Аспекты между медленными планетами */}
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


// ── Карточка луны ─────────────────────────────────────────────────────────────

function MoonCard({ type, event, detail }) {
  const cfg  = EVENT_STYLES[type];
  const date = event?.date?.slice(5) || detail?.date || '';
  const sign = event?.sign || detail?.sign || '';
  const title = detail?.title || `${cfg.label} в ${sign}`;
  const desc  = detail?.description || '';
  const ritual = detail?.ritual;
  const practice = detail?.practice;

  return (
    <section style={{ ...s.card, ...s.moonCard }}>
      <div style={s.moonHeader}>
        <span style={{ fontSize: '24px' }}>{cfg.emoji}</span>
        <div>
          <p style={{ ...s.cardTitle, margin: 0 }}>{title}</p>
          {date && <p style={s.moonDate}>{date} UTC</p>}
        </div>
      </div>

      {desc && <p style={s.moonDesc}>{desc}</p>}

      {/* Темы новолуния */}
      {detail?.key_themes?.length > 0 && (
        <ul style={s.themeList}>
          {detail.key_themes.map((t, i) => <li key={i} style={s.themeItem}>• {t}</li>)}
        </ul>
      )}

      {/* Что делать / не делать */}
      {detail?.do && (
        <div style={{ marginTop: '12px' }}>
          <p style={s.sectionLabel}>✅ Что делать</p>
          {Object.entries(detail.do).map(([k, items]) =>
            (items || []).map((item, i) => <p key={`${k}${i}`} style={s.listItem}>{item}</p>)
          )}
        </div>
      )}
      {detail?.avoid?.length > 0 && (
        <div style={{ marginTop: '8px' }}>
          <p style={s.sectionLabel}>⚠️ Чего избегать</p>
          {detail.avoid.map((item, i) => <p key={i} style={s.listItem}>{item}</p>)}
        </div>
      )}

      {ritual && (
        <div style={s.ritualBox}>
          🌑 Ритуал новолуния: {ritual}
        </div>
      )}
      {practice && (
        <div style={s.ritualBox}>
          🌕 Практика на полнолуние: {practice}
        </div>
      )}
    </section>
  );
}


// ── Стили ─────────────────────────────────────────────────────────────────────

const s = {
  root: { display: 'flex', flexDirection: 'column', gap: '0' },
  nav: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: '20px',
  },
  navBtn: {
    background: 'none', border: '0.5px solid var(--color-border-secondary)',
    borderRadius: '8px', padding: '6px 14px', fontSize: '18px',
    color: 'var(--color-text-secondary)', cursor: 'pointer',
  },
  navTitle: { margin: 0, fontSize: '18px', fontWeight: '500', color: 'var(--color-text-primary)' },
  content: { display: 'flex', flexDirection: 'column', gap: '16px' },
  card: {
    background: 'var(--color-background-primary)', padding: '18px 20px',
    borderRadius: 'var(--border-radius-lg)', border: '0.5px solid var(--color-border-tertiary)',
  },
  moonCard: { borderLeft: '3px solid var(--color-border-info)' },
  cardTitle: { fontSize: '16px', fontWeight: '500', color: 'var(--color-text-primary)', margin: '0 0 6px' },
  tagline: { margin: '0 0 12px', fontSize: '14px', color: 'var(--color-text-secondary)', fontStyle: 'italic' },
  sectionLabel: {
    margin: '0 0 6px', fontSize: '11px', fontWeight: '500',
    letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-text-tertiary)',
  },
  themes: { marginTop: '12px' },
  themeList: { margin: 0, padding: 0, listStyle: 'none' },
  themeItem: { fontSize: '13px', lineHeight: '1.7', color: 'var(--color-text-primary)' },
  weekRow: {
    display: 'flex', alignItems: 'center', gap: '10px',
    padding: '6px 0', borderBottom: '0.5px solid var(--color-border-tertiary)',
  },
  weekNum:   { fontSize: '12px', fontWeight: '500', color: 'var(--color-text-secondary)', width: '56px', flexShrink: 0 },
  weekDates: { fontSize: '12px', color: 'var(--color-text-tertiary)', width: '48px', flexShrink: 0 },
  weekTone:  { fontSize: '13px', color: 'var(--color-text-primary)' },
  affirmation: {
    marginTop: '14px', padding: '10px 14px', borderRadius: 'var(--border-radius-md)',
    background: 'var(--color-background-info)', fontSize: '14px',
    fontStyle: 'italic', color: 'var(--color-text-info)', textAlign: 'center',
  },
  moonHeader: { display: 'flex', alignItems: 'flex-start', gap: '12px', marginBottom: '10px' },
  moonDate: { margin: '2px 0 0', fontSize: '12px', color: 'var(--color-text-tertiary)' },
  moonDesc: { margin: '0 0 10px', fontSize: '14px', lineHeight: '1.6', color: 'var(--color-text-primary)' },
  ritualBox: {
    marginTop: '10px', padding: '10px 14px', background: 'var(--color-background-secondary)',
    borderRadius: 'var(--border-radius-md)', fontSize: '13px', color: 'var(--color-text-primary)',
  },
  eventRow: {
    display: 'flex', alignItems: 'flex-start', gap: '10px',
    padding: '6px 0', borderBottom: '0.5px solid var(--color-border-tertiary)',
  },
  eventDate:    { fontSize: '12px', color: 'var(--color-text-tertiary)', width: '36px', flexShrink: 0 },
  eventDesc:    { fontSize: '13px', color: 'var(--color-text-primary)', flex: 1 },
  eventMeaning: { fontSize: '12px', color: 'var(--color-text-secondary)', flex: 1 },
  listItem: { margin: '2px 0', fontSize: '13px', lineHeight: '1.5', color: 'var(--color-text-primary)' },
  muted:  { color: 'var(--color-text-tertiary)', fontSize: '13px' },
  danger: { color: 'var(--color-text-danger)',   fontSize: '13px' },
};
