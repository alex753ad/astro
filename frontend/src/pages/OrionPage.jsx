/* zodiac data-color, intentional — OrionPage mirrors LandingPage's fixed light-theme design */
import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import MotionButton from '../components/MotionButton';
import crmPreview from '../assets/crm-preview.png';
import { TIER_NAMES } from '../constants';

const VIEWPORT_ONCE = { once: true, margin: '-80px' };

export default function OrionPage({ currentUser }) {
  const navigate = useNavigate();
  const prefersReduced = useReducedMotion();

  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  const sectionReveal = prefersReduced
    ? { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { duration: 0.5, ease: 'easeOut' } } }
    : { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' } } };

  const gridContainer = { hidden: {}, visible: { transition: { staggerChildren: 0.08 } } };
  const cardHover = prefersReduced ? undefined : { y: -3 };

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
      <div style={{ maxWidth: 820, margin: '0 auto', padding: '32px 24px 0' }}>
        <Link to="/" style={{ color: '#8B5CF6', textDecoration: 'none', fontSize: 14, fontWeight: 600 }}
          onMouseEnter={e => e.currentTarget.style.textDecoration = 'underline'}
          onMouseLeave={e => e.currentTarget.style.textDecoration = 'none'}
        >← На главную</Link>
      </div>

      <div style={{ textAlign: 'center', padding: '24px 24px 0', maxWidth: 700, margin: '0 auto' }}>
        <div style={{
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: '0.12em',
          color: '#8B5CF6',
          textTransform: 'uppercase',
        }}>
          Астрея для практики
        </div>
      </div>

      {/* Astrologer block */}
      <div style={{
        maxWidth: 820,
        margin: '24px auto 48px',
        padding: '0 24px',
      }}>
        <motion.div
          variants={sectionReveal}
          initial="hidden"
          whileInView="visible"
          viewport={VIEWPORT_ONCE}
          style={{
            textAlign: 'center',
            maxWidth: 620,
            margin: '0 auto 28px',
          }}
        >
          <h2 style={{
            fontSize: 'clamp(26px, 3.5vw, 36px)',
            fontWeight: 700,
            lineHeight: 1.2,
            margin: '0 0 14px',
            color: '#1a1230',
          }}>
            Астрея станет вашим рабочим местом
          </h2>
          <p style={{ fontSize: 15, color: '#6B6885', lineHeight: 1.7, margin: 0 }}>
            Ваша практика переезжает из заметок телефона в одно живое пространство —
            и каждый повод написать превращается в новую консультацию.
          </p>
        </motion.div>

        {/* Cabinet screenshot */}
        <motion.div
          variants={sectionReveal}
          initial="hidden"
          whileInView="visible"
          viewport={VIEWPORT_ONCE}
          style={{
            borderRadius: 20,
            border: '1px solid rgba(139,92,246,0.15)',
            boxShadow: '0 12px 40px rgba(0,0,0,0.10)',
            overflow: 'hidden',
            marginBottom: 20,
          }}
        >
          <img
            src={crmPreview}
            alt="Кабинет астролога в Астрея"
            loading="lazy"
            style={{
              width: '100%',
              height: 'auto',
              objectFit: 'contain',
              display: 'block',
            }}
          />
        </motion.div>

        <motion.div
          variants={gridContainer}
          initial="hidden"
          whileInView="visible"
          viewport={VIEWPORT_ONCE}
          style={{
            // Тот же приём, что и в первой сетке: ряд 3 + центрированный ряд 2.
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            gap: 16,
            marginBottom: 28,
          }}
        >
          {[
            {
              title: 'Вся база в одном месте',
              desc: 'Карты, заметки и история каждого клиента живут рядом и всегда под рукой. Ваша практика становится единым, спокойным пространством, где легко ориентироваться.',
            },
            {
              title: 'Астрея сама подсказывает момент',
              desc: 'Она следит за периодами всех ваших клиентов и подсказывает, у кого прямо сейчас открывается важное окно. Каждый такой сигнал — тёплый повод написать и провести консультацию вовремя.',
              highlight: true,
            },
            {
              title: 'Готовы к встрече за 20 минут',
              desc: 'Астрея собирает бриф по клиенту заранее: карта, актуальные транзиты, главные темы периода. Вы приходите на консультацию собранным и глубоким, а время до неё остаётся вашим.',
            },
            {
              title: 'История, которая работает на вас',
              desc: 'Все сессии, брифы и заметки по клиенту хранятся вместе и складываются в живую летопись отношений. Вы возвращаетесь к прошлым разговорам легко и ведёте каждого клиента как своего.',
            },
            {
              title: 'Практика в цифрах',
              desc: `Ваши консультации и доход видны наглядно — вы видите, как растёт практика, и чувствуете отдачу от каждого шага. Одна консультация окупает месяц ${TIER_NAMES.premium}, дальше — только ваш рост.`,
            },
          ].map((f) => (
            <motion.div
              key={f.title}
              variants={sectionReveal}
              whileHover={cardHover}
              style={{
                flex: isMobile ? '1 1 100%' : '0 1 calc((100% - 32px) / 3)',
                background: f.highlight ? 'rgba(139,92,246,0.08)' : 'rgba(255,255,255,0.6)',
                backdropFilter: 'blur(8px)',
                borderRadius: 16,
                border: `1px solid ${f.highlight ? 'rgba(139,92,246,0.2)' : 'rgba(139,92,246,0.1)'}`,
                padding: '24px 20px',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: 15, color: '#1a1230', marginBottom: 8 }}>{f.title}</div>
              <div style={{ fontSize: 13, color: '#6B6885', lineHeight: 1.6 }}>{f.desc}</div>
            </motion.div>
          ))}
        </motion.div>

        <motion.div
          variants={sectionReveal}
          initial="hidden"
          whileInView="visible"
          viewport={VIEWPORT_ONCE}
          style={{ textAlign: 'center' }}
        >
          <MotionButton
            level="secondary"
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
            Открыть пространство Астреи
          </MotionButton>
        </motion.div>
      </div>
    </div>
  );
}
