/**
 * ScreenStub.jsx — заглушка вкладки.
 *
 * Общий рендерер для Feed/Chart/More: только заголовок, без контента.
 * Задание прямо описывает эти три экрана как заглушки без содержимого —
 * добавлять сюда что-то вроде «скоро появится» не нужно и намеренно не
 * сделано: одна лишняя строка текста на трёх экранах превращается в три
 * места, которые придётся синхронно вычищать, когда экраны станут настоящими.
 */

import React from 'react';

export default function ScreenStub({ title }) {
  return (
    <div
      style={{
        minHeight: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 700,
          fontSize: 22,
          color: 'var(--text-primary)',
        }}
      >
        {title}
      </span>
    </div>
  );
}
