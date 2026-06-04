/**
 * PaywallModal.jsx — контекстный модал апгрейда
 *
 * Props:
 *   context: 'free_to_lite' | 'lite_to_pro' | 'pro_to_premium'
 *   onClose: () => void
 *   chartId?: string (optional, for checkout redirect)
 */

import React, { useState } from 'react';
import { createCheckoutSession, validatePromoCode } from '../api/client';

const PAYWALL_CONTENT = {
  free_to_lite: {
    badge: 'Lite',
    title: 'Прочитайте полную интерпретацию',
    subtitle: 'Узнайте больше о себе — без ограничений',
    benefits: [
      { icon: '🔮', text: 'Полный текст без ограничений — 800 слов о вас' },
      { icon: '🪐', text: 'Просмотр всех активных транзитов' },
      { icon: '📅', text: 'Планер Timeline на год вперёд' },
      { icon: '🌙', text: 'Лунный календарь на год вперёд' },
      { icon: '✨', text: 'Виральная карточка вашей карты для Stories' },
    ],
    cta: 'Перейти на Lite — 790 ₽/мес',
    price: 'Отмена в любой момент · Без обязательств',
    tier: 'lite',
    monthly: '790 ₽ / мес',
    annual: '7 490 ₽ / год',
    annualNote: '624 ₽/мес при оплате за год',
    annualSave: '−21%',
  },
  lite_to_pro: {
    badge: 'Pro',
    title: 'Разблокируйте ваши транзиты',
    subtitle: 'AI-интерпретации и чат-ассистент',
    benefits: [
      { icon: '🪐', text: 'AI-объяснение каждого транзита лично для вашей карты' },
      { icon: '💬', text: 'Чат-ассистент: задайте любой вопрос о своей карте' },
      { icon: '📄', text: 'PDF-отчёты для скачивания' },
    ],
    cta: 'Перейти на Pro — 1 990 ₽/мес',
    price: 'Отмена в любой момент · Без обязательств',
    tier: 'pro',
    monthly: '1 990 ₽ / мес',
    annual: '18 990 ₽ / год',
    annualNote: '1 582 ₽/мес при оплате за год',
    annualSave: '−20%',
  },
  pro_to_premium: {
    badge: 'Premium',
    title: 'Работаете с клиентами?',
    subtitle: '1 клиент окупает подписку',
    benefits: [
      { icon: '👥', text: 'CRM клиентов — карты и заметки в одном месте' },
      { icon: '📊', text: '100 AI-интерпретаций в месяц на GPT-4o' },
      { icon: '🖨️', text: 'Безлимитный PDF с вашим брендингом' },
    ],
    cta: 'Перейти на Premium — 7 990 ₽/мес',
    price: '1 клиент окупает подписку',
    tier: 'premium',
    monthly: '7 990 ₽ / мес',
    annual: '75 990 ₽ / год',
    annualNote: '6 332 ₽/мес при оплате за год',
    annualSave: '−21%',
  },
};

/**
 * Determine paywall context from API error response.
 * Backend returns: { error: "tier_required", required: "pro", current: "lite" }
 */
export function getPaywallContext(errorDetail) {
  if (!errorDetail || errorDetail.error !== 'tier_required') return null;
  const { current, required } = errorDetail;
  if (current === 'free' && ['lite', 'pro', 'premium'].includes(required)) return 'free_to_lite';
  if (current === 'lite' && ['pro', 'premium'].includes(required)) return 'lite_to_pro';
  if (current === 'pro' && required === 'premium') return 'pro_to_premium';
  return 'free_to_lite'; // fallback
}

export default function PaywallModal({ context = 'free_to_lite', onClose, chartId }) {
  const content = PAYWALL_CONTENT[context] || PAYWALL_CONTENT.free_to_lite;
  const [billing, setBilling]         = useState('monthly');
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
      const { url } = await createCheckoutSession(content.tier, billing, chartId, promoApplied || null);
      window.location.href = url;
    } catch (e) {
      if (e.detail?.error === 'invalid_promo_code') {
        setPromoError('Промокод не действителен');
        setPromoApplied('');
      } else {
        setError('Не удалось открыть страницу оплаты. Попробуйте позже.');
      }
      setLoading(false);
    }
  }

  return (
    <div style={s.overlay} onClick={onClose}>
      <div style={s.modal} onClick={e => e.stopPropagation()}>

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
              <span style={s.benefitIcon}>{b.icon}</span>
              <div style={s.benefitText}>{b.text}</div>
            </div>
          ))}
        </div>

        {/* Billing toggle */}
        <div style={s.billingToggle}>
          <button
            style={{ ...s.toggleBtn, ...(billing === 'monthly' ? s.toggleActive : {}) }}
            onClick={() => setBilling('monthly')}
          >
            {content.monthly}
          </button>
          <button
            style={{ ...s.toggleBtn, ...(billing === 'annual' ? s.toggleActive : {}) }}
            onClick={() => setBilling('annual')}
          >
            {content.annual}
            <span style={s.saveBadge}>{content.annualSave}</span>
          </button>
        </div>

        {billing === 'annual' && (
          <p style={s.annualNote}>{content.annualNote}</p>
        )}

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
            <button style={s.promoBtn} onClick={handleApplyPromo} disabled={promoLoading || !promoInput.trim()}>
              {promoLoading ? '…' : 'Применить'}
            </button>
          )}
          {promoApplied && (
            <button style={s.promoClear} onClick={() => { setPromoApplied(''); setPromoInput(''); }}>✕</button>
          )}
        </div>
        {promoError && <p style={s.promoErrorMsg}>{promoError}</p>}

        {/* CTA */}
        <button style={s.cta} onClick={handleUpgrade} disabled={loading}>
          {loading ? 'Открываем страницу оплаты…' : content.cta}
        </button>

        {error && <p style={s.error}>{error}</p>}

        <p style={s.legal}>{content.price}</p>
      </div>
    </div>
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
    background: '#FFFFFF',
    borderRadius: '20px',
    border: '0.5px solid #EDE8F5',
    padding: '32px 28px 24px',
    maxWidth: '420px',
    width: '100%',
    position: 'relative',
    boxShadow: '0 20px 60px rgba(112, 96, 160, 0.15)',
  },
  close: {
    position: 'absolute', top: '16px', right: '16px',
    background: 'none', border: 'none',
    color: '#9080B0', fontSize: '16px',
    cursor: 'pointer', padding: '4px',
    lineHeight: 1,
  },
  header: {
    textAlign: 'center',
    marginBottom: '24px',
  },
  badge: {
    display: 'inline-block',
    background: '#1E1A2E',
    color: '#FFFFFF',
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
    color: '#1E1A2E',
    lineHeight: 1.3,
  },
  subtitle: {
    margin: 0,
    fontSize: '14px',
    color: '#7060A0',
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
  benefitIcon: {
    fontSize: '20px',
    lineHeight: 1,
    flexShrink: 0,
  },
  benefitText: {
    fontSize: '14px',
    color: '#1E1A2E',
    lineHeight: 1.4,
  },
  billingToggle: {
    display: 'flex',
    gap: '8px',
    marginBottom: '8px',
  },
  toggleBtn: {
    flex: 1,
    padding: '10px 12px',
    border: '1.5px solid #EDE8F5',
    borderRadius: '10px',
    background: '#F4F0FA',
    color: '#7060A0',
    fontSize: '13px',
    fontWeight: '500',
    cursor: 'pointer',
    fontFamily: 'inherit',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    transition: 'all 0.15s',
  },
  toggleActive: {
    background: '#1E1A2E',
    color: '#FFFFFF',
    borderColor: '#1E1A2E',
  },
  saveBadge: {
    background: '#4CAF50',
    color: '#fff',
    fontSize: '10px',
    fontWeight: '700',
    padding: '1px 5px',
    borderRadius: '4px',
  },
  annualNote: {
    margin: '0 0 16px',
    fontSize: '12px',
    color: '#7060A0',
    textAlign: 'center',
  },
  cta: {
    width: '100%',
    padding: '14px',
    background: 'linear-gradient(135deg, #6C3CE0 0%, #9060C8 100%)',
    color: '#FFFFFF',
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
    color: '#C03030',
    textAlign: 'center',
  },
  legal: {
    margin: 0,
    fontSize: '11px',
    color: '#9080B0',
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
    border: '1.5px solid #EDE8F5',
    borderRadius: '8px',
    fontSize: '13px',
    fontFamily: 'inherit',
    color: '#1E1A2E',
    background: '#F4F0FA',
    outline: 'none',
    letterSpacing: '0.04em',
  },
  promoInputOk: {
    borderColor: '#4CAF50',
    background: '#F0FBF0',
    color: '#2E7D32',
    fontWeight: '600',
  },
  promoBtn: {
    padding: '9px 14px',
    background: '#1E1A2E',
    color: '#fff',
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
    color: '#9080B0',
    border: '1.5px solid #EDE8F5',
    borderRadius: '8px',
    fontSize: '13px',
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  promoErrorMsg: {
    margin: '0 0 10px',
    fontSize: '12px',
    color: '#C03030',
    textAlign: 'left',
  },
};
