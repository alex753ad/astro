/**
 * LunarCalendarPage.jsx
 * Редизайн: «Минималистичный Квадратный Календарь»
 * Путь: src/pages/LunarCalendarPage.jsx
 */

import React, { useState, useEffect, useMemo } from 'react';
import useAuth from '../hooks/useAuth';

import ariesIcon       from '../assets/zodiac/aries.png';
import taurusIcon      from '../assets/zodiac/taurus.png';
import geminiIcon      from '../assets/zodiac/gemini.png';
import cancerIcon      from '../assets/zodiac/cancer.png';
import leoIcon         from '../assets/zodiac/leo.png';
import virgoIcon       from '../assets/zodiac/virgo.png';
import libraIcon       from '../assets/zodiac/libra.png';
import scorpioIcon     from '../assets/zodiac/scorpio.png';
import sagittariusIcon from '../assets/zodiac/sagittarius.png';
import capricornIcon   from '../assets/zodiac/capricorn.png';
import aquariusIcon    from '../assets/zodiac/aquarius.png';
import piscesIcon      from '../assets/zodiac/pisces.png';

// ── Знаки зодиака ──────────────────────────────────────────

const SIGNS_RU = {
  Aries:       { name: 'Овен',      glyph: '♈', icon: ariesIcon,       color: '#E06050', bg: '#FFF0EE' },
  Taurus:      { name: 'Телец',     glyph: '♉', icon: taurusIcon,      color: '#70A030', bg: '#F2FAE8' },
  Gemini:      { name: 'Близнецы',  glyph: '♊', icon: geminiIcon,      color: '#D09010', bg: '#FFF8E0' },
  Cancer:      { name: 'Рак',       glyph: '♋', icon: cancerIcon,      color: '#5090C0', bg: '#E8F5FF' },
  Leo:         { name: 'Лев',       glyph: '♌', icon: leoIcon,         color: '#D07020', bg: '#FFF2E0' },
  Virgo:       { name: 'Дева',      glyph: '♍', icon: virgoIcon,       color: '#609050', bg: '#EDFAE8' },
  Libra:       { name: 'Весы',      glyph: '♎', icon: libraIcon,       color: '#A060C0', bg: '#F8EEFF' },
  Scorpio:     { name: 'Скорпион',  glyph: '♏', icon: scorpioIcon,     color: '#903050', bg: '#FFE8F0' },
  Sagittarius: { name: 'Стрелец',   glyph: '♐', icon: sagittariusIcon, color: '#C05020', bg: '#FFF0E4' },
  Capricorn:   { name: 'Козерог',   glyph: '♑', icon: capricornIcon,   color: '#506080', bg: '#EEF2F8' },
  Aquarius:    { name: 'Водолей',   glyph: '♒', icon: aquariusIcon,    color: '#3080B0', bg: '#E8F4FF' },
  Pisces:      { name: 'Рыбы',      glyph: '♓', icon: piscesIcon,      color: '#7050B0', bg: '#F0EAFF' },
};

const SIGN_KEYS = [
  'Aries','Taurus','Gemini','Cancer','Leo','Virgo',
  'Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces',
];

const SIGN_RU_TO_KEY = {
  'Овен':'Aries','Телец':'Taurus','Близнецы':'Gemini','Рак':'Cancer',
  'Лев':'Leo','Дева':'Virgo','Весы':'Libra','Скорпион':'Scorpio',
  'Стрелец':'Sagittarius','Козерог':'Capricorn','Водолей':'Aquarius','Рыбы':'Pisces',
};

const MONTHS_RU = [
  'Январь','Февраль','Март','Апрель','Май','Июнь',
  'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь',
];

const DOW_RU = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];

// Приближённый знак Луны (меняется каждые ~2.46 дня)
// Якорь: 1 мая 2026 → Стрелец (индекс 8)
const ANCHOR_MS   = new Date('2026-05-01').getTime();
const ANCHOR_IDX  = 8;

function approxMoonSign(dateStr) {
  const ms   = new Date(dateStr + 'T12:00:00').getTime();
  const days = (ms - ANCHOR_MS) / 86400000;
  const idx  = ((ANCHOR_IDX + Math.floor(days / 2.46)) % 12 + 12) % 12;
  return SIGN_KEYS[idx];
}

function buildCalendarDays(year, month) {
  const firstDay = new Date(year, month - 1, 1);
  const total    = new Date(year, month, 0).getDate();
  let startDow   = firstDay.getDay();
  startDow = startDow === 0 ? 6 : startDow - 1; // Monday-first

  const days = Array(startDow).fill(null);
  for (let d = 1; d <= total; d++) {
    const mm = String(month).padStart(2,'0');
    const dd = String(d).padStart(2,'0');
    days.push(`${year}-${mm}-${dd}`);
  }
  return days;
}

function sameDay(a, b) {
  return a && b && a.slice(0,10) === b.slice(0,10);
}

function fmtPhaseTime(event) {
  if (!event) return '';
  // /calendar/lunar возвращает date + time раздельно ("2026-06-15" + "05:54 GMT+3")
  if (event.time) {
    const src = event.exact_date || event.date;
    if (!src) return '';
    const [, mo, dd] = src.split('-');
    const tm = event.time.replace(/\s*GMT\+3/, '').replace(/\s*UTC/, '');
    return `${dd}.${mo} - ${tm} ОМТ+3`;
  }
  const src = event.exact_date || event.date;
  if (!src) return '';
  const d  = new Date(src);
  const dd = String(d.getDate()).padStart(2,'0');
  const mo = String(d.getMonth()+1).padStart(2,'0');
  const hh = String(d.getHours()).padStart(2,'0');
  const mi = String(d.getMinutes()).padStart(2,'0');
  return `${dd}.${mo} - ${hh}:${mi} ОМТ+3`;
}

// ══════════════════════════════════════════════════════════
// MAIN
// ══════════════════════════════════════════════════════════

export default function LunarCalendarPage() {
  const { user } = useAuth();
  const isFree = !user?.tier || user?.tier === 'free';
  const now      = new Date();
  const todayStr = now.toISOString().slice(0,10);
  const isPremium = user?.tier === 'premium';
  const lunarMonths = isPremium ? null
                    : user?.tier === 'pro' ? 12
                    : user?.tier === 'lite' ? 12
                    : isFree ? 1 : 1;
  const minDate = lunarMonths ? new Date(now.getFullYear(), now.getMonth() - (lunarMonths - 1), 1) : null;
  const maxDate = lunarMonths ? new Date(now.getFullYear(), now.getMonth() + (lunarMonths - 1), 1) : null;

  const [year,    setYear]    = useState(now.getFullYear());
  const [month,   setMonth]   = useState(now.getMonth() + 1);
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);
  const [dailyMap,    setDailyMap]    = useState({});
  const [lunarPhases, setLunarPhases] = useState([]);

  useEffect(() => { load(); }, [year, month]);

  async function load() {
    setLoading(true); setError(null);
    try {
      const ms  = `${year}-${String(month).padStart(2,'0')}`;
      const res = await fetch(
        `https://astro-production-abcc.up.railway.app/api/v1/calendar/monthly?month=${ms}`
      );
      if (!res.ok) throw new Error(res.status);
      setData(await res.json());

      // Пробуем ежедневные знаки
      try {
        const r2 = await fetch(
          `https://astro-production-abcc.up.railway.app/api/v1/calendar/lunar?year=${year}&month=${month}`
        );
        if (r2.ok) {
          const j2  = await r2.json();
          const map = {};
          (j2.daily_signs || []).forEach(d => { if (d.date && d.sign) map[d.date] = SIGN_RU_TO_KEY[d.sign] || d.sign; });
          setDailyMap(map);
          setLunarPhases(j2.phases || []);
        } else { setDailyMap({}); setLunarPhases([]); }
      } catch { setDailyMap({}); }

    } catch(e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function prev() {
    if (minDate && new Date(year, month - 2, 1) < minDate) return;
    if (month === 1) { setYear(y => y-1); setMonth(12); }
    else setMonth(m => m-1);
  }
  function next() {
    if (maxDate && new Date(year, month, 1) > maxDate) return;
    if (month === 12) { setYear(y => y+1); setMonth(1); }
    else setMonth(m => m+1);
  }

  const events   = data?.events    || [];
  const overview = data?.overview;
  const phaseSrc = lunarPhases.length ? lunarPhases : events;
  const newMoons = phaseSrc.filter(e => e.type === 'new_moon');
  const fullMoons= phaseSrc.filter(e => e.type === 'full_moon');

  const todaySign     = dailyMap[todayStr] || approxMoonSign(todayStr);
  const todaySignData = SIGNS_RU[todaySign] || SIGNS_RU.Leo;

  const calDays = useMemo(() => buildCalendarDays(year, month), [year, month]);

  // Schema.org — Event разметка для лунных фаз
  const schemaOrg = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: `Лунный календарь ${MONTHS_RU[month-1]} ${year}`,
    description: 'Фазы луны, знаки зодиака и астрологические события месяца',
    itemListElement: [
      ...newMoons.map((e, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        item: {
          '@type': 'Event',
          name: `Новолуние в ${SIGNS_RU[e.sign]?.name || e.sign || 'знаке'}`,
          startDate: (e.exact_date || e.date || '').slice(0, 10),
          description: 'Новолуние — начало нового лунного цикла',
          location: { '@type': 'VirtualLocation', url: 'https://astreatime.ru/calendar/lunar' },
        },
      })),
      ...fullMoons.map((e, i) => ({
        '@type': 'ListItem',
        position: newMoons.length + i + 1,
        item: {
          '@type': 'Event',
          name: `Полнолуние в ${SIGNS_RU[e.sign]?.name || e.sign || 'знаке'}`,
          startDate: (e.exact_date || e.date || '').slice(0, 10),
          description: 'Полнолуние — кульминация лунного цикла',
          location: { '@type': 'VirtualLocation', url: 'https://astreatime.ru/calendar/lunar' },
        },
      })),
    ],
  };

  return (
    <div className="lc-scope" style={pg.page}>
      {/* Декоративные блобы */}
      <div className="lc-blob" style={pg.blob1} aria-hidden="true" />
      <div className="lc-blob" style={pg.blob2} aria-hidden="true" />

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schemaOrg) }}
      />

      <div style={pg.wrap}>
        <div style={pg.card}>

          {/* ── Заголовок ─────────────────────────────── */}
          <div style={pg.cardHead}>
            <span style={{ fontSize: 18 }}>🌙</span>
            <span style={pg.cardTitle}>Лунный календарь</span>
          </div>

          {/* ── Шапка фаз ─────────────────────────────── */}
          {loading
            ? <SkeletonRow />
            : <PhaseHeader
                todaySign={todaySign}
                todaySignData={todaySignData}
                newMoons={newMoons}
                fullMoons={fullMoons}
                overview={overview}
              />
          }

          <div style={pg.hr} />

          {/* ── Навигация ─────────────────────────────── */}
          <div style={pg.nav}>
            {!isFree && <button onClick={prev} style={pg.navBtn} disabled={minDate && new Date(year, month-2, 1) < minDate}>‹</button>}
            <span style={pg.navMonth}>{MONTHS_RU[month-1]} {year}</span>
            {!isFree && <button onClick={next} style={pg.navBtn} disabled={maxDate && new Date(year, month, 1) > maxDate}>›</button>}
          </div>

          {/* ── Сетка календаря ───────────────────────── */}
          <div style={pg.grid}>
            {DOW_RU.map(d => (
              <div key={d} style={pg.dow}>{d}</div>
            ))}

            {calDays.map((dateStr, i) => {
              if (!dateStr) return <div key={`e${i}`} />;

              const dayNum     = parseInt(dateStr.slice(8), 10);
              const isToday    = dateStr === todayStr;
              const isNewMoon  = newMoons.some(e => sameDay(e.date, dateStr));
              const isFullMoon = fullMoons.some(e => sameDay(e.date, dateStr));
              const signKey    = dailyMap[dateStr] || approxMoonSign(dateStr);
              const signData   = SIGNS_RU[signKey] || SIGNS_RU.Leo;

              return (
                <DayCell
                  key={dateStr}
                  dayNum={dayNum}
                  isToday={isToday}
                  isNewMoon={isNewMoon}
                  isFullMoon={isFullMoon}
                  signData={signData}
                />
              );
            })}
          </div>

          {/* ── Легенда ───────────────────────────────── */}
          <div style={pg.legend}>
            <LegendDot fill="#C3CFFC" border="#8898D8" label="Сегодня" />
            <LegendDot fill="#2A2A3A" border="none"    label="Новолуние" />
            <LegendDot fill="#F5C842" border="#C0980A" label="Полнолуние" />
          </div>

        </div>

        {error && (
          <p style={{ color:'#C03030', fontSize:12, textAlign:'center', marginTop:8 }}>
            Ошибка: {error}
          </p>
        )}
      </div>

      <style>{`
        @keyframes shimmer {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        .lc-scope {
          --lc-bg: #FDFBF9; --lc-card: #FFFFFF; --lc-border: #F0EAF8;
          --lc-title: #1E1A2E; --lc-text2: #9080B0; --lc-text3: #B0A0C8; --lc-daynum: #2D2540;
        }
        .dark .lc-scope {
          --lc-bg: transparent; --lc-card: rgba(26,18,48,0.60); --lc-border: rgba(139,92,246,0.16);
          --lc-title: #E2DFF0; --lc-text2: #9B97B0; --lc-text3: #8983A0; --lc-daynum: #E2DFF0;
        }
        .dark .lc-scope .lc-blob { display: none; }
      `}</style>
    </div>
  );
}

// ── Шапка фаз ─────────────────────────────────────────────

function PhaseHeader({ todaySign, todaySignData, newMoons, fullMoons, overview }) {
  const nm  = newMoons[0];
  const fm1 = fullMoons[0];
  const fm2 = fullMoons[1];

  const nmSign  = SIGN_RU_TO_KEY[nm?.sign  || overview?.new_moon?.sign  || ''] || nm?.sign  || '';
  const fm1Sign = SIGN_RU_TO_KEY[fm1?.sign || overview?.full_moon?.sign || ''] || fm1?.sign || '';
  const fm2Sign = SIGN_RU_TO_KEY[fm2?.sign || ''] || fm2?.sign || '';

  return (
    <div>
      {/* Ряд 1 */}
      <div style={ph.row}>
        <PhaseBlock
          label="ЛУНА СЕЙЧАС"
          signData={todaySignData}
          extra={overview?.moon_degree ? `${overview.moon_degree}°` : ''}
        />
        {nm && (
          <PhaseBlock
            label="НОВОЛУНИЕ"
            signData={SIGNS_RU[nmSign] || SIGNS_RU.Taurus}
            extra={fmtPhaseTime(nm)}
            dark
          />
        )}
        {fm1 && (
          <PhaseBlock
            label="ПОЛНОЛУНИЕ"
            signData={SIGNS_RU[fm1Sign] || SIGNS_RU.Scorpio}
            extra={fmtPhaseTime(fm1)}
            gold
          />
        )}
      </div>

      {/* Ряд 2 — если есть второе полнолуние */}
      {fm2 && (
        <div style={{ ...ph.row, marginTop: 8 }}>
          <PhaseBlock
            label="ПОЛНОЛУНИЕ"
            signData={SIGNS_RU[fm2Sign] || SIGNS_RU.Sagittarius}
            extra={fmtPhaseTime(fm2)}
            gold
          />
        </div>
      )}
    </div>
  );
}

function PhaseBlock({ label, signData, extra, dark, gold }) {
  const iconBg    = dark ? '#1E1E2E' : gold ? '#FFF0A0' : signData.bg;
  const iconColor = dark ? '#FFFFFF' : gold ? '#8A6200' : signData.color;

  return (
    <div style={ph.block}>
      <span style={ph.label}>{label}</span>
      <div style={ph.inner}>
        <div style={{ ...ph.icon, background: 'transparent' }}>
          <img src={signData.icon} alt={signData.name}
               style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
        </div>
        <div>
          <div style={ph.name}>{signData.name}</div>
          {extra && <div style={ph.extra}>{extra}</div>}
        </div>
      </div>
    </div>
  );
}

function SkeletonRow() {
  return (
    <div style={{ display: 'flex', gap: 10, margin: '8px 0' }}>
      {[1,2,3].map(i => (
        <div key={i} style={{
          flex: 1, height: 52, borderRadius: 12,
          background: 'linear-gradient(90deg,#F0EAF8 25%,#FAF5FF 50%,#F0EAF8 75%)',
          backgroundSize: '200% 100%',
          animation: 'shimmer 1.6s ease-in-out infinite',
        }} />
      ))}
    </div>
  );
}

// ── Ячейка дня ────────────────────────────────────────────

function DayCell({ dayNum, isToday, isNewMoon, isFullMoon, signData }) {
  const numBg    = isToday    ? '#C3CFFC'
                 : isNewMoon  ? '#2A2A3A'
                 : isFullMoon ? '#F5C842'
                 : 'transparent';
  const numColor = isToday    ? '#1A2D90'
                 : isNewMoon  ? '#FFFFFF'
                 : isFullMoon ? '#7A5400'
                 : 'var(--lc-daynum)';
  const iconBg   = isNewMoon  ? '#3A3A50'
                 : isFullMoon ? '#FFF3C0'
                 : signData.bg;
  const iconColor= isNewMoon  ? '#FFFFFF'
                 : isFullMoon ? '#8A6200'
                 : signData.color;

  return (
    <div style={dc.root}>
      <div style={{ ...dc.num, background: numBg, color: numColor,
                    fontWeight: (isToday||isNewMoon||isFullMoon) ? 600 : 400 }}>
        {dayNum}
      </div>
      <div style={{ ...dc.icon, background: 'transparent' }}>
        <img src={signData.icon} alt={signData.name}
             style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
      </div>
      <div style={dc.name}>{signData.name}</div>
    </div>
  );
}

// ── Легенда ───────────────────────────────────────────────

function LegendDot({ fill, border, label }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:5 }}>
      <div style={{
        width: 11, height: 11, borderRadius: '50%',
        background: fill,
        border: border !== 'none' ? `1.5px solid ${border}` : 'none',
        flexShrink: 0,
      }} />
      <span style={{ fontSize: 11, color: 'var(--lc-text2)' }}>{label}</span>
    </div>
  );
}

// ══════════════════════════════════════════════════════════
// СТИЛИ
// ══════════════════════════════════════════════════════════

const pg = {
  page: {
    position: 'relative', minHeight: '100vh', background: 'var(--lc-bg)',
    overflow: 'hidden', display: 'flex', justifyContent: 'center',
    padding: '28px 16px 48px',
    fontFamily: "'Space Grotesk','Inter',system-ui,sans-serif",
  },
  blob1: {
    position:'absolute', top:-60, right:-160,
    width:500, height:500, borderRadius:'50%',
    background:'radial-gradient(circle,#FFF0C3 0%,#FCE0EE 45%,#E0C3FC 80%,transparent 100%)',
    filter:'blur(80px)', opacity:0.65, pointerEvents:'none', zIndex:0,
  },
  blob2: {
    position:'absolute', bottom:-80, left:-100,
    width:360, height:360, borderRadius:'50%',
    background:'radial-gradient(circle,#C3E0FC 0%,#E0C3FC 70%,transparent 100%)',
    filter:'blur(80px)', opacity:0.50, pointerEvents:'none', zIndex:0,
  },
  wrap: { position:'relative', zIndex:1, width:'100%', maxWidth:500 },
  card: {
    background:'var(--lc-card)', borderRadius:24,
    padding:'20px 18px 16px',
    boxShadow:'0 12px 40px -8px rgba(224,195,252,0.28),0 2px 8px rgba(0,0,0,0.04)',
    border:'1px solid var(--lc-border)',
  },
  cardHead:  { display:'flex', alignItems:'center', gap:7, marginBottom:12 },
  cardTitle: { fontSize:16, fontWeight:700, color:'var(--lc-title)' },
  hr:        { height:1, background:'var(--lc-border)', margin:'10px 0 0' },
  nav: {
    display:'flex', alignItems:'center', justifyContent:'center',
    gap:12, margin:'10px 0 12px',
  },
  navBtn:   { background:'none', border:'none', fontSize:22, color:'var(--lc-text3)', cursor:'pointer', padding:'0 4px', lineHeight:1 },
  navMonth: { fontSize:14, fontWeight:600, color:'var(--lc-title)', minWidth:110, textAlign:'center' },
  grid: {
    display:'grid', gridTemplateColumns:'repeat(7,1fr)',
    gap:'1px 0',
  },
  dow: {
    textAlign:'center', fontSize:10, fontWeight:600,
    color:'var(--lc-text3)', paddingBottom:6,
    letterSpacing:'0.02em',
  },
  legend: {
    display:'flex', alignItems:'center', justifyContent:'center',
    gap:14, marginTop:12,
  },
};

const ph = {
  row:   { display:'flex', gap:6, flexWrap:'wrap' },
  block: { flex:'1 1 120px', display:'flex', flexDirection:'column', gap:3 },
  label: { fontSize:8, fontWeight:700, color:'var(--lc-text3)', letterSpacing:'0.08em', textTransform:'uppercase' },
  inner: { display:'flex', alignItems:'center', gap:6 },
  icon:  { width:32, height:32, borderRadius:10, display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 },
  name:  { fontSize:13, fontWeight:700, color:'var(--lc-title)', lineHeight:1.2 },
  extra: { fontSize:9, color:'var(--lc-text2)', marginTop:1 },
};

const dc = {
  root: {
    display:'flex', flexDirection:'column', alignItems:'center',
    gap:2, padding:'4px 1px 5px',
  },
  num: {
    width:20, height:20, borderRadius:10,
    display:'flex', alignItems:'center', justifyContent:'center',
    fontSize:11, lineHeight:1,
  },
  icon: {
    width:26, height:26, borderRadius:8,
    display:'flex', alignItems:'center', justifyContent:'center',
  },
  name: {
    fontSize:7.5, color:'var(--lc-text2)',
    textAlign:'center', lineHeight:1.2,
    maxWidth:38, wordBreak:'break-word',
  },
};
