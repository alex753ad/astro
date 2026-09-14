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
import { signInRu } from '../lib/ruDeclension';

/** «1 день» / «3 дня» / «5 дней» — остаток периода и срок до фазы (§6). */
function pluralDays(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'день';
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return 'дня';
  return 'дней';
}

// Родительный падеж для «до …» (§6: «до полнолуния», «до новолуния»).
// Лента строит только эти два — квадратов (первая/последняя четверть) в
// /feed нет вовсе (см. builder.py: phase_events собирает только new_moon
// и full_moon).
const PHASE_GENITIVE = {
  new_moon: 'новолуния',
  full_moon: 'полнолуния',
};

/**
 * Строка 1 (§6) — текущий период Солнца: тот же planner_period, что уже
 * идёт в потоке ленты (не вторая выборка с другим правилом) — здесь просто
 * найден среди events тот единственный экземпляр, что покрывает сегодня.
 */
function findSunPeriod(events, today) {
  return events.find((e) => (
    e.kind === 'planner_period'
    && e.meta?.planet === 'sun'
    && e.at.slice(0, 10) <= today
    && today <= (e.ends_at || '').slice(0, 10)
  )) || null;
}

/**
 * Строка 2 (§6) — состояние Луны: ближайшая фаза ВПЕРЁД от сегодня плюс
 * текущий знак Луны. Своей ручки под «текущий знак» у мобильного приложения
 * нет (§6 спецификации admits второй вариант — знак берётся из ближайшего
 * лунного транзита, а не из /calendar/lunar: третий запрос ради одной
 * строки нарушил бы правило feedApi.js «запросов ровно два»). Ближайший —
 * по минимальной разнице календарных дат с сегодня, не обязательно вперёд:
 * трактует «ближайший» буквально, как написано в спецификации.
 */
function findMoonState(events, today) {
  const nextPhase = events
    .filter((e) => e.kind === 'moon_phase' && e.at.slice(0, 10) >= today)
    .sort((a, b) => (a.at < b.at ? -1 : 1))[0] || null;

  const moonTransits = events.filter((e) => e.kind === 'transit' && e.meta?.transit_planet === 'Moon');
  let nearestMoon = null;
  let nearestDiff = Infinity;
  for (const e of moonTransits) {
    const diff = Math.abs(daysBetween(today, e.at.slice(0, 10)));
    if (diff < nearestDiff) { nearestDiff = diff; nearestMoon = e; }
  }

  if (!nextPhase || !nearestMoon) return null; // §6: не хватает данных — строку не рисуем.

  return {
    currentSign: nearestMoon.meta.transit_sign,
    phaseGenitive: PHASE_GENITIVE[nextPhase.meta?.type] || 'фазы',
    phaseSign: nextPhase.meta?.sign,
    daysUntil: Math.max(0, daysBetween(today, nextPhase.at.slice(0, 10))),
  };
}

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
  const longterm = all.filter((e) => e.kind === 'planner_longterm');
  const sunPeriod = findSunPeriod(all, today);
  const moonState = findMoonState(all, today);

  if (longterm.length === 0 && !sunPeriod && !moonState) return null;

  // Копия перед сортировкой: массив приходит из состояния экрана, и sort
  // на месте перетасовал бы его там же.
  const chips = [...longterm].sort((a, b) => (a.duration_days || 0) - (b.duration_days || 0));
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
