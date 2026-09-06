/**
 * MoreSwitch.jsx — визуальный тумблер (трек + бегунок), а не текст «Вкл/Выкл».
 *
 * Заведён 06.09.2026 по правке приёмки: «Тёмная тема» на экране «Ещё»
 * выглядела строкой меню с индикатором-текстом, в прототипе — тумблер.
 * Один компонент на все булевы переключатели этого экрана (тема,
 * уведомления, экспертный режим) — не по одному текстовому индикатору на
 * каждый, иначе ряды выглядели бы вперемешку.
 */

import React from 'react';

export default function MoreSwitch({ on }) {
  return (
    <span
      aria-hidden="true"
      style={{
        width: 44,
        height: 26,
        borderRadius: 13,
        background: on ? 'var(--accent)' : 'var(--border)',
        position: 'relative',
        flexShrink: 0,
        transition: 'background-color 0.15s ease',
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 3,
          left: on ? 21 : 3,
          width: 20,
          height: 20,
          borderRadius: '50%',
          background: '#fff',
          boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
          transition: 'left 0.15s ease',
        }}
      />
    </span>
  );
}
