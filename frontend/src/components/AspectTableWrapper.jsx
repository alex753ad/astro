/**
 * AspectTableWrapper.jsx
 *
 * Анимированная обёртка для AspectTable.
 * expertMode=false → плавно схлопывается, убирается из DOM.
 * expertMode=true  → монтируется, плавно раскрывается.
 */

import React, { useRef, useEffect, useState } from 'react';
import AspectTable from './AspectTable';

export default function AspectTableWrapper({ expertMode, ...props }) {
  const [mounted, setMounted]     = useState(expertMode);
  const [maxHeight, setMaxHeight] = useState(expertMode ? '2000px' : '0px');
  const [opacity, setOpacity]     = useState(expertMode ? 1 : 0);
  const innerRef = useRef(null);

  useEffect(() => {
    if (expertMode) {
      setMounted(true);
      const raf = requestAnimationFrame(() => {
        if (innerRef.current) {
          setMaxHeight(innerRef.current.scrollHeight + 40 + 'px');
        }
        setOpacity(1);
      });
      return () => cancelAnimationFrame(raf);
    } else {
      setMaxHeight('0px');
      setOpacity(0);
      const t = setTimeout(() => setMounted(false), 370);
      return () => clearTimeout(t);
    }
  }, [expertMode]);

  if (!mounted) return null;

  return (
    <div
      style={{
        overflow: 'hidden',
        maxHeight,
        opacity,
        transition: 'max-height 0.35s cubic-bezier(0.4,0,0.2,1), opacity 0.25s ease',
      }}
    >
      <div ref={innerRef}>
        {/* Разделитель с меткой */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px', paddingTop: '2px' }}>
          <span style={{
            fontSize: '11px', fontWeight: '500', letterSpacing: '0.07em',
            textTransform: 'uppercase', color: 'var(--color-text-tertiary)',
          }}>
            Таблица аспектов
          </span>
          <div style={{ flex: 1, height: '1px', background: 'var(--color-border-tertiary)' }} />
          <span style={{
            fontSize: '11px', padding: '2px 9px', borderRadius: '10px',
            background: 'var(--color-background-info)', color: 'var(--color-text-info)',
          }}>
            эксперт
          </span>
        </div>

        <AspectTable {...props} />
      </div>
    </div>
  );
}
