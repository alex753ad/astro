/* zodiac data-color, intentional — LandingPage is a fixed light-theme design; colors are pinned by design, not theme-dependent tokens */
import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import MotionButton from '../components/MotionButton';
import chartPreview from '../assets/chart-preview.png';

const VIEWPORT_ONCE = { once: true, margin: '-80px' };

export default function LandingPage({ onShowAuth, currentUser }) {
  const navigate = useNavigate();
  const prefersReduced = useReducedMotion();

  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  // ── Варианты анимаций (при prefers-reduced-motion — только fade, без сдвига) ──
  const heroContainer = { hidden: {}, visible: { transition: { staggerChildren: 0.08 } } };
  const heroItem = prefersReduced
    ? { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { duration: 0.4, ease: 'easeOut' } } }
    : { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } } };

  const sectionReveal = prefersReduced
    ? { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { duration: 0.5, ease: 'easeOut' } } }
    : { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' } } };

  const gridContainer = { hidden: {}, visible: { transition: { staggerChildren: 0.08 } } };

  const cardHover = prefersReduced ? undefined : { y: -3 };
  const previewShadow = '0 12px 40px rgba(0,0,0,0.10)';

  const handleActivate = () => {
    if (currentUser) {
      navigate('/profile');
    } else {
      navigate('/home');
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #f8f0ff 0%, #f0e8ff 20%, #fce8f4 45%, #e8f0ff 70%, #f0f8ff 100%)',
      fontFamily: '"Space Grotesk", system-ui, sans-serif',
      color: '#1a1230',
    }}>


      {/* Hero */}
      <motion.div
        variants={heroContainer}
        initial="hidden"
        animate="visible"
        style={{
          textAlign: 'center',
          padding: isMobile ? '40px 20px 32px' : '80px 40px 40px',
          maxWidth: 700,
          margin: '0 auto',
        }}
      >
        <motion.div variants={heroItem} style={{
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: '0.12em',
          color: '#8B5CF6',
          textTransform: 'uppercase',
          marginBottom: 20,
        }}>
          Астрология, которая ведёт
        </motion.div>

        <motion.h1 variants={heroItem} style={{
          fontSize: 'clamp(36px, 5vw, 58px)',
          fontWeight: 700,
          lineHeight: 1.15,
          margin: '0 0 20px',
          color: '#1a1230',
        }}>
          Лучшее время для возможностей —<br />
          <motion.span
            style={{
              background: 'linear-gradient(135deg, #8B5CF6, #EC4899)',
              // Растягиваем градиент вдвое, чтобы было куда его смещать.
              backgroundSize: prefersReduced ? '100% 100%' : '200% 100%',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
            animate={prefersReduced ? undefined : { backgroundPosition: ['0% 50%', '100% 50%', '0% 50%'] }}
            transition={prefersReduced ? undefined : { duration: 7, ease: 'easeInOut', repeat: Infinity }}
          >
            в твоём планере
          </motion.span>
        </motion.h1>

        <motion.p variants={heroItem} style={{
          fontSize: 16,
          color: '#6B6885',
          lineHeight: 1.7,
          maxWidth: 540,
          margin: '0 auto 36px',
        }}>
          Астрея мягко ведёт тебя по твоим жизненным циклам — показывает, какой
          период сейчас наступает, о чём он для тебя и как прожить его в своём
          ритме, опираясь на твою натальную карту.
        </motion.p>

        <motion.div variants={heroItem}>
          <MotionButton
            level="primary"
            onClick={handleActivate}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 10,
              padding: '16px 36px',
              borderRadius: 14,
              border: 'none',
              background: '#1a1230',
              color: '#fff',
              fontSize: 16,
              fontWeight: 700,
              cursor: 'pointer',
              fontFamily: 'inherit',
              letterSpacing: '0.01em',
              transition: 'transform 0.2s, box-shadow 0.2s',
              boxShadow: '0 4px 20px rgba(26,18,48,0.2)',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 8px 28px rgba(26,18,48,0.28)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 4px 20px rgba(26,18,48,0.2)';
            }}
          >
            Собрать мой Timeline
          </MotionButton>
        </motion.div>
      </motion.div>

      {/* Preview card */}
      <div style={{
        maxWidth: 820,
        margin: '48px auto 0',
        padding: '0 24px',
      }}>
        <motion.div
          initial={prefersReduced
            ? { opacity: 0, boxShadow: previewShadow }
            : { opacity: 0, scale: 0.96, boxShadow: '0 0px 0px rgba(0,0,0,0)' }}
          animate={{ opacity: 1, scale: 1, boxShadow: previewShadow }}
          transition={{ duration: 0.5, ease: 'easeOut', delay: 0.55 }}
          style={{
            background: 'rgba(255,255,255,0.7)',
            backdropFilter: 'blur(16px)',
            borderRadius: 20,
            border: '1px solid rgba(139,92,246,0.15)',
            overflow: 'hidden',
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr' : '1fr 1.4fr',
            minHeight: 220,
          }}
        >
          {/* Left — natal chart preview */}
          <div style={{
            display: 'flex',
            flexDirection: isMobile ? 'row' : 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: isMobile ? '20px 24px' : '32px 24px',
            borderRight: isMobile ? 'none' : '1px solid rgba(139,92,246,0.1)',
            borderBottom: isMobile ? '1px solid rgba(139,92,246,0.1)' : 'none',
            background: 'rgba(248,244,255,0.6)',
            gap: 16,
          }}>
            <img
              src={chartPreview}
              alt="Натальная карта в Астрея"
              loading="lazy"
              style={{
                width: '100%',
                maxWidth: 200,
                height: 'auto',
                objectFit: 'contain',
                borderRadius: 16,
                display: 'block',
              }}
            />
            <span style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.12em',
              color: '#9B97B0',
              textTransform: 'uppercase',
            }}>Swiss Ephemeris Core &amp; AI</span>
          </div>

          {/* Right — timeline */}
          <div style={{ padding: '28px 28px' }}>
            <div style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.12em',
              color: '#8B5CF6',
              textTransform: 'uppercase',
              marginBottom: 18,
            }}>
              Твой таймлайн на месяц
            </div>

            <PlanetItem
              color="#EAB308"
              planet="Солнце"
              period="Период 01.07 — 20.07"
              desc="Говори о карьере, статусе и росте, проси о повышении — сейчас твоё имя звучит громче, и тебя слышат яснее."
            />
            <PlanetItem
              color="#EC4899"
              planet="Венера"
              period="Период 01.07 — 28.07"
              desc="Обнови гардероб, выбери парфюм, украшения или аксессуары — в эти дни твоя харизма работает сильнее, и люди тянутся к тебе охотнее."
            />

            {/* AI Sintez badge */}
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              marginTop: 16,
              padding: '6px 14px',
              borderRadius: 20,
              background: '#1a1230',
              color: '#fff',
              fontSize: 12,
              fontWeight: 600,
            }}>
              <span style={{ fontSize: 10 }}>✦</span>
              AI Синтез
            </div>

            <div style={{
              marginTop: 16,
              fontSize: 13,
              fontStyle: 'italic',
              color: '#8B5CF6',
              lineHeight: 1.6,
            }}>
              И это лишь два окна твоего месяца — Астрея ведёт тебя по всем планетам и покажет,
              где действие сработает в 2–3 раза сильнее.
            </div>
          </div>
        </motion.div>
      </div>

      {/* Features */}
      <motion.h2
        variants={sectionReveal}
        initial="hidden"
        whileInView="visible"
        viewport={VIEWPORT_ONCE}
        style={{
          fontSize: 'clamp(26px, 3.5vw, 36px)',
          fontWeight: 700,
          lineHeight: 1.2,
          textAlign: 'center',
          margin: '48px 0 24px',
          color: '#1a1230',
        }}
      >
        Что делает Астрея
      </motion.h2>
      <motion.div
        variants={gridContainer}
        initial="hidden"
        whileInView="visible"
        viewport={VIEWPORT_ONCE}
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: 16,
          maxWidth: 820,
          margin: '0 auto',
          padding: '0 24px',
        }}
      >
        {[
          {
            title: 'Транзитный Timeline',
            desc: 'Линия времени, где отображается движение транзитных планет по твоей натальной карте. Начало каждого важного периода у тебя перед глазами.',
            descShort: 'Начало каждого важного периода — перед глазами.',
          },
          {
            title: 'Timeline Планер',
            desc: 'Поможет сориентироваться по каждому твоему периоду и применить компенсаторику транзитов, встроив нужные действия в своё ежедневное расписание. Планируй заранее отпуск, финансы и важные решения в самое правильное время.',
            descShort: 'Встрой нужные действия в своё расписание — заранее и вовремя.',
          },
          {
            title: 'AI-астролог Астрея',
            desc: 'В чате с Астреей можно задать любой вопрос о себе — и она ответит по твоей карте и текущим транзитам сразу. Соединив твою натальную основу с событиями момента, она даст подсказку именно для тебя, здесь и сейчас.',
            descShort: 'Спроси о себе — ответит по твоей карте и транзитам сейчас.',
          },
        ].map((f) => (
          <motion.div
            key={f.title}
            variants={sectionReveal}
            whileHover={cardHover}
            style={{
              flex: isMobile ? '1 1 100%' : '0 1 calc((100% - 32px) / 3)',
              background: 'rgba(255,255,255,0.6)',
              backdropFilter: 'blur(8px)',
              borderRadius: 16,
              border: '1px solid rgba(139,92,246,0.1)',
              padding: '24px 20px',
            }}
          >
            <div style={{
              fontWeight: 700,
              fontSize: 15,
              color: '#1a1230',
              marginBottom: 8,
            }}>{f.title}</div>
            <div style={{
              fontSize: 13,
              color: '#6B6885',
              lineHeight: 1.6,
            }}>{isMobile ? f.descShort : f.desc}</div>
          </motion.div>
        ))}
      </motion.div>

      {/* CTA под сеткой возможностей */}
      <motion.div
        variants={sectionReveal}
        initial="hidden"
        whileInView="visible"
        viewport={VIEWPORT_ONCE}
        style={{ textAlign: 'center', margin: '32px 0 48px', padding: '0 24px' }}
      >
        <MotionButton
          level="primary"
          onClick={handleActivate}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 10,
            padding: '16px 36px',
            borderRadius: 14,
            border: 'none',
            background: '#1a1230',
            color: '#fff',
            fontSize: 16,
            fontWeight: 700,
            cursor: 'pointer',
            fontFamily: 'inherit',
            letterSpacing: '0.01em',
            transition: 'transform 0.2s, box-shadow 0.2s',
            boxShadow: '0 4px 20px rgba(26,18,48,0.2)',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.transform = 'translateY(-2px)';
            e.currentTarget.style.boxShadow = '0 8px 28px rgba(26,18,48,0.28)';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = '0 4px 20px rgba(26,18,48,0.2)';
          }}
        >
          Собрать мой Timeline
        </MotionButton>
      </motion.div>

      {/* Ссылка на B2B-пространство */}
      <div style={{ textAlign: 'center', padding: '0 24px 8px' }}>
        <Link to="/orion" style={{ fontSize: 16, color: '#9B97B0', textDecoration: 'none' }}
          onMouseEnter={e => e.currentTarget.style.textDecoration = 'underline'}
          onMouseLeave={e => e.currentTarget.style.textDecoration = 'none'}
        >
          Ты астролог и ведёшь клиентов? → Астрея для практики
        </Link>
      </div>

      {/* Footer links */}
      <div style={{
        textAlign: 'center',
        padding: '0 24px 48px',
        fontSize: 13,
        color: '#9B97B0',
      }}>
        <Link to="/privacy" style={{ color: '#8B5CF6', textDecoration: 'none' }}
          onMouseEnter={e => e.currentTarget.style.textDecoration = 'underline'}
          onMouseLeave={e => e.currentTarget.style.textDecoration = 'none'}
        >Политика конфиденциальности</Link>
        <span style={{ margin: '0 10px' }}>·</span>
        <Link to="/terms" style={{ color: '#8B5CF6', textDecoration: 'none' }}
          onMouseEnter={e => e.currentTarget.style.textDecoration = 'underline'}
          onMouseLeave={e => e.currentTarget.style.textDecoration = 'none'}
        >Правила использования</Link>
      </div>
    </div>
  );
}

function PlanetItem({ color, planet, period, desc }) {
  return (
    <div style={{ display: 'flex', gap: 0, marginBottom: 16 }}>
      {/* Левая скобка */}
      <div style={{
        width: 3,
        borderRadius: 2,
        background: color,
        marginRight: 12,
        flexShrink: 0,
      }} />
      <div style={{ flex: 1 }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: 4,
          flexWrap: 'wrap',
          gap: 4,
        }}>
          <span style={{ fontWeight: 700, fontSize: 14, color }}>
            <span style={{
              display: 'inline-block',
              width: 8, height: 8,
              borderRadius: '50%',
              background: color,
              marginRight: 8,
              verticalAlign: 'middle',
            }} />
            {planet}
          </span>
          <span style={{
            fontSize: 11,
            fontWeight: 600,
            color,
            background: color === '#EAB308' ? 'rgba(234,179,8,0.1)' : 'rgba(236,72,153,0.1)',
            padding: '2px 8px',
            borderRadius: 10,
          }}>{period}</span>
        </div>
        <div style={{ fontSize: 13, color: '#6B6885', lineHeight: 1.5 }}>{desc}</div>
      </div>
    </div>
  );
}

function ZodiacWheelSVG() {
  const cx = 70, cy = 70, r = 55, rInner = 30;
  const signs = 12;
  const lines = Array.from({ length: signs }, (_, i) => {
    const angle = (i * 360) / signs - 90;
    const rad = (angle * Math.PI) / 180;
    return {
      x1: cx + rInner * Math.cos(rad),
      y1: cy + rInner * Math.sin(rad),
      x2: cx + r * Math.cos(rad),
      y2: cy + r * Math.sin(rad),
    };
  });

  // Cross lines (ASC/DSC/MC/IC)
  const crossAngles = [0, 90, 180, 270];

  return (
    <svg width="140" height="140" viewBox="0 0 140 140" fill="none">
      <style>{`
        @keyframes zodiacWheelRotate {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
      <g style={{ transformOrigin: `${cx}px ${cy}px`, animation: 'zodiacWheelRotate 40s linear infinite' }}>
        {/* Outer circle */}
        <circle cx={cx} cy={cy} r={r} stroke="rgba(139,92,246,0.25)" strokeWidth="1" fill="rgba(139,92,246,0.04)" />
        {/* Inner circle */}
        <circle cx={cx} cy={cy} r={rInner} stroke="rgba(139,92,246,0.15)" strokeWidth="1" fill="none" />
        {/* Segment lines */}
        {lines.map((l, i) => (
          <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke="rgba(139,92,246,0.2)" strokeWidth="1" />
        ))}
        {/* Cross lines */}
        {crossAngles.map((a, i) => {
          const rad = ((a - 90) * Math.PI) / 180;
          return (
            <line
              key={i}
              x1={cx + 8 * Math.cos(rad)} y1={cy + 8 * Math.sin(rad)}
              x2={cx + r * Math.cos(rad)} y2={cy + r * Math.sin(rad)}
              stroke="rgba(139,92,246,0.5)" strokeWidth="1.5"
            />
          );
        })}
        {/* Center dot */}
        <circle cx={cx} cy={cy} r={3} fill="rgba(139,92,246,0.5)" />
        {/* Planet dots */}
        {[
          { angle: 30, dist: 42, c: '#8B5CF6' },
          { angle: 110, dist: 38, c: '#EC4899' },
          { angle: 200, dist: 45, c: '#8B5CF6' },
          { angle: 300, dist: 40, c: '#A78BFA' },
        ].map((p, i) => {
          const rad = ((p.angle - 90) * Math.PI) / 180;
          return <circle key={i} cx={cx + p.dist * Math.cos(rad)} cy={cy + p.dist * Math.sin(rad)} r={3} fill={p.c} />;
        })}
      </g>
    </svg>
  );
}
