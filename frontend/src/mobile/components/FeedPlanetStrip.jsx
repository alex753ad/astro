/**
 * FeedPlanetStrip.jsx — полоса планет: все три горизонта планера одним рядом.
 *
 * Решение владельца 16.09.2026. До него в приложении было два разных ряда
 * значков: чипы пяти медленных планет в развёрнутой полосе и шесть пар
 * «планета — число» в липкой, причём у Солнца число означало ДНИ, а у
 * остальных — ДОМ. Теперь ряд один, семантика одна (дом), и он показывает
 * ровно то, чем планер занят: ☽ — неделя, ☉ ☿ ♀ ♂ — месяц, ♃ ♄ ♅ ♆ ♇ —
 * долгосрочно.
 *
 * ⚠️ Значок НАЖИМАЕТСЯ и открывает панель события — ту же, что вся остальная
 * лента. Это и есть компенсация §4 SPEC_FEED_VISUAL.md для долгосрочных
 * периодов: срок словами («с ноября 2012 по март 2032») живёт в панели.
 * Отбор данных — `plannerTimeline` (lib/feedNow.js), порядок —
 * `PLANNER_PLANET_ORDER` (lib/feedGlyphs.js); здесь только вид.
 *
 * ⚠️ Нажимается ЭЛЕМЕНТ, а не полоса. Обработчик на всём блоке уже ловили на
 * приёмке 15.09.2026: тап по чипу дома уводил ленту на месяц назад.
 *
 * ⚠️ Закрытый тарифом горизонт значка НЕ лишается. Человек должен видеть, что
 * период существует и когда он идёт, — закрыт только разбор, и об этом
 * говорит панель (lib/plannerAccess.js). Спрятав значок, мы спрятали бы сам
 * факт, а не платное содержимое.
 *
 * ⚠️ `compact` — липкий вид (44 px). Отличается ТОЛЬКО размерами и тем, что
 * ряд ужимается растушёвкой вместо переноса: высота липкой строки
 * фиксирована, и перенос выдавил бы её за собственные границы. Второго
 * компонента под это не заводится — разошлись бы порядок и семантика, ровно
 * то, что этой правкой и сводится.
 */

import React from 'react';
import { glyph, glyphStyle } from '../lib/feedGlyphs';

export default function FeedPlanetStrip({ items, onOpen, compact = false, innerRef }) {
  if (!items || items.length === 0) return null;

  const glyphSize = compact ? 13 : 17;
  const houseSize = compact ? 11 : 11;

  return (
    <div
      ref={innerRef}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: compact ? 8 : 4,
        minWidth: 0,
        // В липком виде ряд не переносится и гасится у правой кромки; в
        // развёрнутом планеты делят ширину поровну, как делали чипы домов.
        ...(compact
          ? {
            overflow: 'hidden',
            maskImage: 'linear-gradient(to right, black calc(100% - 8px), transparent)',
            WebkitMaskImage: 'linear-gradient(to right, black calc(100% - 8px), transparent)',
          }
          : {}),
      }}
    >
      {items.map((event) => {
        const meta = event.meta || {};
        const openable = typeof onOpen === 'function';
        return (
          <button
            key={event.key}
            type="button"
            onClick={openable ? () => onOpen(event) : undefined}
            disabled={!openable}
            aria-label={`${meta.planet_name || ''} в ${meta.house} доме`}
            style={{
              // Развёрнутый вид: равные доли, как у прежних чипов домов.
              // Липкий: по содержимому, иначе десять планет растянули бы
              // строку и вытеснили кнопку «Сегодня».
              ...(compact ? { flexShrink: 0 } : { flex: '1 1 0', minWidth: 0 }),
              display: 'flex',
              flexDirection: compact ? 'row' : 'column',
              alignItems: 'center',
              gap: compact ? 2 : 2,
              padding: compact ? 0 : '4px 2px',
              background: 'transparent',
              border: 'none',
              font: 'inherit',
              color: 'var(--text-primary)',
              cursor: openable ? 'pointer' : 'default',
            }}
          >
            <span style={{ ...glyphStyle, fontSize: glyphSize }}>{glyph(meta.planet)}</span>
            {/* Только число: слово «дом» не влезает ни в липкую строку из
                десяти планет, ни в развёрнутую на узком экране. Что это дом,
                говорит единообразие ряда и подпись над ним. */}
            <span
              style={{
                fontSize: houseSize,
                fontFamily: 'var(--font-body)',
                fontWeight: 600,
                fontVariantNumeric: 'tabular-nums',
                whiteSpace: 'nowrap',
              }}
            >
              {meta.house}
            </span>
          </button>
        );
      })}
    </div>
  );
}
