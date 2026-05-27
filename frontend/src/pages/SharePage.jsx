/**
 * SharePage.jsx — публичная страница карты по токену (/chart/share/:token)
 * Загружает данные карты и показывает превью + кнопку "Открыть в Astrea"
 */

import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import NatalChart from '../components/NatalChart';

const API_BASE = 'https://astro-production-abcc.up.railway.app/api/v1';
const BACKEND  = 'https://astro-production-abcc.up.railway.app';

const SIGN_RU = {
  Aries: 'Овен', Taurus: 'Телец', Gemini: 'Близнецы', Cancer: 'Рак',
  Leo: 'Лев', Virgo: 'Дева', Libra: 'Весы', Scorpio: 'Скорпион',
  Sagittarius: 'Стрелец', Capricorn: 'Козерог', Aquarius: 'Водолей', Pisces: 'Рыбы',
};
const SIGN_EMOJI = {
  Aries: '♈', Taurus: '♉', Gemini: '♊', Cancer: '♋', Leo: '♌', Virgo: '♍',
  Libra: '♎', Scorpio: '♏', Sagittarius: '♐', Capricorn: '♑', Aquarius: '♒', Pisces: '♓',
};

function getPlanet(planets, name) {
  return planets?.find(p => p.name === name);
}

function SignBadge({ label, planet }) {
  if (!planet) return null;
  const emoji = SIGN_EMOJI[planet.sign] || '';
  const ru    = SIGN_RU[planet.sign] || planet.sign;
  return (
    <div style={s.badge}>
      <span style={s.badgeLabel}>{label}</span>
      <span style={s.badgeValue}>{emoji} {ru}</span>
    </div>
  );
}

export default function SharePage() {
  const { token }   = useParams();
  const navigate    = useNavigate();
  const [chart, setChart]   = useState(null);
  const [error, setError]   = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!token) return;
    // бэкенд возвращает HTML с OG-тегами на /share/{token},
    // данные карты получаем через отдельный API-эндпоинт
    fetch(`${API_BASE}/share/${token}/data`)
      .then(r => { if (!r.ok) throw new Error('Карта не найдена'); return r.json(); })
      .then(setChart)
      .catch(e => setError(e.message));
  }, [token]);

  function handleCopyLink() {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  }

  function handleDownloadCard() {
    const a = document.createElement('a');
    a.href = `${BACKEND}/share/${token}/card.png`;
    a.download = 'astrea-timeline-card.png';
    a.click();
  }

  if (error) return (
    <div style={s.page}>
      <div style={s.center}>
        <p style={{ color: '#C03030' }}>{error}</p>
        <button onClick={() => navigate('/')} style={s.btn}>На главную</button>
      </div>
    </div>
  );

  if (!chart) return (
    <div style={s.page}>
      <div style={s.center}>
        <div style={s.logo}>☽ ✦ ☾</div>
        <p style={{ color: '#9080B0' }}>Загружаем карту…</p>
      </div>
    </div>
  );

  const sun  = getPlanet(chart.planets, 'Sun');
  const moon = getPlanet(chart.planets, 'Moon');
  const asc  = chart.ascendant;

  return (
    <div style={s.page}>

      {/* Шапка */}
      <header style={s.header}>
        <div style={s.logo}>☽ ✦ ☾</div>
        <span style={s.brand}>Astrea Timeline</span>
      </header>

      <main style={s.main}>

        {/* Заголовок */}
        <div style={s.titleBlock}>
          <h1 style={s.title}>{chart.share_name || 'Натальная карта'}</h1>
          <p style={s.subtitle}>{chart.birth_date} · {chart.birth_place}</p>
        </div>

        {/* Бейджи планет */}
        <div style={s.badges}>
          <SignBadge label="☀ Солнце"    planet={sun} />
          <SignBadge label="☽ Луна"      planet={moon} />
          {asc?.sign && (
            <div style={s.badge}>
              <span style={s.badgeLabel}>↑ Асцендент</span>
              <span style={s.badgeValue}>
                {SIGN_EMOJI[asc.sign] || ''} {SIGN_RU[asc.sign] || asc.sign}
              </span>
            </div>
          )}
        </div>

        {/* SVG карта */}
        <div style={s.chartWrap}>
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

        {/* Кнопки */}
        <div style={s.actions}>
          <button onClick={() => navigate('/')} style={s.btnPrimary}>
            ✦ Рассчитать свою карту
          </button>
          <button onClick={handleCopyLink} style={s.btnSecondary}>
            {copied ? '✓ Скопировано' : '🔗 Копировать ссылку'}
          </button>
          <button onClick={handleDownloadCard} style={s.btnSecondary}>
            🖼 Скачать карточку
          </button>
        </div>

        <p style={s.promo}>
          Персональные натальные карты, транзиты и AI-интерпретации — <strong>astreatime.ru</strong>
        </p>
      </main>
    </div>
  );
}

const s = {
  page: {
    minHeight: '100vh',
    background: 'linear-gradient(160deg, #0e0c1a 0%, #1a1030 100%)',
    color: '#fff',
    fontFamily: "'Segoe UI', Arial, sans-serif",
  },
  center: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', minHeight: '100vh', gap: '16px',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: '12px',
    padding: '20px 32px',
    borderBottom: '1px solid rgba(112,80,200,0.2)',
  },
  logo:  { fontSize: '20px', color: '#c9a8ff' },
  brand: { fontSize: '16px', fontWeight: '700', color: '#c9a8ff', letterSpacing: '1px' },
  main: {
    maxWidth: '720px', margin: '0 auto',
    padding: '32px 20px 60px',
    display: 'flex', flexDirection: 'column', gap: '24px',
  },
  titleBlock: {},
  title:    { margin: '0 0 6px', fontSize: '28px', fontWeight: '700', color: '#f0e8ff' },
  subtitle: { margin: 0, fontSize: '14px', color: '#9080b0' },
  badges: { display: 'flex', gap: '12px', flexWrap: 'wrap' },
  badge: {
    background: 'rgba(112,80,200,0.15)',
    border: '1px solid rgba(112,80,200,0.3)',
    borderRadius: '10px',
    padding: '10px 16px',
    minWidth: '120px',
  },
  badgeLabel: { display: 'block', fontSize: '11px', color: '#9060C8', fontWeight: '700',
                textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '4px' },
  badgeValue: { fontSize: '16px', fontWeight: '600', color: '#e0d0ff' },
  chartWrap: {
    background: 'rgba(255,255,255,0.03)',
    borderRadius: '20px',
    border: '1px solid rgba(112,80,200,0.2)',
    padding: '16px',
    display: 'flex', justifyContent: 'center',
  },
  actions: { display: 'flex', gap: '10px', flexWrap: 'wrap' },
  btnPrimary: {
    background: 'linear-gradient(135deg, #9060C8, #C060A0)',
    color: '#fff', border: 'none', borderRadius: '12px',
    padding: '12px 24px', fontSize: '15px', fontWeight: '700',
    cursor: 'pointer', fontFamily: 'inherit',
  },
  btnSecondary: {
    background: 'rgba(112,80,200,0.15)',
    color: '#c9a8ff', border: '1px solid rgba(112,80,200,0.3)',
    borderRadius: '12px', padding: '12px 20px',
    fontSize: '14px', cursor: 'pointer', fontFamily: 'inherit',
  },
  btn: {
    background: '#9060C8', color: '#fff', border: 'none',
    borderRadius: '10px', padding: '10px 20px', cursor: 'pointer',
  },
  promo: { fontSize: '13px', color: '#6050a0', textAlign: 'center', marginTop: '8px' },
};
