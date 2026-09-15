/**
 * FeedEventRow.jsx — рядовое событие сжатого дня, одна строка
 * (DESIGN_SYSTEM.md §5, «День в ленте — БЛОК, а не строка в потоке»).
 *
 * Принятый ритм задаёт ОБЪЁМ, а не кегль: в дне, который не раскрыт, карточкой
 * остаётся только крупное (feedRank.js), а рядовое сжимается сюда. Разница
 * между «важным» и «рядовым» читается тем, сколько места занимает событие, —
 * поэтому у строки нет ни своего кегля заголовка, ни своего цвета.
 *
 * ⚠️ Строка знаков («18.8° Дева → Телец») здесь НЕ показывается, и это не
 * потеря: её показывает панель события по тапу (FeedEventPanel.jsx), а строка
 * остаётся нажимаемой ровно по тому же правилу isOpenable(), что и карточка.
 * Заводить своё условие открытия нельзя — оно разошлось бы с карточкой молча,
 * как это уже было 09.09.2026 («тапаю на транзиты, ничего не открывается»).
 *
 * ⚠️ Чип орба взят общим компонентом (FeedOrbChip.jsx), а не переписан здесь
 * своими 10 строками: у него внутри пороговое правило («точный» — заливка
 * акцентом), и вторая копия этого правила разъехалась бы с первой при первой
 * же правке порога.
 */

import React from 'react';
import FeedOrbChip from './FeedOrbChip';
import { isOpenable } from './FeedEventCard';
import { aspectColor, aspectSymbol, glyph, glyphStyle } from '../lib/feedGlyphs';
import { eventTitle, planetRu } from '../lib/feedTime';

export default function FeedEventRow({ event, onOpen }) {
  const meta = event.meta || {};
  const openable = isOpenable(event) && typeof onOpen === 'function';
  const formula = event.kind === 'transit' && meta.transit_planet && meta.natal_planet && meta.aspect_type
    ? meta
    : null;

  return (
    <div
      onClick={openable ? () => onOpen(event) : undefined}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        padding: '2px 0',
        fontFamily: 'var(--font-body)',
        cursor: openable ? 'pointer' : 'default',
      }}
    >
      {formula ? (
        <>
          <span style={{ ...glyphStyle, fontSize: 13 }}>{glyph(formula.transit_planet)}</span>
          <span style={{ ...glyphStyle, fontSize: 13, color: aspectColor(formula.aspect_type) }}>
            {aspectSymbol(formula.aspect_type)}
          </span>
          <span style={{ ...glyphStyle, fontSize: 13 }}>{glyph(formula.natal_planet)}</span>
          <span
            style={{
              fontSize: 13,
              color: 'var(--text-primary)',
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {planetRu(formula.transit_planet)} — {planetRu(formula.natal_planet)}
          </span>
        </>
      ) : (
        <span
          style={{
            fontSize: 13,
            color: 'var(--text-primary)',
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {eventTitle(event)}
        </span>
      )}
      <span style={{ marginLeft: 'auto', flexShrink: 0 }}>
        <FeedOrbChip meta={meta} />
      </span>
    </div>
  );
}
