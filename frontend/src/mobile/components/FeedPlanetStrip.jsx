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
import { planetDotColor } from '../lib/feedTimelineDot';

export default function FeedPlanetStrip({ items, onOpen, compact = false, innerRef }) {
  if (!items || items.length === 0) return null;

  const ring = compact ? 24 : 34;
  const glyphSize = compact ? 13 : 17;

  return (
    <div
      ref={innerRef}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: compact ? 6 : 8,
        minWidth: 0,
        /*
         * ⚠️ Прокрутка вбок, а не деление ширины поровну (приёмка 16.09.2026).
         * Планет десять, и при равных долях каждая получала 35px на кружок,
         * значок и номер дома — на пределе даже при обычном системном шрифте,
         * а при увеличенном ряд ломался. Полоса дней рядом решает то же самое
         * тем же способом, так что приём не новый.
         */
        overflowX: 'auto',
        overflowY: 'hidden',
        scrollbarWidth: 'none',
        /* Обрезанный кружок у кромки тает, а не торчит половиной — тот же
           приём, что у полосы дней (FeedDayStrip.jsx). */
        maskImage: 'linear-gradient(to right, transparent, black 10px, black calc(100% - 10px), transparent)',
        WebkitMaskImage: 'linear-gradient(to right, transparent, black 10px, black calc(100% - 10px), transparent)',
      }}
    >
      {items.map((event) => {
        const meta = event.meta || {};
        const openable = typeof onOpen === 'function';
        const color = planetDotColor(meta.planet);
        return (
          <button
            key={event.key}
            type="button"
            onClick={openable ? () => onOpen(event) : undefined}
            disabled={!openable}
            aria-label={`${meta.planet_name || ''} в ${meta.house} доме`}
            style={{
              flexShrink: 0,
              display: 'flex',
              flexDirection: compact ? 'row' : 'column',
              alignItems: 'center',
              gap: compact ? 3 : 3,
              padding: 0,
              background: 'transparent',
              border: 'none',
              font: 'inherit',
              color: 'var(--text-primary)',
              cursor: openable ? 'pointer' : 'default',
            }}
          >
            {/*
              Кружок в цвете планеты — та же примета, что точка этого события
              на линии времени, и тот же источник цвета (planetDotColor).
              ⚠️ Цвет здесь ВТОРАЯ примета: значок внутри остаётся всегда, и
              по нему планета опознаётся без цвета вовсе.
            */}
            <span
              style={{
                width: ring,
                height: ring,
                flexShrink: 0,
                borderRadius: '50%',
                border: `1.5px solid ${color}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <span style={{ ...glyphStyle, fontSize: glyphSize, color }}>{glyph(meta.planet)}</span>
            </span>
            {/* Только число: слово «дом» не влезает ни в липкую строку из
                десяти планет, ни в развёрнутую на узком экране. Что это дом,
                говорит единообразие ряда и подпись над ним. */}
            <span
              style={{
                fontSize: compact ? 11 : 12,
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
