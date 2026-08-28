/**
 * PaywallModal.jsx — контекстный модал апгрейда
 *
 * Props:
 *   context: 'free_to_lite' | 'lite_to_pro' | 'pro_to_premium'
 *   onClose: () => void
 *   chartId?: string (optional, for checkout redirect)
 */

import React, { useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { createCheckoutSession, validatePromoCode, apiErrorText } from '../api/client';
import MotionButton from './MotionButton';
import { TIER_NAMES } from '../constants';

const overlayVariants = {
  hidden:  { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.2, ease: 'easeOut' } },
  exit:    { opacity: 0, transition: { duration: 0.15, ease: 'easeOut' } },
};

const PAYWALL_CONTENT = {
  free_to_lite: {
    badge: TIER_NAMES.lite,
    title: 'Какой планетарный период сейчас влияет на вашу жизнь',
    subtitle: 'И что это значит для вас — по вашей карте, а не в общем',
    benefits: [
      { text: 'Полный разбор натальной карты — все планеты, дома и их влияние' },
      { text: 'Все активные транзиты месяца — что происходит с тобой сейчас' },
      { text: 'Лунный календарь месяца — лучшие дни для решений' },
      { text: 'Планер Timeline на 3 месяца вперёд' },
      { text: 'Карты партнёра, детей, родителей — до 5 сохранённых карт одновременно' },
      { text: 'Виральная карточка вашей карты для Stories' },
    ],
    cta: `Перейти на тариф ${TIER_NAMES.lite} — 790 ₽/мес`,
    price: 'Доступ на 1 месяц · Без автопродления',
    tier: 'lite',
    monthly: '790 ₽ / мес',
  },
  lite_to_pro: {
    badge: TIER_NAMES.pro,
    title: 'Вы видите транзит — Астрея говорит, что в нём делать',
    subtitle: 'Компенсации под вашу карту и астролог Астрея, которая помнит, о чём вы говорили',
    benefits: [
      { text: 'Чат с астрологом Астреей: знает вашу карту и помнит суть прошлых разговоров — как консультант, который вас уже знает' },
      { text: 'Разбор каждого транзита: что Сатурн в вашем 7-м доме значит и как его мягче прожить' },
      { text: 'Глубокий разбор натальной карты — от 1500 слов' },
      { text: 'Планер Timeline: все планеты, индивидуальные астро-рекомендации на неделю и месяц, долгосрочно, Google Календарь' },
      { text: 'До 15 сохранённых карт одновременно — для семьи' },
    ],
    cta: `Перейти на тариф ${TIER_NAMES.pro} — 2 490 ₽/мес`,
    price: 'Доступ на 1 месяц · Без автопродления',
    tier: 'pro',
    monthly: '2 490 ₽ / мес',
  },
  pro_to_premium: {
    badge: TIER_NAMES.premium,
    title: 'Подготовка к консультации — 20 минут вместо 2 часов',
    subtitle: 'При 3 клиентах по 4 000 ₽ подписка окупается с первой консультации',
    benefits: [
      { text: 'Синастрия: AI-разбор совместимости клиента с партнёром, ребёнком, коллегой' },
      { text: 'AI готовит разбор карты клиента — вы приходите подготовленными' },
      { text: 'CRM: все клиенты, карты, заметки и история в одном месте' },
      { text: 'PDF-отчёты с вашим брендингом — клиент уходит с документом' },
      { text: 'Безлимитные AI-интерпретации' },
      { text: 'Безлимитные карты и клиентские профили' },
    ],
    cta: `Перейти на тариф ${TIER_NAMES.premium} — 7 990 ₽/мес`,
    price: 'При 3 клиентах по 4 000 ₽ — окупается с первой консультации',
    tier: 'premium',
    monthly: '7 990 ₽ / мес',
  },
};

/**
 * Determine paywall context from API error response.
 * Backend returns: { error: "tier_required", required: "pro", current: "lite" }
 */
export function getPaywallContext(errorDetail) {
  if (!errorDetail || errorDetail.error !== 'tier_required') return null;
  const { required } = errorDetail;
  // Контент модалки всегда описывает конкретный требуемый тариф — показываем
  // именно его, а не «следующую ступень» от текущего тарифа пользователя.
  // Иначе free-пользователь, которому нужен pro, увидит и купит lite и всё
  // равно не получит доступ к фиче.
  if (required === 'lite') return 'free_to_lite';
  if (required === 'pro') return 'lite_to_pro';
  if (required === 'premium') return 'pro_to_premium';
  return 'free_to_lite'; // fallback
}

export default function PaywallModal({ context = 'free_to_lite', onClose, chartId }) {
  const content = PAYWALL_CONTENT[context] || PAYWALL_CONTENT.free_to_lite;
  const prefersReduced = useReducedMotion();
  const dialogVariants = prefersReduced
    ? {
        hidden:  { opacity: 0 },
        visible: { opacity: 1, transition: { duration: 0.2, ease: 'easeOut' } },
        exit:    { opacity: 0, transition: { duration: 0.15, ease: 'easeOut' } },
      }
    : {
        hidden:  { opacity: 0, scale: 0.96 },
        visible: { opacity: 1, scale: 1, transition: { duration: 0.2, ease: 'easeOut' } },
        exit:    { opacity: 0, scale: 0.96, transition: { duration: 0.15, ease: 'easeOut' } },
      };
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState(null);
  const [promoInput, setPromoInput]   = useState('');
  const [promoApplied, setPromoApplied] = useState('');   // применённый код
  const [promoError, setPromoError]   = useState('');
  const [promoLoading, setPromoLoading] = useState(false);

  async function handleApplyPromo() {
    const code = promoInput.trim().toUpperCase();
    if (!code) return;
    setPromoLoading(true);
    setPromoError('');
    try {
      await validatePromoCode(code);
      setPromoApplied(code);
      setPromoError('');
    } catch {
      setPromoError('Промокод не найден или истёк');
      setPromoApplied('');
    } finally {
      setPromoLoading(false);
    }
  }

  async function handleUpgrade() {
    setLoading(true);
    setError(null);
    try {
      // Поле называется checkout_url — так его отдаёт POST /payments/checkout
      // (backend/payments/yookassa_router.py). Раньше здесь читалось { url } —
      // форма ответа Stripe Checkout Session, удалённого 19.08.2026: значение
      // было undefined, браузер уходил на /undefined и показывал пустую
      // страницу, а исключения не возникало и catch не срабатывал.
      const { checkout_url: checkoutUrl } = await createCheckoutSession(content.tier, 'monthly', chartId, promoApplied || null);
      if (!checkoutUrl) {
        setError('Платёжный сервис не вернул ссылку на оплату. Попробуйте позже.');
        setLoading(false);
        return;
      }
      window.location.href = checkoutUrl;
    } catch (e) {
      if (e.detail?.error === 'invalid_promo_code') {
        setPromoError('Промокод не действителен');
        setPromoApplied('');
      } else {
        setError(apiErrorText(e, 'Не удалось открыть страницу оплаты. Попробуйте позже.'));
      }
      setLoading(false);
    }
  }

  return (
    <motion.div
      variants={overlayVariants} initial="hidden" animate="visible" exit="exit"
      style={s.overlay} onClick={onClose}>
      <motion.div
        variants={dialogVariants} initial="hidden" animate="visible" exit="exit"
        style={s.modal} onClick={e => e.stopPropagation()}>

        <button style={s.close} onClick={onClose}>✕</button>

        {/* Header */}
        <div style={s.header}>
          <div style={s.badge}>{content.badge}</div>
          <h2 style={s.title}>{content.title}</h2>
          <p style={s.subtitle}>{content.subtitle}</p>
        </div>

        {/* Benefits */}
        <div style={s.benefits}>
          {content.benefits.map(b => (
            <div key={b.text} style={s.benefit}>
              <div style={s.benefitText}>{b.text}</div>
            </div>
          ))}
        </div>

        <p style={s.monthlyPrice}>{content.monthly}</p>

        {/* Промокод */}
        <div style={s.promoRow}>
          <input
            style={{ ...s.promoInput, ...(promoApplied ? s.promoInputOk : {}) }}
            placeholder="Промокод"
            value={promoApplied ? `✓ ${promoApplied}` : promoInput}
            disabled={!!promoApplied || promoLoading}
            onChange={e => { setPromoInput(e.target.value); setPromoError(''); }}
            onKeyDown={e => e.key === 'Enter' && handleApplyPromo()}
          />
          {!promoApplied && (
            <MotionButton level="secondary" style={s.promoBtn} onClick={handleApplyPromo} disabled={promoLoading || !promoInput.trim()}>
              {promoLoading ? '…' : 'Применить'}
            </MotionButton>
          )}
          {promoApplied && (
            <button style={s.promoClear} onClick={() => { setPromoApplied(''); setPromoInput(''); }}>✕</button>
          )}
        </div>
        {promoError && <p style={s.promoErrorMsg}>{promoError}</p>}

        {/* CTA */}
        <MotionButton level="primary" style={s.cta} onClick={handleUpgrade} disabled={loading}>
          {loading ? 'Открываем страницу оплаты…' : content.cta}
        </MotionButton>

        {error && <p style={s.error}>{error}</p>}

        {/* E4: явный escape-hatch — не серый-на-сером */}
        <MotionButton level="ghost" style={s.continueFree} onClick={onClose}>
          Продолжить бесплатно
        </MotionButton>

        <p style={s.legal}>{content.price}</p>
      </motion.div>
    </motion.div>
  );
}

const s = {
  overlay: {
    position: 'fixed', inset: 0,
    background: 'rgba(30, 26, 46, 0.55)',
    backdropFilter: 'blur(4px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000,
    padding: '16px',
  },
  modal: {
    background: 'var(--bg-card)',
    borderRadius: '20px',
    border: '0.5px solid var(--border)',
    padding: '32px 28px 24px',
    maxWidth: '420px',
    width: '100%',
    position: 'relative',
    boxShadow: '0 20px 60px rgba(112, 96, 160, 0.15)',
  },
  close: {
    position: 'absolute', top: '16px', right: '16px',
    background: 'none', border: 'none',
    color: 'var(--text-secondary)', fontSize: '16px',
    cursor: 'pointer', padding: '4px',
    lineHeight: 1,
  },
  header: {
    textAlign: 'center',
    marginBottom: '24px',
  },
  badge: {
    display: 'inline-block',
    background: 'var(--accent)',
    color: '#fff',
    fontSize: '11px',
    fontWeight: '600',
    letterSpacing: '0.08em',
    padding: '3px 10px',
    borderRadius: '20px',
    marginBottom: '12px',
    textTransform: 'uppercase',
  },
  title: {
    margin: '0 0 8px',
    fontSize: '20px',
    fontWeight: '600',
    color: 'var(--text-primary)',
    lineHeight: 1.3,
  },
  subtitle: {
    margin: 0,
    fontSize: '14px',
    color: 'var(--text-secondary)',
  },
  benefits: {
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
    marginBottom: '24px',
  },
  benefit: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  benefitText: {
    fontSize: '14px',
    color: 'var(--text-primary)',
    lineHeight: 1.4,
  },
  monthlyPrice: {
    margin: '0 0 16px',
    fontSize: '20px',
    fontWeight: '700',
    color: 'var(--text-primary)',
    textAlign: 'center',
  },
  cta: {
    width: '100%',
    padding: '14px',
    background: 'linear-gradient(135deg, var(--accent) 0%, var(--accent) 100%)',
    color: '#fff',
    border: 'none',
    borderRadius: '12px',
    fontSize: '15px',
    fontWeight: '600',
    cursor: 'pointer',
    fontFamily: 'inherit',
    marginBottom: '12px',
    transition: 'opacity 0.15s',
  },
  error: {
    margin: '0 0 8px',
    fontSize: '12px',
    color: 'var(--color-danger)',
    textAlign: 'center',
  },
  continueFree: {
    display: 'block',
    width: '100%',
    background: 'none',
    border: 'none',
    color: 'var(--accent)',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    fontFamily: 'inherit',
    padding: '6px 0',
    marginBottom: '10px',
    textDecoration: 'underline',
  },
  legal: {
    margin: 0,
    fontSize: '11px',
    color: 'var(--text-secondary)',
    textAlign: 'center',
  },
  promoRow: {
    display: 'flex',
    gap: '8px',
    marginBottom: '6px',
  },
  promoInput: {
    flex: 1,
    padding: '9px 12px',
    border: '1.5px solid var(--border)',
    borderRadius: '8px',
    fontSize: '13px',
    fontFamily: 'inherit',
    color: 'var(--text-primary)',
    background: 'var(--border)',
    outline: 'none',
    letterSpacing: '0.04em',
  },
  promoInputOk: {
    borderColor: 'var(--color-success)',
    background: 'var(--accent-muted)',
    color: 'var(--color-success)',
    fontWeight: '600',
  },
  promoBtn: {
    padding: '9px 14px',
    background: 'var(--bg-card)',
    color: 'var(--text-primary)',
    border: 'none',
    borderRadius: '8px',
    fontSize: '12px',
    fontWeight: '600',
    cursor: 'pointer',
    fontFamily: 'inherit',
    whiteSpace: 'nowrap',
  },
  promoClear: {
    padding: '9px 12px',
    background: 'none',
    color: 'var(--text-secondary)',
    border: '1.5px solid var(--border)',
    borderRadius: '8px',
    fontSize: '13px',
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  promoErrorMsg: {
    margin: '0 0 10px',
    fontSize: '12px',
    color: 'var(--color-danger)',
    textAlign: 'left',
  },
};
