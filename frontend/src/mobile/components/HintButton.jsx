/**
 * HintButton.jsx — кнопка «?» в шапке экрана (SPEC_ONBOARDING.md §8).
 *
 * Доступна всегда, а не только до первого показа: это постоянный вход в
 * справку по экрану, а не «показать ещё раз, если не запомнил».
 *
 * Размер 28px — меньше, чем рекомендуемые 44px для основной цели касания,
 * и это осознанно: кнопка вторичная, стоит в шапке рядом с заголовком, и
 * 44px раздули бы шапку на экране, где вертикали и так не хватает. Промах
 * по ней ничего не ломает и ничем не грозит.
 */

import React from 'react';
import { HINT_BUTTON_LABEL } from '../lib/onboardingCopy';

export default function HintButton({ onClick, style }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={HINT_BUTTON_LABEL}
      style={{
        width: 28,
        height: 28,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: '50%',
        border: '1px solid var(--border)',
        background: 'var(--bg-card)',
        color: 'var(--text-secondary)',
        fontFamily: 'var(--font-display)',
        fontSize: 14,
        fontWeight: 600,
        lineHeight: 1,
        padding: 0,
        cursor: 'pointer',
        ...style,
      }}
    >
      ?
    </button>
  );
}
