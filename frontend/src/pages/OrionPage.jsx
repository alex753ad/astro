/* zodiac data-color, intentional — OrionPage mirrors LandingPage's fixed light-theme design */
import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import MotionButton from '../components/MotionButton';
import crmPreview from '../assets/crm-preview.png';
import { TIER_NAMES } from '../constants';

const VIEWPORT_ONCE = { once: true, margin: '-80px' };

const DISPLAY = "'Space Grotesk', system-ui, sans-serif";
const BODY = "'Inter', system-ui, sans-serif";

const PRACTICE_FEATURES = [
  'Кабинет астролога: все клиенты, их карты, заметки и история разговоров — в одном месте',
  'AI готовит разбор карты клиента заранее — вы приходите подготовленными',
  'Клиент сам заполняет анкету по ссылке — данные и карта сразу в вашем кабинете',
  'Ваши авторские трактовки: Астрея разбирает карты вашим голосом, а не общими словами',
  'Аналитика практики: доход, средний чек и темы консультаций — наглядно, помесячно',
  'PDF-отчёты с вашим брендингом — клиент уходит с документом',
  'Астрея сама замечает, у кого открывается важное окно, и подсказывает написать — и сама отправит',
  'Безлимит карт и клиентских профилей',
];

const PERSONAL_FEATURES = [
  'Чат с Астреей — персональный разбор в любой момент',
  'AI-разбор каждого транзита без лимита',
  'Глубокий разбор натальной карты — от 1500 слов',
  'Планер Timeline: все планеты, астро-рекомендации на неделю и месяц, долгосрочные периоды',
  'Горизонт транзитов на 24 месяца вперёд',
  'Лунный календарь и Google Календарь',
  'PDF-экспорт',
];

function CheckIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function FeatureGroup({ title, items }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{
        fontFamily: DISPLAY,
        fontWeight: 700,
        fontSize: 13,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        color: 'var(--text-primary)',
        marginBottom: 10,
      }}>
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {items.map((text, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <span style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 2 }}>
              <CheckIcon />
            </span>
            <span style={{ fontSize: 14, lineHeight: 1.5, color: 'var(--text-primary)' }}>{text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Модалка-оффер перед редиректом — стиль как LyraPaywallModal, без эмодзи/иконок.
function OrionOfferModal({ onClose, onActivate }) {
  const reduce = useReducedMotion();

  return (
    <motion.div
      onClick={onClose}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        background: 'rgba(15,10,26,0.7)',
        backdropFilter: 'blur(4px)',
      }}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="Тариф Орион"
        onClick={e => e.stopPropagation()}
        initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
        animate={reduce ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }}
        exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
        transition={{ type: 'spring', stiffness: 320, damping: 26 }}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: 460,
          maxHeight: '90vh',
          overflowY: 'auto',
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 20,
          padding: 32,
          boxShadow: '0 24px 60px rgba(0,0,0,0.40)',
          fontFamily: BODY,
          color: 'var(--text-primary)',
        }}
      >
        <button
          type="button"
          aria-label="Закрыть"
          onClick={onClose}
          style={{
            position: 'absolute',
            top: 16,
            right: 16,
            background: 'none',
            border: 'none',
            color: 'var(--text-secondary)',
            fontSize: 16,
            cursor: 'pointer',
            padding: 4,
            lineHeight: 1,
          }}
        >✕</button>

        <div style={{
          display: 'inline-block',
          background: 'var(--accent)',
          color: '#fff',
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.08em',
          padding: '3px 10px',
          borderRadius: 20,
          marginBottom: 12,
          textTransform: 'uppercase',
          fontFamily: DISPLAY,
        }}>
          {TIER_NAMES.premium}
        </div>

        <h2 style={{ margin: '0 0 12px', fontFamily: DISPLAY, fontSize: 22, fontWeight: 700, lineHeight: 1.3 }}>
          Вы делаете астрологию. Орион берёт на себя всё остальное.
        </h2>
        <p style={{ margin: '0 0 24px', fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          Astrea готовит разбор клиента заранее, помнит каждого и сама подсказывает,
          кому написать сегодня. Вы приходите на консультацию собранными — за 20 минут
          вместо двух часов, с PDF-отчётом под вашим именем.
        </p>

        <FeatureGroup title="Для практики" items={PRACTICE_FEATURES} />
        <FeatureGroup title="И всё для себя" items={PERSONAL_FEATURES} />

        <div style={{
          paddingTop: 16,
          borderTop: '1px solid var(--border)',
          marginBottom: 20,
        }}>
          <p style={{ margin: '0 0 4px', fontFamily: DISPLAY, fontSize: 20, fontWeight: 700 }}>
            7 990 ₽ в месяц
          </p>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>
            При 3 клиентах по 4 000 ₽ Орион окупается с первой встречи — дальше только ваш рост.
          </p>
        </div>

        <MotionButton
          level="primary"
          onClick={() => { onClose(); onActivate(); }}
          style={{
            width: '100%',
            padding: 14,
            border: 'none',
            borderRadius: 12,
            background: 'var(--accent)',
            color: '#fff',
            fontSize: 15,
            fontWeight: 700,
            cursor: 'pointer',
            fontFamily: DISPLAY,
            marginBottom: 12,
          }}
        >
          Открыть пространство Астреи
        </MotionButton>

        <button
          type="button"
          onClick={onClose}
          style={{
            display: 'block',
            width: '100%',
            background: 'none',
            border: 'none',
            color: 'var(--text-secondary)',
            fontSize: 13,
            cursor: 'pointer',
            fontFamily: 'inherit',
            textAlign: 'center',
          }}
        >
          Отмена в любой момент · Без обязательств
        </button>
      </motion.div>
    </motion.div>
  );
}

export default function OrionPage({ currentUser }) {
  const navigate = useNavigate();
  const prefersReduced = useReducedMotion();

  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  const [showOfferModal, setShowOfferModal] = useState(false);
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
            onClick={() => setShowOfferModal(true)}
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
          <p style={{ fontSize: 13, color: '#6B6885', marginTop: 12 }}>
            Каждый клиент, потерянный в заметках телефона, — несостоявшаяся консультация.
          </p>
        </motion.div>
      </div>

      <AnimatePresence>
        {showOfferModal && (
          <OrionOfferModal onClose={() => setShowOfferModal(false)} onActivate={handleActivate} />
        )}
      </AnimatePresence>
    </div>
  );
}
