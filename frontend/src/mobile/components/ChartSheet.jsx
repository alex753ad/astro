/**
 * ChartSheet.jsx — шторка снизу экрана «Карта» (§5 спецификации).
 *
 * Три вкладки переключателем: Планеты, Дома, Аспекты. Высота
 * фиксированная (≈45% экрана), тянуть пальцем нельзя — это отдельная
 * работа, и без неё экран полон: список внутри прокручивается сам.
 *
 * ⚠️ Собственный `overflow` у списка здесь безопасен, в отличие от ленты:
 * на экране «Карта» нет `position: sticky`, ломать нечего. В FeedScreen
 * то же самое было бы дефектом (см. FeedDayHeader.jsx).
 */

import React, { useRef, useState } from 'react';
import PullIndicator from './PullIndicator';
import usePullToRefresh from '../lib/usePullToRefresh';
import { aspectColor, aspectSymbol, glyph, glyphStyle } from '../lib/feedGlyphs';
import {
  aspectRu, degreeInSign, isNodePair, planetRu, romanHouse, signRu, toDMS,
} from '../lib/chartFormat';

const TABS = [
  { key: 'planets', label: 'Планеты' },
  { key: 'houses', label: 'Дома' },
  { key: 'aspects', label: 'Аспекты' },
];

const rowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  padding: '9px 0',
  borderBottom: '1px solid var(--border)',
  fontSize: 14,
  color: 'var(--text-primary)',
};

const secondary = { fontSize: 13, color: 'var(--text-secondary)' };

// Общая ширина первой колонки вкладки «Дома» — у Asc/MC и у самих домов
// разная длина метки («MC» и «VII дом»), но колонка обязана быть одна:
// без общей ширины знак у Asc/MC начинается сразу за меткой, а у домов —
// с отступом (ширина «VII дом» их раздвигает), и получаются три вертикали
// вместо одной. 66 — по самой длинной метке дома, взято из её же строки.
const HOUSE_LABEL_WIDTH = 66;

// Градус — моноширинными цифрами и всегда справа: колонка из
// «24° 04′ 12″» и «5° 35′ 01″» иначе пляшет по ширине.
const degreeStyle = {
  marginLeft: 'auto',
  flexShrink: 0,
  fontFamily: 'var(--font-body)',
  fontVariantNumeric: 'tabular-nums',
  fontSize: 13,
  color: 'var(--text-secondary)',
};

function PlanetRow({ planet }) {
  return (
    <div style={rowStyle}>
      <span style={{ ...glyphStyle, fontSize: 17, width: 20, textAlign: 'center', flexShrink: 0 }}>
        {glyph(planet.name)}
      </span>
      <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {planetRu(planet.name)}
      </span>
      <span style={{ ...secondary, flexShrink: 0 }}>{signRu(planet.sign)}</span>
      {planet.retrograde && (
        <span
          title="Ретроградная"
          style={{
            flexShrink: 0,
            fontSize: 11,
            fontWeight: 700,
            color: 'var(--color-danger)',
            fontFamily: 'var(--font-body)',
          }}
        >
          R
        </span>
      )}
      <span style={degreeStyle}>{toDMS(planet.degree_in_sign)}</span>
    </div>
  );
}

/**
 * Углы идут первыми строками вкладки «Дома», до самих домов: Asc и MC —
 * то, что человек ищет в этой таблице чаще всего. Dsc и IC не
 * показываются (§5): они зеркальны и в колесе подписаны все четыре.
 */
function AngleRow({ label, angle }) {
  if (!angle) return null;
  return (
    <div style={rowStyle}>
      <span style={{ width: HOUSE_LABEL_WIDTH, flexShrink: 0, fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 12, color: 'var(--accent)' }}>
        {label}
      </span>
      <span style={{ ...secondary }}>{signRu(angle.sign)}</span>
      <span style={degreeStyle}>{toDMS(angle.degree)}</span>
    </div>
  );
}

export default function ChartSheet({ chart, onRefresh }) {
  const [tab, setTab] = useState('planets');

  // ⚠️ Жест обновления живёт ЗДЕСЬ, а не в ChartScreen.jsx, хотя обновляет
  // весь экран. Причина в раскладке: у «Карты» собственной прокрутки нет
  // вовсе — колесо и шторка делят высоту, а прокручивается только этот
  // список. Тянуть можно лишь то, что скроллится, поэтому слушатели
  // вешаются на его узел, а экран передаёт сюда готовый обработчик.
  // Обратный путь (отдать ref наружу через forwardRef) дал бы то же самое,
  // но лишним звеном.
  const listRef = useRef(null);
  const pull = usePullToRefresh(listRef, onRefresh, Boolean(onRefresh));
  const planets = chart?.planets || [];
  const houses = chart?.houses || [];
  const aspects = (chart?.aspects || []).filter((a) => !isNodePair(a));

  return (
    <section
      style={{
        flexShrink: 0,
        height: '45%',
        minHeight: 220,
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--bg-card)',
        borderTop: '1px solid var(--border)',
        borderTopLeftRadius: 24,
        borderTopRightRadius: 24,
        padding: '8px 16px 0',
      }}
    >
      {/* «Ручка» из прототипа — она же граница касания: показывает, что
          панель отдельная от колеса, даже пока её нельзя тянуть. */}
      <span
        aria-hidden="true"
        style={{
          width: 36,
          height: 4,
          borderRadius: 2,
          background: 'var(--border)',
          alignSelf: 'center',
          marginBottom: 10,
          flexShrink: 0,
        }}
      />

      <div style={{ display: 'flex', gap: 6, flexShrink: 0, marginBottom: 6 }}>
        {TABS.map((t) => {
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              aria-pressed={active}
              style={{
                flex: 1,
                padding: '8px 0',
                borderRadius: 'var(--radius-md)',
                border: 'none',
                background: active ? 'var(--accent-muted)' : 'transparent',
                color: active ? 'var(--accent)' : 'var(--text-secondary)',
                fontFamily: 'var(--font-body)',
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {/* paddingBottom: 88, не 12 — запас под кнопку чата (AristeaFab.jsx,
          52px + 16px отступ + немного воздуха): она всегда показана вместе
          с этим экраном (§5 SPEC_CHART_SCREEN.md), сидит поверх правого
          нижнего угла именно этого списка. Клиренс — здесь, внутри
          собственного скролла шторки, а не общим отступом в TabShell.jsx:
          тот сжал бы всю композицию «колесо + шторка» разом и утопил
          подсказку под колесом (регресс 06.09.2026, см. TabShell.jsx). */}
      <PullIndicator state={pull.state} ready={pull.ready} innerRef={pull.indicatorRef} />

      <div ref={listRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', paddingBottom: 88 }}>
        {tab === 'planets' && planets.map((p) => <PlanetRow key={p.name} planet={p} />)}

        {tab === 'houses' && (
          <>
            <AngleRow label="Asc" angle={chart?.ascendant} />
            <AngleRow label="MC" angle={chart?.midheaven} />
            {houses.map((h) => (
              <div key={h.number} style={rowStyle}>
                {/* Римскими, как дома подписаны в самом колесе — список и
                    колесо читаются одинаково. Арабской цифры рядом нет: это
                    было бы одно и то же число дважды. */}
                <span style={{ width: HOUSE_LABEL_WIDTH, flexShrink: 0, whiteSpace: 'nowrap', fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>
                  {romanHouse(h.number)} дом
                </span>
                <span style={{ ...secondary, flexShrink: 0 }}>{signRu(h.sign)}</span>
                {/* degree у дома — абсолютная долгота, внутрь знака её
                    переводит degreeInSign (см. chartFormat.js). */}
                <span style={degreeStyle}>{toDMS(degreeInSign(h.degree))}</span>
              </div>
            ))}
          </>
        )}

        {tab === 'aspects' && aspects.map((a) => (
          <div key={`${a.planet1}-${a.planet2}-${a.aspect_type}`} style={rowStyle}>
            <span style={{ ...glyphStyle, fontSize: 15, flexShrink: 0 }}>{glyph(a.planet1)}</span>
            <span style={{ ...glyphStyle, fontSize: 15, flexShrink: 0, color: aspectColor(a.aspect_type) }}>
              {aspectSymbol(a.aspect_type)}
            </span>
            <span style={{ ...glyphStyle, fontSize: 15, flexShrink: 0 }}>{glyph(a.planet2)}</span>
            <span
              style={{
                ...secondary,
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {planetRu(a.planet1)} — {planetRu(a.planet2)}, {aspectRu(a.aspect_type)}
            </span>
            <span style={degreeStyle}>{a.orb.toFixed(1)}°</span>
          </div>
        ))}
      </div>
    </section>
  );
}
