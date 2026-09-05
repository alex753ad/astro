/**
 * FeedNowStrip.jsx — полоса «сейчас»: долгосрочные периоды (§4).
 *
 * Пять медленных планет (Юпитер, Сатурн, Уран, Нептун, Плутон) — по одному
 * текущему периоду на планету, структурная константа бэкенда. Из
 * хронологического потока они изъяты полностью, и это главное, ради чего
 * полоса существует.
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
import { glyph, glyphStyle } from '../lib/feedGlyphs';
import { periodRange } from '../lib/feedTime';

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
        borderRadius: 12,
        border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
        background: active ? 'var(--accent-muted)' : 'var(--bg-card)',
        color: active ? 'var(--accent)' : 'var(--text-primary)',
      }}
    >
      <span style={{ ...glyphStyle, fontSize: 17 }}>{glyph(meta.planet)}</span>
      {/* «11 дом», без слова «дом» во второй строке места не хватает на
          узком экране — пять чипов делят ширину поровну (§12.3). */}
      <span style={{ fontSize: 11, fontFamily: 'var(--font-display)', fontWeight: 600, whiteSpace: 'nowrap' }}>
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
        borderRadius: 16,
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

export default function FeedNowStrip({ events, onUpgrade }) {
  const [openKey, setOpenKey] = useState(null);
  if (!events || events.length === 0) return null;

  // Копия перед сортировкой: массив приходит из состояния экрана, и sort
  // на месте перетасовал бы его там же.
  const chips = [...events].sort((a, b) => (a.duration_days || 0) - (b.duration_days || 0));
  const open = chips.find((e) => e.key === openKey) || null;

  return (
    <section style={{ padding: '12px 0 4px' }}>
      <h2
        style={{
          margin: '0 0 8px',
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.09em',
          textTransform: 'uppercase',
          fontFamily: 'var(--font-display)',
          color: 'var(--text-secondary)',
        }}
      >
        Сейчас
      </h2>

      <div style={{ display: 'flex', gap: 6 }}>
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
    </section>
  );
}
