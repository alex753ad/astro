/**
 * OnboardingTooltips.jsx — D1
 *
 * Показывает тултипы поверх SVG-карты при первом открытии.
 * Dismiss по клику, флаг astrea_onboarding_seen в localStorage.
 */

import React, { useState, useEffect } from 'react';

const TOOLTIPS = [
  {
    id: 'asc',
    title: 'Асцендент (AC)',
    text: 'Ваша маска для мира — то, каким вас видят окружающие при первом знакомстве.',
    icon: '↑',
  },
  {
    id: 'mc',
    title: 'Середина Неба (MC)',
    text: 'Ваше призвание и публичный образ — то, к чему вы стремитесь в карьере и обществе.',
    icon: '★',
  },
  {
    id: 'aspects',
    title: 'Аспекты',
    text: 'Красные линии — напряжение и рост. Синие — природные таланты и лёгкость.',
    icon: '△',
  },
];

export default function OnboardingTooltips() {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const seen = localStorage.getItem('astrea_onboarding_seen');
    if (!seen) {
      // Небольшая задержка чтобы карта успела отрендериться
      const t = setTimeout(() => setVisible(true), 800);
      return () => clearTimeout(t);
    }
  }, []);

  function dismiss() {
    localStorage.setItem('astrea_onboarding_seen', '1');
    setDismissed(true);
    setVisible(false);
  }

  function next() {
    if (step < TOOLTIPS.length - 1) {
      setStep(s => s + 1);
    } else {
      dismiss();
    }
  }

  if (!visible || dismissed) return null;

  const tip = TOOLTIPS[step];

  return (
    <div style={s.overlay} onClick={dismiss}>
      <div style={s.card} onClick={e => e.stopPropagation()}>
        <div style={s.icon}>{tip.icon}</div>
        <div style={s.title}>{tip.title}</div>
        <div style={s.text}>{tip.text}</div>
        <div style={s.footer}>
          <div style={s.dots}>
            {TOOLTIPS.map((_, i) => (
              <div
                key={i}
                style={{ ...s.dot, ...(i === step ? s.dotActive : {}) }}
              />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={s.skip} onClick={dismiss}>Пропустить</button>
            <button style={s.next} onClick={next}>
              {step < TOOLTIPS.length - 1 ? 'Далее →' : 'Понятно ✓'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

const s = {
  overlay: {
    position: 'fixed', inset: 0,
    background: 'rgba(30, 26, 46, 0.45)',
    backdropFilter: 'blur(2px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 900, padding: 16,
  },
  card: {
    background: 'var(--bg-card)',
    borderRadius: 20,
    border: '0.5px solid var(--border)',
    padding: '28px 24px 20px',
    maxWidth: 360, width: '100%',
    boxShadow: '0 16px 48px rgba(112,96,160,0.18)',
    display: 'flex', flexDirection: 'column', gap: 12,
  },
  icon: {
    width: 48, height: 48, borderRadius: 14,
    background: 'linear-gradient(135deg, rgba(124,108,255,0.15), rgba(192,96,160,0.15))',
    border: '1px solid rgba(124,108,255,0.25)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 22, color: 'var(--accent)',
    fontWeight: 700,
  },
  title: {
    fontSize: 16, fontWeight: 700, color: 'var(--bg-card)',
  },
  text: {
    fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6,
  },
  footer: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    marginTop: 4, flexWrap: 'wrap', gap: 8,
  },
  dots: {
    display: 'flex', gap: 6, alignItems: 'center',
  },
  dot: {
    width: 6, height: 6, borderRadius: 3,
    background: 'var(--border)',
    transition: 'all 0.2s',
  },
  dotActive: {
    width: 18,
    background: 'var(--accent)',
  },
  skip: {
    background: 'none', border: 'none',
    color: 'var(--text-secondary)', fontSize: 12, cursor: 'pointer',
    fontFamily: 'inherit', padding: '6px 10px',
  },
  next: {
    padding: '8px 18px', borderRadius: 10, border: 'none',
    background: 'linear-gradient(135deg, var(--accent), var(--accent))',
    color: '#fff', fontSize: 13, fontWeight: 600,
    cursor: 'pointer', fontFamily: 'inherit',
  },
};
