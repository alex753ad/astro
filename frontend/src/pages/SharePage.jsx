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

function getPlanet(planets, name) {
  return planets?.find(p => p.name === name);
}

function SignBadge({ label, planet }) {
  if (!planet) return null;
  const ru    = SIGN_RU[planet.sign] || planet.sign;
  return (
    <div style={s.badge}>
      <span style={s.badgeLabel}>{label}</span>
      <span style={s.badgeValue}>{ru}</span>
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
        <p style={{ color: 'var(--color-danger)' }}>{error}</p>
        <button onClick={() => navigate('/')} style={s.btn}>На главную</button>
      </div>
    </div>
  );

  if (!chart) return (
    <div style={s.page}>
      <div style={s.center}>
        <div style={s.logo}>☽ ✦ ☾</div>
        <p style={{ color: 'var(--text-secondary)' }}>Загружаем карту…</p>
      </div>
    </div>
  );

  const sun  = getPlanet(chart.planets, 'Sun');
  const moon = getPlanet(chart.planets, 'Moon');
  const asc  = chart.ascendant;

  return (
    <div style={s.page}>

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
                {SIGN_RU[asc.sign] || asc.sign}
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

        {/* Приглашение построить свою карту */}
        <div style={{ textAlign: 'center', margin: '4px 0 14px' }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
            А что сейчас в вашей карте?
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Постройте свою за минуту и узнайте, какой период у вас идёт прямо сейчас — бесплатно.
          </div>
        </div>

        {/* Кнопки */}
        <div style={s.actions}>
          <button onClick={() => navigate('/')} style={s.btnPrimary}>
            ✦ Построить мою карту
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
    background: 'linear-gradient(160deg, var(--bg-deeper) 0%, var(--bg-card) 100%)',
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
  logo:  { fontSize: '20px', color: 'var(--accent-glow)' },
  brand: { fontSize: '16px', fontWeight: '700', color: 'var(--accent-glow)', letterSpacing: '1px' },
  main: {
    maxWidth: '720px', margin: '0 auto',
    padding: '32px 20px 60px',
    display: 'flex', flexDirection: 'column', gap: '24px',
  },
  titleBlock: {},
  title:    { margin: '0 0 6px', fontSize: '28px', fontWeight: '700', color: 'var(--text-primary)' },
  subtitle: { margin: 0, fontSize: '14px', color: 'var(--text-secondary)' },
  badges: { display: 'flex', gap: '12px', flexWrap: 'wrap' },
  badge: {
    background: 'rgba(112,80,200,0.12)',
    border: '1px solid rgba(112,80,200,0.25)',
    borderRadius: '10px',
    padding: '10px 16px',
    minWidth: '120px',
  },
  badgeLabel: { display: 'block', fontSize: '11px', color: 'var(--accent)', fontWeight: '700',
                textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: '4px' },
  badgeValue: { fontSize: '16px', fontWeight: '600', color: 'var(--text-primary)' },
  chartWrap: {
    background: 'rgba(255,255,255,0.03)',
    borderRadius: '20px',
    border: '1px solid rgba(112,80,200,0.2)',
    padding: '16px',
    display: 'flex', justifyContent: 'center',
  },
  actions: { display: 'flex', gap: '10px', flexWrap: 'wrap' },
  btnPrimary: {
    background: 'linear-gradient(135deg, var(--accent), var(--accent))',
    color: '#fff', border: 'none', borderRadius: '12px',
    padding: '12px 24px', fontSize: '15px', fontWeight: '700',
    cursor: 'pointer', fontFamily: 'inherit',
  },
  btnSecondary: {
    background: 'rgba(112,80,200,0.15)',
    color: 'var(--accent-glow)', border: '1px solid rgba(112,80,200,0.3)',
    borderRadius: '12px', padding: '12px 20px',
    fontSize: '14px', cursor: 'pointer', fontFamily: 'inherit',
  },
  btn: {
    background: 'var(--accent)', color: '#fff', border: 'none',
    borderRadius: '10px', padding: '10px 20px', cursor: 'pointer',
  },
  promo: { fontSize: '13px', color: 'var(--accent)', textAlign: 'center', marginTop: '8px' },
};
