/**
 * FeedNowCompact.jsx — компактная полоска «сейчас» поверх потока.
 *
 * Задача (решение владельца 15.09.2026): состояние «сейчас» не должно
 * зависеть от позиции прокрутки. Развёрнутая полоса (FeedNowStrip.jsx) стоит
 * в начале списка и уезжает вверх; прокрутив ленту на месяц назад, до неё
 * нельзя добраться иначе как вернувшись в самое начало, а это тысячи
 * пикселей: вся лента на боевых данных — 28 093 px.
 *
 * ⚠️ Полоска лежит ПОВЕРХ потока (`position: fixed`), а не схлопывает собой
 * исходный блок, и это главное решение этого файла. Если уменьшать блок в
 * самом потоке (211 px развёрнутый → 44 px компактный), содержимое под
 * пальцем подскочит на 167 px в момент пересечения порога. Оверлей не
 * трогает раскладку вовсе, поэтому прыжка нет ни одного.
 *
 * ⚠️ Бюджет высоты — не украшение, а ограничение экрана. Прилипнуть могли бы
 * три слоя сразу: полоса «сейчас» (143 px), полоска дней (68) и заголовок дня
 * (39) — вместе 250 px из 788 доступных, треть экрана до первой карточки.
 * Сегодня липнет РОВНО ОДНА строка в 44 px: заголовки дней с 15.09.2026 не
 * липкие вовсе (разбор — в шапке FeedDayHeader.jsx).
 *
 * ⚠️ Отсюда вторая обязанность этой строки: она показывает ДЕНЬ У КРОМКИ —
 * тот, чьи события сейчас на экране. Пока заголовки липли, на вопрос «какой
 * день я смотрю» отвечали они; сняв липкость, ответ надо было вернуть, иначе
 * при прокрутке на месяц назад человек видит события без даты.
 *
 * ⚠️ Дата пишется ПРЯМО В DOM (`dateRef`), в обход состояния React. День у
 * кромки меняется на каждой границе суток — при быстрой прокрутке это десятки
 * раз в секунду, и `setState` перерисовывал бы весь список из 148 секций.
 * Подробности — в шапке lib/useTopDay.js.
 *
 * ⚠️ Свой safe-area отступ обязателен: `position: fixed` считается от окна, а
 * не от скроллера, и верхний отступ TabShell.jsx на него не распространяется.
 * Без этого полоска уедет под статус-бар на edge-to-edge (targetSdk 35).
 *
 * Тап уводит к началу ленты — туда, где стоит развёрнутая полоса с чипами
 * домов и раскрытием периода. Компактная строка показывает состояние, но
 * раскрывать его у себя не умеет: второй набор раскрытий был бы вторым видом
 * одного и того же, а этого в ленте уже избегали (см. §7 про свёртку).
 */

import React from 'react';
import { glyph, glyphStyle } from '../lib/feedGlyphs';
import { findMoonState, findSunPeriod, longtermChips, pluralDays } from '../lib/feedNow';
import { daysBetween } from '../lib/feedTime';
// Именительный падеж, а не предложный: предлога «в» рядом со значком Луны
// здесь нет — он съедал место, которого в 44px строке нет ни на что
// лишнее. В развёрнутой полосе предлог остаётся (там фраза целиком).
import { SIGN_RU } from '../lib/feedTime';

/** Высота самой строки, без safe-area. Заголовки дней липнут ровно под неё. */
export const COMPACT_HEIGHT = 44;

export default function FeedNowCompact({ events, today, visible, onGoTop, dateRef }) {
  const all = events || [];
  const sunPeriod = findSunPeriod(all, today);
  const moonState = findMoonState(all, today);
  const chips = longtermChips(all);

  // Нечего показать — нечего и прилеплять: пустая полоска отъедала бы
  // 44 px экрана, не сообщая ничего.
  if (!sunPeriod && !moonState && chips.length === 0) return null;

  const sunLeft = sunPeriod ? daysBetween(today, sunPeriod.ends_at.slice(0, 10)) : null;

  return (
    <div
      onClick={onGoTop}
      aria-hidden={!visible}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 5,
        // Плашка непрозрачная и своей поверхностью: под ней едет лента, а в
        // светлой теме ещё и градиент страницы — полупрозрачная полоска
        // пропускала бы под собой текст (тот же довод, что у заголовка дня).
        background: 'var(--bg-card)',
        borderBottom: '1px solid var(--border)',
        boxShadow: 'var(--shadow-card)',
        paddingTop: 'env(safe-area-inset-top)',
        // Появление — прозрачностью и сдвигом, без изменения высоты: высота
        // здесь ничего не занимает (fixed), а анимировать её у липкого слоя
        // значит двигать точку прилипания заголовков дня на каждом кадре.
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(-100%)',
        transition: 'opacity 0.18s ease, transform 0.18s ease',
        pointerEvents: visible ? 'auto' : 'none',
      }}
    >
      <div
        style={{
          height: COMPACT_HEIGHT,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '0 16px',
          fontFamily: 'var(--font-body)',
          fontSize: 12,
          color: 'var(--text-secondary)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
        }}
      >
        {/* Дата дня у кромки. Ширина фиксирована (tabular-nums + запас), чтобы
            смена дня не двигала соседние блоки строки на каждой границе
            суток — дёрганье было бы заметнее самой даты. */}
        <span
          ref={dateRef}
          style={{
            flexShrink: 0,
            minWidth: 74,
            fontWeight: 700,
            fontSize: 12.5,
            color: 'var(--text-primary)',
            fontVariantNumeric: 'tabular-nums',
          }}
        />
        {sunLeft !== null && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0 }}>
            <span style={{ ...glyphStyle, fontSize: 14, color: 'var(--color-warning)' }}>☉</span>
            <span style={{ color: 'var(--text-primary)' }}>{sunLeft}</span>
            {pluralDays(sunLeft)}
          </span>
        )}
        {moonState && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, minWidth: 0 }}>
            <span style={{ ...glyphStyle, fontSize: 14 }}>☽</span>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--text-primary)' }}>
              {SIGN_RU[moonState.currentSign] || moonState.currentSign}
            </span>
          </span>
        )}
        {/* Дома — значком планеты и номером, без слова «дом»: в развёрнутой
            полосе оно помещается, здесь пять пар делят остаток строки. */}
        {chips.length > 0 && (
          <span style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            // Сжимаются и обрезаются первыми: дома при прокрутке не меняются,
            // а дата и остаток периода меняются — им место нужнее.
            minWidth: 0,
            overflow: 'hidden',
            maskImage: 'linear-gradient(to right, black calc(100% - 16px), transparent)',
            WebkitMaskImage: 'linear-gradient(to right, black calc(100% - 16px), transparent)',
          }}>
            {chips.map((e) => (
              <span key={e.key} style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <span style={{ ...glyphStyle, fontSize: 13, color: 'var(--text-primary)' }}>
                  {glyph(e.meta?.planet)}
                </span>
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{e.meta?.house}</span>
              </span>
            ))}
          </span>
        )}
      </div>
    </div>
  );
}
