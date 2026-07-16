/**
 * StreakBadge.jsx — D5
 *
 * Отображает счётчик «Вы изучаете карту N дней подряд».
 * Показывается на ChartPage при streak >= 2.
 *
 * Props:
 *   streak: number
 *   isNew:  boolean — анимировать при росте стрика
 */

import React, { useState, useEffect } from 'react';

export default function StreakBadge({ streak, isNew }) {
  const [visible, setVisible] = useState(false);
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    if (streak >= 2) {
      setVisible(true);
      if (isNew) {
        // небольшая задержка чтобы CSS transition сработал
        setTimeout(() => setAnimate(true), 100);
        setTimeout(() => setAnimate(false), 2000);
      }
    }
  }, [streak, isNew]);

  if (!visible) return null;

  const emoji = streak >= 30 ? '🔥🔥🔥'
              : streak >= 14 ? '🔥🔥'
              : streak >= 7  ? '🔥'
              : '⚡';

  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '6px 14px', borderRadius: 20,
      background: animate
        ? 'linear-gradient(135deg, rgba(255,140,0,0.18), rgba(255,80,80,0.18))'
        : 'rgba(255,140,0,0.08)',
      border: `1.5px solid ${animate ? 'rgba(255,140,0,0.5)' : 'rgba(255,140,0,0.2)'}`,
      transition: 'all 0.4s ease',
      transform: animate ? 'scale(1.06)' : 'scale(1)',
      cursor: 'default',
      userSelect: 'none',
    }}>
      <span style={{ fontSize: 16, lineHeight: 1 }}>{emoji}</span>
      <span style={{
        fontSize: 13, fontWeight: 600,
        color: streak >= 7 ? 'var(--color-warning)' : 'var(--color-warning)',
      }}>
        {streak} {pluralDays(streak)} подряд
      </span>
    </div>
  );
}

function pluralDays(n) {
  const mod10  = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 19) return 'дней';
  if (mod10 === 1) return 'день';
  if (mod10 >= 2 && mod10 <= 4) return 'дня';
  return 'дней';
}
