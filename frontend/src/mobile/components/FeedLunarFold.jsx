/**
 * FeedLunarFold.jsx — свёртка лунного фона внутри дня (§7).
 *
 * На боевых данных лунные транзиты — 75% всей ленты (526 событий из 723,
 * 4–5 записей в день). Развёрнутыми они топят собой то, ради чего лента и
 * открывается: фазы, затмения, точные аспекты медленных планет. Поэтому
 * они сворачиваются в одну строку внизу блока дня.
 *
 * Что сворачивается: `importance === "low"` (это ровно транзиты, где
 * транзитная планета — Луна) плюс `planner_moon_house`. Признак берётся с
 * бэкенда, а не вычисляется на клиенте из имени планеты: важность —
 * серверное решение, и вторая его копия здесь разошлась бы с первой.
 *
 * ⚠️ Фазы Луны и затмения (`moon_phase`, `eclipse`) под свёртку НЕ
 * попадают — у них importance medium/high. Это события, а не фон, и
 * спрятать новолуние под строку «ещё 5 лунных» значило бы спрятать ровно
 * то, за чем в лунный календарь и приходят.
 *
 * В свёрнутой строке — количество и значки НАТАЛЬНЫХ точек, по которым
 * Луна прошла, без повторов. Не значок Луны: она в каждом таком событии
 * одна и та же, информации в ней нет.
 *
 * Состояние (развёрнуто/свёрнуто) живёт в этом компоненте, то есть у
 * каждого дня своё, между днями не разделяется и никуда не сохраняется —
 * так требует §7.
 */

import React, { useState } from 'react';
import FeedEventCard from './FeedEventCard';
import { glyph, glyphStyle } from '../lib/feedGlyphs';

/** Фон дня — то, что прячется под свёртку. */
export function isLunarBackground(event) {
  return event.importance === 'low' || event.kind === 'planner_moon_house';
}

/** Склонение: «1 лунное», «2 лунных», «5 лунных». */
function plural(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'лунное';
  return 'лунных';
}

export default function FeedLunarFold({ events, onOpen }) {
  const [open, setOpen] = useState(false);
  if (!events || events.length === 0) return null;

  // Натальные точки без повторов, в порядке появления — порядок задаёт
  // лента, а не алфавит: так строка совпадает с тем, что человек увидит,
  // когда развернёт.
  const points = [];
  for (const e of events) {
    const g = glyph(e.meta?.natal_planet);
    if (g && !points.includes(g)) points.push(g);
  }

  return (
    <div style={{ paddingBottom: 16 }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          padding: '10px 12px',
          background: 'transparent',
          border: '1px dashed var(--border)',
          borderRadius: 12,
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-body)',
          fontSize: 13,
        }}
      >
        <span>{open ? 'скрыть' : `ещё ${events.length} ${plural(events.length)}`}</span>
        {!open && points.length > 0 && (
          <span style={{ ...glyphStyle, fontSize: 14, letterSpacing: '0.14em', opacity: 0.75 }}>
            {points.join(' ')}
          </span>
        )}
      </button>

      {open && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
          {events.map((event) => (
            <FeedEventCard key={event.key} event={event} onOpen={onOpen} />
          ))}
        </div>
      )}
    </div>
  );
}
