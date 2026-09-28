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
import { createCheckoutSession, apiErrorText } from '../api/client';
import { rememberWebPayment } from '../lib/webPayment';
import MotionButton from './MotionButton';
import { TIER_NAMES, tierPriceLabel } from '../constants';
import { TIER_WORDS } from '../lib/interpretationUpsell';

const overlayVariants = {
  hidden:  { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.2, ease: 'easeOut' } },
  exit:    { opacity: 0, transition: { duration: 0.15, ease: 'easeOut' } },
};

// Пункты — только то, что тариф действительно даёт (TIER_FLAGS). 28.09.2026
// отсюда убраны обещания, которых нет ни в одном тарифе: «планер на 3 месяца»,
// «виральная карточка» (карточка «Поделиться» есть у всех), Google Календарь
// на Лире (он с Веги), синастрия на Орионе (закрыта всем, см. TIER_FLAGS).
// Цены — tierPriceLabel, а не числом: при смене цены по расписанию окно
// показывало бы старую.
const PAYWALL_CONTENT = {
  free_to_lite: {
    badge: TIER_NAMES.lite,
    title: 'Какой период сейчас влияет на твою жизнь',
    subtitle: 'И что это значит для тебя — по твоей карте, а не в общем',
    benefits: [
      { text: `Разбор карты — подробнее, около ${TIER_WORDS.lite} слов` },
      { text: 'Разборы транзитов каждый месяц' },
      { text: 'Чат с Аристеей каждый месяц' },
      { text: 'Планер: Луна по домам на всё окно и периоды Солнца–Марса' },
      { text: 'Лунный календарь на год' },
      { text: 'Экспорт событий в Google Календарь' },
      { text: 'Карты партнёра, детей, родителей — до 5 сохранённых карт' },
    ],
    tier: 'lite',
  },
  lite_to_pro: {
    badge: TIER_NAMES.pro,
    title: 'Ты видишь транзит — Аристея говорит, что в нём делать',
    subtitle: 'Разборы транзитов и чат с Аристеей без лимита',
    benefits: [
      { text: 'Чат с Аристеей без лимита: знает твою карту и помнит суть прошлых разговоров' },
      { text: 'Разбор транзитов без лимита: что транзит значит для тебя и как его прожить' },
      { text: `Разбор карты — самый подробный, около ${TIER_WORDS.pro} слов` },
      { text: 'Планер: долгосрочные периоды — Юпитер, Сатурн, Уран, Нептун, Плутон' },
      { text: 'До 15 сохранённых карт — для семьи' },
    ],
    tier: 'pro',
  },
  pro_to_premium: {
    badge: TIER_NAMES.premium,
    title: 'Подготовка к консультации — 20 минут вместо 2 часов',
    subtitle: 'При 3 клиентах по 4 000 ₽ подписка окупается с первой консультации',
    benefits: [
      { text: 'Разбор карты клиента готовится заранее — к встрече всё уже под рукой' },
      { text: 'Кабинет астролога: клиенты, карты, заметки и история в одном месте' },
      { text: 'PDF-отчёты с твоим именем — клиент уходит с документом' },
      { text: 'Разбор карты без лимита' },
      { text: 'Карты без лимита' },
    ],
    tier: 'premium',
  },
};
for (const c of Object.values(PAYWALL_CONTENT)) {
  c.cta = `Перейти на тариф ${TIER_NAMES[c.tier]} — ${tierPriceLabel(c.tier)}/мес`;
  c.monthly = `${tierPriceLabel(c.tier)} / мес`;
  c.price = c.tier === 'premium'
    ? 'При 3 клиентах по 4 000 ₽ — окупается с первой консультации'
    : 'Доступ на 1 месяц · Без автопродления';
}

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

  async function handleUpgrade() {
    setLoading(true);
    setError(null);
    try {
      // Поле называется checkout_url — так его отдаёт POST /payments/checkout
      // (backend/payments/yookassa_router.py). Раньше здесь читалось { url } —
      // форма ответа Stripe Checkout Session, удалённого 19.08.2026: значение
      // было undefined, браузер уходил на /undefined и показывал пустую
      // страницу, а исключения не возникало и catch не срабатывал.
      const { checkout_url: checkoutUrl, payment_id: paymentId } = await createCheckoutSession(content.tier, 'monthly', chartId);
      if (!checkoutUrl) {
        setError('Платёжный сервис не вернул ссылку на оплату. Попробуй чуть позже.');
        setLoading(false);
        return;
      }
      rememberWebPayment(paymentId, content.tier);
      window.location.href = checkoutUrl;
    } catch (e) {
      setError(apiErrorText(e, 'Не удалось открыть страницу оплаты. Попробуй чуть позже.'));
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
    borderRadius: 'var(--radius-xl)',
    border: '0.5px solid var(--border)',
    padding: '32px 28px 24px',
    maxWidth: '420px',
    width: '100%',
    position: 'relative',
    boxShadow: '0 20px 60px rgba(112, 96, 160, 0.15)', /* леденец: тень держится за градиент-«леденец», удалить вместе с ним — DESIGN_SYSTEM.md §6 */
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
    borderRadius: 'var(--radius-xl)',
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
    borderRadius: 'var(--radius-md)',
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
};
