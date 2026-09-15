/**
 * FeedNowStrip.jsx — полоса «сейчас»: три строки заголовка (§6) + чипы
 * долгосрочных периодов (§4).
 *
 * Строки 1-2 добавлены заходом Б (§6 SPEC_FEED_VISUAL.md) — период Солнца и
 * состояние Луны. Не сделано сейчас: полоса НЕ липкая (`position: sticky`),
 * хотя §6 явно просит `top: 0`. Причина — заголовки дней (`FeedDayHeader.jsx`)
 * уже липкие на том же `top: 0` того же скроллера, а высота этой полосы
 * плавает (открытие чипа добавляет `ExpandedCard`, строки 1-2 пропадают при
 * нехватке данных) — без измерения фактической высоты и проброса её как
 * `top`-отступа в заголовки дней они наедут друг на друга или полоса
 * перекроет часть контента. Сделать правильно — отдельная, самостоятельная
 * задача (ResizeObserver + проброс отступа), не путать с содержимым строк.
 *
 * Чипы долгосрочных периодов — пять медленных планет (Юпитер, Сатурн,
 * Уран, Нептун, Плутон), по одному текущему периоду на планету, структурная
 * константа бэкенда. Из хронологического потока они изъяты полностью, и
 * это главное, ради чего полоса изначально была заведена.
 *
 * ⚠️ Высота полосы ФИКСИРОВАННАЯ, приём «высота ∝ длительности» к ней не
 * применяется — именно поэтому долгосрочные и вынесены. Период Плутона идёт
 * 19 лет; в потоке, где высота значит длительность, он растянулся бы на
 * тысячи пикселей и сломал бы шкалу для всего остального. После изъятия
 * самое длинное в потоке — месячный период Солнца, и приём снова честен.
 *
 * ⚠️ Что потеряно вместе с изъятием: привязка к шкале. «Сатурн выйдет из 7
 * дома через полгода» на таймлайне больше не видно, и §4 требует
 * компенсировать это словами — поэтому в развёрнутой карточке срок написан
 * текстом («с ноября 2012 по март 2032»), а не только нарисован.
 *
 * Порядок чипов — от самого короткого периода к самому длинному
 * (Юпитер → Плутон), НЕ по дате начала: периоды идут одновременно, и
 * хронология между ними бессмысленна.
 */

import React, { useState } from 'react';
import BlurredHint from './BlurredHint';
import HintButton from './HintButton';
import { glyph, glyphStyle } from '../lib/feedGlyphs';
import { daysBetween, periodRange } from '../lib/feedTime';
// Отбор — общий с компактной полоской (FeedNowCompact.jsx): один факт,
// два вида. Разбор, почему вынесено, — в шапке lib/feedNow.js.
import { findMoonState, findSunPeriod, longtermChips, pluralDays } from '../lib/feedNow';
import { signInRu } from '../lib/ruDeclension';

function Chip({ event, active, onClick }) {
  const meta = event.meta || {};
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        flex: '1 1 0',
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 2,
        padding: '8px 2px',
        borderRadius: 'var(--radius-md)',
        border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
        background: active ? 'var(--accent-muted)' : 'var(--bg-card)',
        color: active ? 'var(--accent)' : 'var(--text-primary)',
      }}
    >
      <span style={{ ...glyphStyle, fontSize: 17 }}>{glyph(meta.planet)}</span>
      {/* «11 дом», без слова «дом» во второй строке места не хватает на
          узком экране — пять чипов делят ширину поровну (§12.3). */}
      <span style={{ fontSize: 11, fontFamily: 'var(--font-body)', fontWeight: 600, whiteSpace: 'nowrap' }}>
        {meta.house} дом
      </span>
    </button>
  );
}

function ExpandedCard({ event, onUpgrade }) {
  const meta = event.meta || {};
  const groups = Array.isArray(meta.groups) ? meta.groups : [];
  const hasContent = groups.some((g) => (g.items || []).length > 0);

  return (
    <div
      style={{
        marginTop: 10,
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ ...glyphStyle, fontSize: 18, color: 'var(--accent)' }}>{glyph(meta.planet)}</span>
        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, fontFamily: 'var(--font-display)', color: 'var(--text-primary)' }}>
          {meta.planet_name} в {meta.house} доме
        </h3>
      </div>

      {/* Срок словами — компенсация потерянной шкалы, см. шапку файла. */}
      <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
        {periodRange(event.at, event.ends_at)}
      </div>

      {meta.theme && (
        <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{meta.theme}</div>
      )}

      {hasContent
        ? groups.map((group, gi) => (
          <ul key={gi} style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            {(group.items || []).map((item) => <li key={item}>{item}</li>)}
          </ul>
        ))
        : <BlurredHint />}

      {event.locked && (
        <button
          type="button"
          className="mobile-btn-primary"
          disabled={!onUpgrade}
          onClick={onUpgrade ? () => onUpgrade(event) : undefined}
          style={{ marginTop: 4 }}
        >
          Открыть доступ
        </button>
      )}
    </div>
  );
}

export default function FeedNowStrip({ events, today, onUpgrade, onHelp, chipsRef }) {
  const [openKey, setOpenKey] = useState(null);
  const all = events || [];
  const longterm = longtermChips(all);
  const sunPeriod = findSunPeriod(all, today);
  const moonState = findMoonState(all, today);

  if (longterm.length === 0 && !sunPeriod && !moonState) return null;

  // Порядок и копия — в longtermChips() (lib/feedNow.js), общая с компактной
  // полоской.
  const chips = longterm;
  const open = chips.find((e) => e.key === openKey) || null;

  return (
    // position: relative — под кнопку «?» в правом верхнем углу
    // (SPEC_ONBOARDING.md §8). У экрана «Лента», в отличие от «Карты», нет
    // ни <header>, ни <h1> — ставить кнопку больше некуда, а заводить ради
    // неё полноценную шапку значит отъесть вертикаль там, где её и так не
    // хватает (тот же довод, по которому 06.09.2026 решено не делать
    // липкими одновременно полоску дней и заголовок дня).
    <section style={{ padding: '12px 0 4px', position: 'relative' }}>
      {onHelp && (
        <HintButton
          onClick={onHelp}
          style={{ position: 'absolute', top: 8, right: 0, zIndex: 2 }}
        />
      )}

      {/* Строка 1 (§6) — период Солнца, остаток словами. paddingRight —
          место под кнопку «?», иначе остаток дней уходит под неё. */}
      {sunPeriod && (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4, paddingRight: 36 }}>
          <span style={{ ...glyphStyle, fontSize: 17, color: 'var(--color-warning)' }}>☉</span>
          <h2
            style={{
              margin: 0,
              fontSize: 19,
              fontWeight: 600,
              fontFamily: 'var(--font-display)',
              color: 'var(--text-primary)',
            }}
          >
            Период Солнца
          </h2>
          <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-secondary)', flexShrink: 0 }}>
            {(() => {
              const left = daysBetween(today, sunPeriod.ends_at.slice(0, 10));
              return `${left} ${pluralDays(left)}`;
            })()}
          </span>
        </div>
      )}

      {/* Строка 2 (§6) — состояние Луны. Не хватает данных — строки нет вовсе. */}
      {moonState && (
        <div style={{ margin: '0 0 8px', fontSize: 13, color: 'var(--text-secondary)' }}>
          Луна в <span style={{ color: 'var(--text-primary)' }}>{signInRu(moonState.currentSign)}</span>
          {' · до '}{moonState.phaseGenitive} в{' '}
          <span style={{ color: 'var(--text-primary)' }}>{signInRu(moonState.phaseSign)}</span>
          {' '}{moonState.daysUntil} {pluralDays(moonState.daysUntil)}
        </div>
      )}

      {chips.length > 0 && (
        <>
          <h2
            style={{
              margin: '0 0 8px',
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.09em',
              textTransform: 'uppercase',
              fontFamily: 'var(--font-body)',
              color: 'var(--text-secondary)',
            }}
          >
            Планеты сейчас в домах
          </h2>

          <div ref={chipsRef} style={{ display: 'flex', gap: 6 }}>
            {chips.map((event) => (
              <Chip
                key={event.key}
                event={event}
                active={event.key === openKey}
                onClick={() => setOpenKey(event.key === openKey ? null : event.key)}
              />
            ))}
          </div>

          {open && <ExpandedCard event={open} onUpgrade={onUpgrade} />}
        </>
      )}
    </section>
  );
}
