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
 *
 * ⚠️ `quiet` — ЛУННЫЙ ФОН, а не просто «помельче». Решение владельца
 * 15.09.2026: одиночное лунное событие дня (то, которое не сворачивается,
 * потому что «ещё 1 лунное» ничего не сокращает) рисуется тем же
 * приглушённым видом, что и строка свёртки, — и остаётся ВНИЗУ дня, а не
 * встаёт по времени.
 *
 * Почему не по времени, хотя в сжатом дне «07:56 после 17:34» читается как
 * сбой сортировки: положение фона перестало бы быть предсказуемым — одно
 * лунное стояло бы в потоке, два и больше уезжали бы вниз под свёртку, то
 * есть место события зависело бы от того, сколько их сегодня. Плюс
 * развёрнутая свёртка показывает лунные списком внизу — внутри одного дня
 * появилось бы два разных порядка. Набранная фоном строка внизу дня стоит
 * там законно и сбоем не читается.
 */

import React from 'react';
import FeedLockMark from './FeedLockMark';
import FeedOrbChip from './FeedOrbChip';
import { isOpenable } from './FeedEventCard';
import { aspectColor, aspectSymbol, glyph, glyphStyle } from '../lib/feedGlyphs';
import { eventTitle, moonRangeShort, planetRu } from '../lib/feedTime';

export default function FeedEventRow({ event, onOpen, quiet = false }) {
  const meta = event.meta || {};
  const openable = isOpenable(event) && typeof onOpen === 'function';
  const formula = event.kind === 'transit' && meta.transit_planet && meta.natal_planet && meta.aspect_type
    ? meta
    : null;
  // Проход Луны по дому — недельный горизонт планера (§5 DESIGN_SYSTEM.md).
  // Рядовым он остаётся намеренно: их ~53 на окне ленты, и карточка на
  // каждый вернула бы ту самую массу, ради разбора которой ритм и принят.
  const isMoonHouse = event.kind === 'planner_moon_house';

  /**
   * ⚠️ У прохода Луны СВОЙ вид строки, и это решение приёмки 16.09.2026, а не
   * украшение. Остальные строки сжатого дня — это события, которые уже
   * сказали о себе всё: транзит, фаза, станция. Проход Луны — единственная
   * строка, ЗА которой лежит текст (тема и рекомендации планера), и по
   * рядовой строке этого не видно вовсе: человек читает её как «ещё один
   * транзит» и не нажимает.
   *
   * Отсюда три отличия, все внутри §2 DESIGN_SYSTEM.md, без новых цветов:
   * значок Луны и шеврон набраны `--accent-fg` (акцент в роли текста),
   * заголовок — `--text-primary` даже в приглушённом дне, срок вынесен во
   * вторую строку и переносится. Шеврон, а не рамка: рамка сделала бы строку
   * карточкой и сломала бы ритм, ради которого строку и вводили.
   */
  if (isMoonHouse) {
    return (
      <div
        onClick={openable ? () => onOpen(event) : undefined}
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 8,
          padding: '2px 0',
          fontFamily: 'var(--font-body)',
          cursor: openable ? 'pointer' : 'default',
        }}
      >
        <span style={{ ...glyphStyle, fontSize: 14, color: 'var(--accent-fg)', flexShrink: 0, lineHeight: 1.45 }}>
          {glyph('moon')}
        </span>
        <span style={{ flex: '1 1 auto', minWidth: 0 }}>
          <span style={{ display: 'block', fontSize: 13.5, color: 'var(--text-primary)' }}>
            {eventTitle(event)}
          </span>
          {/* Срок переносится, а не обрезается: обрезанный срок выглядит
              настоящим и потому хуже отсутствующего. */}
          <span style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
            {moonRangeShort(event.at, event.ends_at)}
          </span>
        </span>
        {event.locked && <FeedLockMark />}
        <span
          aria-hidden="true"
          style={{ flexShrink: 0, fontSize: 15, lineHeight: 1.3, color: 'var(--accent-fg)' }}
        >
          ›
        </span>
      </div>
    );
  }

  return (
    <div
      onClick={openable ? () => onOpen(event) : undefined}
      style={{
        display: 'flex',
        // flex-start, а не center: строка формулы может стать двухрядной
        // (см. overflowWrap ниже), и значки обязаны остаться у ПЕРВОГО ряда.
        alignItems: 'flex-start',
        gap: 7,
        padding: '2px 0',
        fontFamily: 'var(--font-body)',
        opacity: quiet ? 0.62 : 1,
        cursor: openable ? 'pointer' : 'default',
      }}
    >
      {formula ? (
        <>
          <span style={{ ...glyphStyle, fontSize: quiet ? 12 : 13 }}>{glyph(formula.transit_planet)}</span>
          <span style={{ ...glyphStyle, fontSize: quiet ? 12 : 13, color: aspectColor(formula.aspect_type) }}>
            {aspectSymbol(formula.aspect_type)}
          </span>
          <span style={{ ...glyphStyle, fontSize: quiet ? 12 : 13 }}>{glyph(formula.natal_planet)}</span>
          <span
            style={{
              fontSize: quiet ? 12 : 13,
              color: quiet ? 'var(--text-secondary)' : 'var(--text-primary)',
              // ⚠️ flex: 1 обязателен. Без него свободное место строки уходило
              // в `margin-left: auto` правого блока, а заголовок сжимался до
              // многоточия при пустом месте справа — ровно то, что поймали на
              // приёмке 15.09.2026 («Меркурий — Ю…» и зазор до чипа).
              flex: '1 1 auto',
              minWidth: 0,
              // ⚠️ ПЕРЕНОС, а не многоточие — приёмка 16.09.2026. Обрезка
              // съедала ВТОРУЮ планету целиком («Меркурий — Ма…», «Венера —
              // Сев. …»), то есть половину содержания аспекта: по первой
              // планете событие не опознать. Сокращать слова тоже нельзя —
              // «Сев. Узел» уже сокращение. Строка на два ряда дороже
              // высотой, но дешевле потерянного смысла.
              //
              // ⚠️ Это НЕ отменяет правило §5 «однострочные сводки не
              // переносятся»: там речь о свёртке лунных, где уступает место
              // список значков, а здесь уступать нечему — обе планеты
              // обязательны.
              overflowWrap: 'anywhere',
            }}
          >
            {planetRu(formula.transit_planet)} — {planetRu(formula.natal_planet)}
          </span>
        </>
      ) : (
        <span
          style={{
            fontSize: quiet ? 12 : 13,
            color: quiet ? 'var(--text-secondary)' : 'var(--text-primary)',
            // Та же причина, что у ветки формулы выше: свободное место строки
            // принадлежит заголовку, иначе он уходит в многоточие при пустом
            // месте справа (приёмка 15.09.2026).
            flex: '1 1 auto',
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {eventTitle(event)}
        </span>
      )}
      {/* Без `margin-left: auto`: место отдаёт заголовок (flex выше), а не
          пустой отступ. Чип не сжимается — «0.1°» не бывает длиннее. */}
      <span style={{ flexShrink: 0 }}>
        <FeedOrbChip meta={meta} />
      </span>
    </div>
  );
}
