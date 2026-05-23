/**
 * ForecastScale.jsx
 *
 * Планировщик с прокруткой дней месяца.
 * Исправления:
 *   1. Прокрутка дней месяца (видно 10, скролл горизонтальный)
 *   2. Недельный прогноз — эндпоинт /forecast/weekly исправлен
 *   3. Зелёные кружочки вместо эмодзи в "Что делать"
 *   4. Вкладки День/Неделя/Месяц
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';

const SCALES = [
  { key: 'day',   label: 'День'   },
  { key: 'week',  label: 'Неделя' },
  { key: 'month', label: 'Месяц'  },
];

const DAYS_RU = ['вс','пн','вт','ср','чт','пт','сб'];
const MONTHS_SHORT = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];

// Получить monday недели для даты
function getMonday(dateStr) {
  const d   = new Date(dateStr + 'T00:00:00');
  const day = d.getDay() || 7;
  d.setDate(d.getDate() - day + 1);
  return d.toISOString().slice(0, 10);
}

// Все дни месяца для выбранной даты
function getMonthDays(dateStr) {
  const d     = new Date(dateStr + 'T00:00:00');
  const year  = d.getFullYear();
  const month = d.getMonth();
  const count = new Date(year, month + 1, 0).getDate();
  return Array.from({ length: count }, (_, i) => {
    const day = new Date(year, month, i + 1);
    return day.toISOString().slice(0, 10);
  });
}

export default function ForecastScale({ chartId, selectedDate: externalDate }) {
  const [scale, setScale]           = useState('day');
  const [selectedDate, setSelected] = useState(externalDate || new Date().toISOString().slice(0, 10));
  const [forecast, setForecast]     = useState(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);
  const stripRef                    = useRef(null);

  // Sync внешней даты
  useEffect(() => {
    if (externalDate) setSelected(externalDate);
  }, [externalDate]);

  // Скролл к выбранному дню
  useEffect(() => {
    if (!stripRef.current) return;
    const days   = getMonthDays(selectedDate);
    const idx    = days.indexOf(selectedDate);
    const btn    = stripRef.current.children[idx];
    btn?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [selectedDate]);

  const load = useCallback(async () => {
    if (!chartId || !selectedDate) return;
    setLoading(true);
    setError(null);
    setForecast(null);

    const token   = localStorage.getItem('astro_access_token');
    const headers = token ? { Authorization: `Bearer ${token}` } : {};

    try {
      let url;
      if (scale === 'day') {
        url = `https://astro-production-abcc.up.railway.app/api/v1/chart/${chartId}/forecast/daily?on_date=${selectedDate}`;
      } else if (scale === 'week') {
        const monday = getMonday(selectedDate);
        const d      = new Date(monday + 'T00:00:00');
        d.setDate(d.getDate() + 6);
        const sunday = d.toISOString().slice(0, 10);
        url = `https://astro-production-abcc.up.railway.app/api/v1/chart/${chartId}/forecast/weekly?week_start=${monday}&week_end=${sunday}`;
      } else {
        const d     = new Date(selectedDate + 'T00:00:00');
        const y     = d.getFullYear();
        const m     = String(d.getMonth() + 1).padStart(2, '0');
        const last  = new Date(y, d.getMonth() + 1, 0).getDate();
        url = `https://astro-production-abcc.up.railway.app/api/v1/chart/${chartId}/forecast/monthly?from_date=${y}-${m}-01&to_date=${y}-${m}-${last}`;
      }

      const res  = await fetch(url, { headers });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `${res.status}`);
      }
      const data = await res.json();
      setForecast(data.forecast || data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [chartId, selectedDate, scale]);

  useEffect(() => { load(); }, [load]);

  const days    = getMonthDays(selectedDate);
  const today   = new Date().toISOString().slice(0, 10);

  return (
    <div style={s.root}>

      {/* ── Прокрутка дней месяца ── */}
      <div style={s.stripWrap}>
        <div ref={stripRef} style={s.strip}>
          {days.map(d => {
            const dt      = new Date(d + 'T00:00:00');
            const isToday = d === today;
            const isSel   = d === selectedDate;
            return (
              <button
                key={d}
                onClick={() => setSelected(d)}
                style={{
                  ...s.dayBtn,
                  ...(isSel ? s.dayBtnSel : {}),
                  ...(isToday && !isSel ? s.dayBtnToday : {}),
                }}
              >
                <span style={{ fontSize: 10, opacity: 0.7, lineHeight: 1 }}>
                  {DAYS_RU[dt.getDay()]}
                </span>
                <span style={{ fontSize: 15, fontWeight: isSel ? 700 : 500, lineHeight: 1 }}>
                  {dt.getDate()}
                </span>
                {isToday && (
                  <span style={{
                    width: 4, height: 4, borderRadius: 2,
                    background: isSel ? '#fff' : 'var(--color-border-info, #3B82F6)',
                    marginTop: 1,
                  }} />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Вкладки масштаба ── */}
      <div style={s.tabs}>
        {SCALES.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setScale(key)}
            style={{ ...s.tab, ...(scale === key ? s.tabActive : {}) }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Контент ── */}
      <div style={s.body}>
        {loading && (
          <div style={s.loadingWrap}>
            {[80, 60, 90, 50].map((w, i) => (
              <div key={i} style={{
                height: 12, width: `${w}%`, borderRadius: 6, marginBottom: 8,
                background: 'var(--color-border-tertiary)',
                animation: `shimmer 1.6s ease-in-out ${i * 0.1}s infinite`,
              }} />
            ))}
            <style>{`@keyframes shimmer{0%{opacity:1}50%{opacity:0.4}100%{opacity:1}}`}</style>
          </div>
        )}
        {error && (
          <div style={s.errorBox}>
            <p style={{ margin: 0, fontSize: 13 }}>Ошибка: {error}</p>
            <button onClick={load} style={s.retryBtn}>Повторить</button>
          </div>
        )}
        {!loading && !error && forecast && (
          <ForecastContent scale={scale} data={forecast} />
        )}
        {!loading && !error && !forecast && !chartId && (
          <p style={s.muted}>Выберите дату выше</p>
        )}
      </div>
    </div>
  );
}


// ── Контент ───────────────────────────────────────────────────────────────────

function ForecastContent({ scale, data }) {
  if (scale === 'day')   return <DayForecast data={data} />;
  if (scale === 'week')  return <WeekForecast data={data} />;
  if (scale === 'month') return <MonthForecast data={data} />;
  return null;
}


// ── Дневной прогноз ───────────────────────────────────────────────────────────

function DayForecast({ data }) {
  return (
    <div style={s.section}>
      <div style={s.scoreRow}>
        <ScoreBadge score={data.potential_score} />
        <p style={s.summary}>{data.summary}</p>
      </div>
      {data.moon_tip && <TipBox text={`🌙 Луна в ${data.moon_house || '?'} доме: ${data.moon_tip}`} />}
      <SphereList spheres={data.spheres} />
      <DoAvoid doItems={data.do_today} avoidItems={data.avoid_today} />
      {data.morning_ritual && <TipBox text={`🌅 ${data.morning_ritual}`} />}
      {data.affirmation    && <Affirmation text={data.affirmation} />}
    </div>
  );
}


// ── Недельный прогноз ─────────────────────────────────────────────────────────

function WeekForecast({ data }) {
  return (
    <div style={s.section}>
      <div style={s.scoreRow}>
        <ScoreBadge score={data.potential_score} />
        <p style={s.summary}>{data.week_summary}</p>
      </div>
      <SphereList spheres={data.spheres} />
      {data.days?.length > 0 && (
        <div>
          <SectionLabel>По дням</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {data.days.map((d, i) => (
              <div key={i} style={s.dayRow}>
                <span style={s.dayLabel}>{d.day_ru}</span>
                <span style={s.dayDate}>{d.date?.slice(5)}</span>
                <span style={s.dayFocus}>{d.focus}</span>
                {d.moon_house && <span style={s.moonPill}>🌙{d.moon_house}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
      <DoAvoid doItems={data.do_this_week} avoidItems={data.avoid_this_week} />
      <BestCaution best={data.best_days} caution={data.caution_days} />
      {data.week_affirmation && <Affirmation text={data.week_affirmation} />}
    </div>
  );
}


// ── Месячный прогноз ──────────────────────────────────────────────────────────

function MonthForecast({ data }) {
  return (
    <div style={s.section}>
      <p style={s.summary}>{data.month_summary}</p>
      <SphereList spheres={data.spheres} extended />
      {data.week_by_week?.length > 0 && (
        <div>
          <SectionLabel>По неделям</SectionLabel>
          {data.week_by_week.map((w, i) => (
            <div key={i} style={s.weekRow}>
              <span style={s.weekNum}>Нед.{w.week}</span>
              <span style={s.weekDates}>{w.dates}</span>
              <span style={s.weekFocus}>{w.focus || w.tone}</span>
            </div>
          ))}
        </div>
      )}
      {/* do_this_month может быть объектом или массивом */}
      {data.do_this_month && (
        typeof data.do_this_month === 'object' && !Array.isArray(data.do_this_month)
          ? <DoAvoidObj doObj={data.do_this_month} avoidItems={data.avoid_this_month} />
          : <DoAvoid doItems={data.do_this_month} avoidItems={data.avoid_this_month} />
      )}
      <BestCaution best={data.best_dates} caution={data.caution_dates} />
      {data.month_affirmation && <Affirmation text={data.month_affirmation} />}
    </div>
  );
}


// ── Переиспользуемые блоки ────────────────────────────────────────────────────

function ScoreBadge({ score }) {
  if (score == null) return null;
  const color = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';
  return (
    <div style={{ ...s.badge, color, borderColor: color }}>{score}</div>
  );
}

function SphereList({ spheres, extended }) {
  if (!spheres?.length) return null;
  return (
    <div>
      <SectionLabel>Активные сферы</SectionLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {spheres.map((sp, i) => (
          <div key={i} style={{
            ...s.sphereCard,
            borderLeftColor: sp.is_main ? 'var(--color-border-info, #3B82F6)' : 'var(--color-border-tertiary)',
          }}>
            <div style={s.sphereHead}>
              <span style={{ fontSize: 17 }}>{sp.emoji}</span>
              <span style={s.sphereName}>{sp.sphere_name}</span>
              {sp.is_main && <span style={s.mainPill}>главная</span>}
            </div>
            <p style={s.sphereRec}>{sp.recommendation}</p>
            {extended && sp.planet_action && (
              <p style={s.sphereAction}>📌 {sp.planet_action}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// Зелёные кружочки вместо эмодзи
function GreenDot() {
  return (
    <span style={{
      display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
      background: '#22c55e', flexShrink: 0, marginTop: 3,
    }} />
  );
}

function RedDot() {
  return (
    <span style={{
      display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
      background: '#ef4444', flexShrink: 0, marginTop: 3,
    }} />
  );
}

function DoAvoid({ doItems, avoidItems }) {
  if (!doItems?.length && !avoidItems?.length) return null;
  // Strip leading emoji from items — заменяем на кружочек
  const stripEmoji = (str) => str.replace(/^[\p{Emoji}\s]+/u, '').trim();

  return (
    <div style={s.twoCol}>
      {doItems?.length > 0 && (
        <div>
          <SectionLabel color="#22c55e">Что делать</SectionLabel>
          {doItems.map((item, i) => (
            <div key={i} style={s.dotRow}>
              <GreenDot />
              <span style={s.dotText}>{stripEmoji(item)}</span>
            </div>
          ))}
        </div>
      )}
      {avoidItems?.length > 0 && (
        <div>
          <SectionLabel color="#ef4444">Чего избегать</SectionLabel>
          {avoidItems.map((item, i) => (
            <div key={i} style={s.dotRow}>
              <RedDot />
              <span style={s.dotText}>{stripEmoji(item)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DoAvoidObj({ doObj, avoidItems }) {
  const stripEmoji = (str) => str.replace(/^[\p{Emoji}\s]+/u, '').trim();
  const allDo = Object.values(doObj).flat();
  return <DoAvoid doItems={allDo} avoidItems={avoidItems} />;
}

function BestCaution({ best, caution }) {
  if (!best?.length && !caution?.length) return null;
  return (
    <div style={s.twoCol}>
      {best?.length > 0 && (
        <div>
          <SectionLabel color="#22c55e">Лучшие дни</SectionLabel>
          {best.map((d, i) => (
            <p key={i} style={s.listItem}>
              {typeof d === 'string' ? d : `${d.date?.slice(5)} — ${d.reason}`}
            </p>
          ))}
        </div>
      )}
      {caution?.length > 0 && (
        <div>
          <SectionLabel color="#f59e0b">Осторожно</SectionLabel>
          {caution.map((d, i) => (
            <p key={i} style={s.listItem}>
              {typeof d === 'string' ? d : `${d.date?.slice(5)} — ${d.reason}`}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function TipBox({ text }) {
  return (
    <div style={s.tip}><span style={s.tipText}>{text}</span></div>
  );
}

function Affirmation({ text }) {
  return (
    <div style={s.affirmation}>✨ {text}</div>
  );
}

function SectionLabel({ children, color }) {
  return (
    <p style={{ ...s.sectionLabel, ...(color ? { color } : {}) }}>{children}</p>
  );
}


// ── Стили ─────────────────────────────────────────────────────────────────────

const s = {
  root: { display: 'flex', flexDirection: 'column', gap: '12px' },

  // Прокрутка дней
  stripWrap: {
    overflow: 'hidden',
    borderRadius: 'var(--border-radius-md, 8px)',
    background: 'var(--color-background-secondary)',
    padding: '4px',
  },
  strip: {
    display: 'flex',
    gap: '4px',
    overflowX: 'auto',
    scrollbarWidth: 'none',
    msOverflowStyle: 'none',
    paddingBottom: '2px',
    // Видно ~10 кнопок по 46px + gap
  },
  dayBtn: {
    minWidth: 44, maxWidth: 44, flexShrink: 0,
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
    padding: '7px 4px', borderRadius: 8,
    border: '1px solid transparent',
    background: 'transparent',
    color: 'var(--color-text-secondary)',
    cursor: 'pointer', transition: 'all 0.15s',
    fontFamily: 'inherit',
  },
  dayBtnSel: {
    background: 'var(--color-background-info, rgba(59,130,246,0.15))',
    border: '1px solid var(--color-border-info, #3B82F6)',
    color: 'var(--color-text-info, #3B82F6)',
  },
  dayBtnToday: {
    border: '1px solid var(--color-border-secondary)',
    color: 'var(--color-text-primary)',
  },

  // Вкладки
  tabs: {
    display: 'flex', gap: '4px', padding: '3px',
    background: 'var(--color-background-secondary)',
    borderRadius: 'var(--border-radius-md, 8px)',
  },
  tab: {
    flex: 1, padding: '7px 10px', borderRadius: 6,
    border: 'none', background: 'transparent',
    color: 'var(--color-text-secondary)', fontSize: '13px', fontWeight: 400,
    cursor: 'pointer', transition: 'all 0.15s', fontFamily: 'inherit',
  },
  tabActive: {
    background: 'var(--color-background-primary)',
    color: 'var(--color-text-primary)', fontWeight: 500,
    boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
  },

  body:    { minHeight: 60 },
  section: { display: 'flex', flexDirection: 'column', gap: 14 },

  scoreRow: { display: 'flex', alignItems: 'flex-start', gap: 12 },
  badge: {
    flexShrink: 0, width: 46, height: 46, borderRadius: '50%',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    border: '2px solid', fontSize: 15, fontWeight: 600,
  },
  summary: { margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--color-text-primary)' },

  sectionLabel: {
    margin: '0 0 6px', fontSize: 11, fontWeight: 500,
    letterSpacing: '0.06em', textTransform: 'uppercase',
    color: 'var(--color-text-tertiary)',
  },

  sphereCard: {
    padding: '10px 12px', borderRadius: 8,
    background: 'var(--color-background-secondary)',
    borderLeft: '3px solid var(--color-border-tertiary)',
  },
  sphereHead: { display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 },
  sphereName: { fontSize: 13, fontWeight: 500, color: 'var(--color-text-primary)', flex: 1 },
  sphereRec:  { margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--color-text-primary)' },
  sphereAction: { margin: '5px 0 0', fontSize: 12, color: 'var(--color-text-secondary)' },
  mainPill: {
    fontSize: 10, padding: '1px 7px', borderRadius: 8, flexShrink: 0,
    background: 'var(--color-background-info)', color: 'var(--color-text-info)',
  },

  twoCol: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },

  dotRow:  { display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 },
  dotText: { fontSize: 13, lineHeight: 1.5, color: 'var(--color-text-primary)' },
  listItem: { margin: '2px 0', fontSize: 13, lineHeight: 1.5, color: 'var(--color-text-primary)' },

  dayRow: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0',
    borderBottom: '0.5px solid var(--color-border-tertiary)',
  },
  dayLabel: { width: 24, fontSize: 12, fontWeight: 500, color: 'var(--color-text-secondary)', flexShrink: 0 },
  dayDate:  { width: 34, fontSize: 12, color: 'var(--color-text-tertiary)', flexShrink: 0 },
  dayFocus: { flex: 1, fontSize: 12, color: 'var(--color-text-primary)' },
  moonPill: { fontSize: 11, padding: '1px 6px', borderRadius: 8, background: 'var(--color-background-secondary)', flexShrink: 0 },

  weekRow: {
    display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0',
    borderBottom: '0.5px solid var(--color-border-tertiary)',
  },
  weekNum:   { fontSize: 12, fontWeight: 500, color: 'var(--color-text-secondary)', width: 50, flexShrink: 0 },
  weekDates: { fontSize: 12, color: 'var(--color-text-tertiary)', width: 44, flexShrink: 0 },
  weekFocus: { flex: 1, fontSize: 13, color: 'var(--color-text-primary)' },

  tip:     { padding: '9px 12px', background: 'var(--color-background-secondary)', borderRadius: 8 },
  tipText: { fontSize: 13, lineHeight: 1.5, color: 'var(--color-text-primary)' },
  affirmation: {
    padding: '10px 14px', borderRadius: 8, textAlign: 'center',
    background: 'var(--color-background-info)',
    fontSize: 13, fontStyle: 'italic', color: 'var(--color-text-info)',
  },

  loadingWrap: { padding: '8px 0' },
  errorBox: {
    padding: '12px 14px', borderRadius: 8,
    background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
  },
  retryBtn: {
    marginTop: 8, padding: '5px 14px', borderRadius: 8, fontSize: 12,
    border: '1px solid rgba(239,68,68,0.4)', background: 'transparent',
    color: '#ef4444', cursor: 'pointer',
  },
  muted:  { color: 'var(--color-text-tertiary)', fontSize: 13, margin: 0 },
};
