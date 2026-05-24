/**
 * PaywallModal.jsx — модал апгрейда до Pro
 * Показывается когда Free-пользователь открывает вкладку Транзитов
 */

import React, { useState } from 'react';
import { createCheckoutSession } from '../api/client';

const BENEFITS = [
  {
    icon: '🪐',
    title: 'Транзиты на 6 месяцев вперёд',
    desc: 'Все активные планетарные периоды на твоей карте. В Free транзиты недоступны.',
  },
  {
    icon: '📖',
    title: 'Интерпретация 2000+ слов',
    desc: 'Все планеты, дома и аспекты подробно. В Free — только ~500 слов без деталей.',
  },
  {
    icon: '🗂',
    title: 'До 10 профилей',
    desc: 'Карты партнёра, детей, родителей — сохраняй и переключайся в один клик.',
  },
];

export default function PaywallModal({ onClose, chartId }) {
  const [billing, setBilling] = useState('monthly'); // 'monthly' | 'yearly'
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleUpgrade() {
    setLoading(true);
    setError(null);
    try {
      const { url } = await createCheckoutSession('pro', billing, chartId);
      window.location.href = url;
    } catch (e) {
      setError('Не удалось открыть страницу оплаты. Попробуйте позже.');
      setLoading(false);
    }
  }

  return (
    <div style={s.overlay} onClick={onClose}>
      <div style={s.modal} onClick={e => e.stopPropagation()}>

        {/* Крестик */}
        <button style={s.close} onClick={onClose}>✕</button>

        {/* Заголовок */}
        <div style={s.header}>
          <div style={s.badge}>Pro</div>
          <h2 style={s.title}>Откройте транзиты и полный анализ</h2>
          <p style={s.subtitle}>Узнайте, какие планеты влияют на вас прямо сейчас</p>
        </div>

        {/* Преимущества */}
        <div style={s.benefits}>
          {BENEFITS.map(b => (
            <div key={b.title} style={s.benefit}>
              <span style={s.benefitIcon}>{b.icon}</span>
              <div>
                <div style={s.benefitTitle}>{b.title}</div>
                <div style={s.benefitDesc}>{b.desc}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Переключатель тарифа */}
        <div style={s.billingToggle}>
          <button
            style={{ ...s.toggleBtn, ...(billing === 'monthly' ? s.toggleActive : {}) }}
            onClick={() => setBilling('monthly')}
          >
            $12 / месяц
          </button>
          <button
            style={{ ...s.toggleBtn, ...(billing === 'yearly' ? s.toggleActive : {}) }}
            onClick={() => setBilling('yearly')}
          >
            $99 / год
            <span style={s.saveBadge}>−31%</span>
          </button>
        </div>

        {billing === 'yearly' && (
          <p style={s.yearlyNote}>$8.25 / месяц при оплате за год</p>
        )}

        {/* CTA */}
        <button style={s.cta} onClick={handleUpgrade} disabled={loading}>
          {loading ? 'Открываем страницу оплаты…' : 'Попробовать Pro бесплатно 7 дней'}
        </button>

        {error && <p style={s.error}>{error}</p>}

        <p style={s.legal}>Отмена в любой момент. Без скрытых платежей.</p>
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
    alignItems: 'flex-start',
    gap: '12px',
  },
  benefitIcon: {
    fontSize: '22px',
    lineHeight: 1,
    flexShrink: 0,
    marginTop: '1px',
  },
  benefitTitle: {
    fontSize: '14px',
    fontWeight: '500',
    color: '#1E1A2E',
    marginBottom: '2px',
  },
  benefitDesc: {
    fontSize: '12px',
    color: '#7060A0',
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
  yearlyNote: {
    margin: '0 0 16px',
    fontSize: '12px',
    color: '#7060A0',
    textAlign: 'center',
  },
  cta: {
    width: '100%',
    padding: '14px',
    background: '#1E1A2E',
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
};
