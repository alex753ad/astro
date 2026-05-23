/**
 * LunarCalendarPage.jsx
 * Route: /lunar
 * Route with chart context: /lunar?chartId=<id>
 *
 * Блоки:
 * 1. Текущее положение Луны в знаке + градус
 * 2. Ближайшие Новолуние и Полнолуние месяца
 * 3. Календарная сетка: знак Луны на каждый день + метки фаз
 */

import { useState, useEffect, useCallback } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { getLunarCalendar } from '../api/client';

// ── Константы ──────────────────────────────────────────────

const SIGN_SYMBOLS = {
  'Овен':     '♈', 'Телец':    '♉', 'Близнецы': '♊',
  'Рак':      '♋', 'Лев':      '♌', 'Дева':     '♍',
  'Весы':     '♎', 'Скорпион': '♏', 'Стрелец':  '♐',
  'Козерог':  '♑', 'Водолей':  '♒', 'Рыбы':     '♓',
};

const MONTH_NAMES_RU = [
  '', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

// ── Helpers ────────────────────────────────────────────────

function isoToday() {
  return new Date().toISOString().slice(0, 10);
}

// Возвращает 0=Пн … 6=Вс для первого дня месяца
function firstDayOfWeek(year, month) {
  const d = new Date(Date.UTC(year, month - 1, 1));
  return (d.getUTCDay() + 6) % 7;
}

// ── CurrentMoonCard ────────────────────────────────────────

function CurrentMoonCard({ moon }) {
  if (!moon) return <div style={s.skeleton} />;
  const sym = SIGN_SYMBOLS[moon.sign] ?? '🌙';
  return (
    <div style={s.infoCard}>
      <div style={s.infoLabel}>Луна сейчас</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 32, lineHeight: 1 }}>{sym}</span>
        <div>
          <div style={s.infoValue}>{moon.sign}</div>
          <div style={s.infoSub}>{moon.degree}°</div>
        </div>
      </div>
    </div>
  );
}

// ── PhaseCard ──────────────────────────────────────────────

function PhaseCard({ phase }) {
  if (!phase) return null;
  const isNew  = phase.type === 'new_moon';
  const emoji  = isNew ? '🌑' : '🌕';
  const label  = isNew ? 'Новолуние' : 'Полнолуние';
  const day    = phase.date?.slice(8, 10);
  const mo     = phase.date?.slice(5, 7);
  const time   = phase.time?.slice(0, 5);
  return (
    <div style={{ ...s.infoCard, flex: '1 1 180px' }}>
      <div style={s.infoLabel}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 32, lineHeight: 1 }}>{emoji}</span>
        <div>
          <div style={s.infoValue}>{phase.sign}</div>
          <div style={s.infoSub}>{day}.{mo} · {time} GMT+3</div>
        </div>
      </div>
    </div>
  );
}

// ── CalendarGrid ───────────────────────────────────────────

function CalendarGrid({ year, month, dailySigns, phases, today }) {
  const phaseLookup = {};
  (phases ?? []).forEach(p => { phaseLookup[p.date] = p; });

  const daysInMonth = dailySigns.length;
  const offset      = firstDayOfWeek(year, month);

  const cells = [];
  for (let i = 0; i < offset; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div style={s.calCard}>
      <div style={s.calGrid}>
        {WEEKDAYS.map(wd => (
          <div key={wd} style={s.calWeekday}>{wd}</div>
        ))}

        {cells.map((day, idx) => {
          if (!day) return <div key={`pad-${idx}`} />;

          const dateStr  = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const signData = dailySigns[day - 1];
          const sign     = signData?.sign ?? '';
          const sym      = SIGN_SYMBOLS[sign] ?? '';
          const phase    = phaseLookup[dateStr];
          const isToday  = dateStr === today;
          const isNew    = phase?.type === 'new_moon';
          const isFull   = phase?.type === 'full_moon';

          return (
            <div
              key={day}
              style={{
                ...s.calCell,
                ...(isToday ? s.calCellToday : {}),
                ...(isNew   ? s.calCellNew   : {}),
                ...(isFull  ? s.calCellFull  : {}),
              }}
            >
              <div style={{
                ...s.calDayNum,
                ...(isToday ? { color: 'var(--color-text-primary)', fontWeight: 600 } : {}),
              }}>
                {day}
              </div>

              <div style={s.calSym}>{sym}</div>
              <div style={s.calSignName}>{sign}</div>

              {phase && (
                <div style={s.calPhaseIcon} title={phase.description}>
                  {isNew ? '🌑' : '🌕'}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────

export default function LunarCalendarPage() {
  const [searchParams]   = useSearchParams();
  const navigate         = useNavigate();
  const chartId          = searchParams.get('chartId') ?? null;

  const now = new Date();
  const [year,    setYear]    = useState(now.getFullYear());
  const [month,   setMonth]   = useState(now.getMonth() + 1);
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');

  const today = isoToday();

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await getLunarCalendar(year, month);
      setData(res);
    } catch (err) {
      setError(err.message || 'Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  }, [year, month]);

  useEffect(() => { load(); }, [load]);

  const prevMonth = () => {
    if (month === 1) { setYear(y => y - 1); setMonth(12); }
    else setMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (month === 12) { setYear(y => y + 1); setMonth(1); }
    else setMonth(m => m + 1);
  };

  const phases    = data?.phases ?? [];
  const newMoons  = phases.filter(p => p.type === 'new_moon');
  const fullMoons = phases.filter(p => p.type === 'full_moon');

  return (
    <div style={s.page}>

      {/* Header */}
      <div style={s.header}>
        {chartId ? (
          <Link to={`/chart/${chartId}`} style={s.backLink}>← Назад к карте</Link>
        ) : (
          <Link to="/" style={s.backLink}>← Главная</Link>
        )}
        <h1 style={s.title}>🌙 Лунный календарь</h1>
      </div>

      {/* Info row: current moon + phases */}
      <div style={s.infoRow}>
        <CurrentMoonCard moon={data?.current_moon} />
        {newMoons.map((p, i)  => <PhaseCard key={`nm-${i}`} phase={p} />)}
        {fullMoons.map((p, i) => <PhaseCard key={`fm-${i}`} phase={p} />)}
      </div>

      {/* Month navigator */}
      <div style={s.navRow}>
        <button onClick={prevMonth} style={s.navBtn} aria-label="Предыдущий месяц">←</button>
        <span style={s.navTitle}>{MONTH_NAMES_RU[month]} {year}</span>
        <button onClick={nextMonth} style={s.navBtn} aria-label="Следующий месяц">→</button>
      </div>

      {/* Error */}
      {error && (
        <div style={s.errorBox}>
          {error}
          <button onClick={load} style={s.retryBtn}>Повторить</button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={s.loadingBox}>Загрузка данных…</div>
      )}

      {/* Calendar grid */}
      {!loading && data && (
        <CalendarGrid
          year={year}
          month={month}
          dailySigns={data.daily_signs}
          phases={phases}
          today={today}
        />
      )}

      {/* Legend */}
      {!loading && (
        <div style={s.legend}>
          <span style={s.legendItem}>
            <span style={s.legendDotToday} /> Сегодня
          </span>
          <span style={s.legendItem}>🌑 Новолуние</span>
          <span style={s.legendItem}>🌕 Полнолуние</span>
        </div>
      )}
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────

const s = {
  page: {
    maxWidth: 760,
    margin: '0 auto',
    padding: '24px 16px 64px',
  },

  header: {
    marginBottom: 20,
  },
  backLink: {
    fontSize: 13,
    color: 'var(--color-text-secondary)',
    textDecoration: 'none',
    display: 'inline-block',
    marginBottom: 8,
  },
  title: {
    margin: 0,
    fontSize: 22,
    fontWeight: 600,
    color: 'var(--color-text-primary)',
  },

  // Info cards
  infoRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 12,
    marginBottom: 20,
  },
  infoCard: {
    flex: '1 1 160px',
    background: 'var(--color-background-primary)',
    border: '0.5px solid var(--color-border-tertiary)',
    borderRadius: 'var(--border-radius-lg, 12px)',
    padding: '14px 16px',
  },
  skeleton: {
    flex: '1 1 160px',
    height: 80,
    borderRadius: 'var(--border-radius-lg, 12px)',
    background: 'var(--color-background-primary)',
    border: '0.5px solid var(--color-border-tertiary)',
  },
  infoLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    color: 'var(--color-text-tertiary)',
    marginBottom: 8,
  },
  infoValue: {
    fontSize: 15,
    fontWeight: 600,
    color: 'var(--color-text-primary)',
  },
  infoSub: {
    fontSize: 12,
    color: 'var(--color-text-secondary)',
    marginTop: 2,
  },

  // Nav
  navRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 20,
    marginBottom: 14,
  },
  navBtn: {
    width: 36,
    height: 36,
    borderRadius: 8,
    border: '0.5px solid var(--color-border-tertiary)',
    background: 'var(--color-background-primary)',
    color: 'var(--color-text-primary)',
    fontSize: 16,
    cursor: 'pointer',
    fontFamily: 'inherit',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  navTitle: {
    fontSize: 17,
    fontWeight: 600,
    color: 'var(--color-text-primary)',
    minWidth: 170,
    textAlign: 'center',
  },

  // Calendar
  calCard: {
    background: 'var(--color-background-primary)',
    border: '0.5px solid var(--color-border-tertiary)',
    borderRadius: 'var(--border-radius-lg, 12px)',
    padding: '16px',
    marginBottom: 14,
  },
  calGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(7, 1fr)',
    gap: 3,
  },
  calWeekday: {
    textAlign: 'center',
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--color-text-tertiary)',
    padding: '4px 0 10px',
  },
  calCell: {
    position: 'relative',
    borderRadius: 8,
    padding: '5px 3px 6px',
    minHeight: 68,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    border: '0.5px solid transparent',
  },
  calCellToday: {
    background: 'rgba(124,108,255,0.12)',
    border: '0.5px solid rgba(124,108,255,0.4)',
  },
  calCellNew: {
    background: 'rgba(15,17,40,0.7)',
  },
  calCellFull: {
    background: 'rgba(255,210,80,0.06)',
  },
  calDayNum: {
    fontSize: 11,
    color: 'var(--color-text-tertiary)',
    alignSelf: 'flex-start',
    marginLeft: 3,
    lineHeight: 1,
  },
  calSym: {
    fontSize: 20,
    lineHeight: 1,
    marginTop: 4,
  },
  calSignName: {
    fontSize: 9,
    color: 'var(--color-text-tertiary)',
    textAlign: 'center',
    marginTop: 2,
    lineHeight: 1.2,
  },
  calPhaseIcon: {
    position: 'absolute',
    top: 3,
    right: 4,
    fontSize: 11,
    lineHeight: 1,
    cursor: 'default',
  },

  // Misc
  loadingBox: {
    textAlign: 'center',
    color: 'var(--color-text-secondary)',
    padding: '40px 0',
    fontSize: 14,
  },
  errorBox: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '12px 16px',
    borderRadius: 10,
    background: 'rgba(239,68,68,0.08)',
    border: '1px solid rgba(239,68,68,0.2)',
    color: '#FCA5A5',
    fontSize: 13,
    marginBottom: 14,
  },
  retryBtn: {
    marginLeft: 'auto',
    background: 'none',
    border: '1px solid rgba(239,68,68,0.4)',
    borderRadius: 6,
    color: '#FCA5A5',
    fontSize: 12,
    padding: '3px 10px',
    cursor: 'pointer',
    fontFamily: 'inherit',
  },

  legend: {
    display: 'flex',
    gap: 20,
    fontSize: 12,
    color: 'var(--color-text-secondary)',
    justifyContent: 'center',
    flexWrap: 'wrap',
  },
  legendItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  legendDotToday: {
    display: 'inline-block',
    width: 12,
    height: 12,
    borderRadius: 3,
    background: 'rgba(124,108,255,0.25)',
    border: '1px solid rgba(124,108,255,0.5)',
    verticalAlign: 'middle',
  },
};
