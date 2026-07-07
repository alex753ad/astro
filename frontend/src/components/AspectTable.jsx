import React from 'react';

const ASPECT_SYMBOLS = {
  conjunction: '☌',
  sextile: '⚹',
  square: '□',
  trine: '△',
  opposition: '☍',
};

const ASPECT_NAMES_RU = {
  conjunction: 'Соединение',
  sextile: 'Секстиль',
  square: 'Квадрат',
  trine: 'Трин',
  opposition: 'Оппозиция',
};

const ASPECT_COLORS = {
  conjunction: 'text-yellow-400',
  sextile: 'text-blue-400',
  trine: 'text-blue-400',
  square: 'text-red-400',
  opposition: 'text-red-400',
};

// ── F4: Индикатор важности ────────────────────────────────

const PERSONAL_PLANETS = new Set(['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Ascendant', 'Midheaven', 'ASC', 'MC']);
const CORE_PLANETS     = new Set(['Sun', 'Moon', 'Ascendant', 'Midheaven', 'ASC', 'MC']);

function calcImportance(aspect) {
  const orb     = Math.abs(aspect.orb ?? 0);
  const planets = new Set([aspect.planet1, aspect.planet2]);
  const hasCore     = [...planets].some(p => CORE_PLANETS.has(p));
  const hasPersonal = [...planets].some(p => PERSONAL_PLANETS.has(p));

  if (orb < 2 && hasCore)     return 'high';
  if (orb < 5 && hasPersonal) return 'medium';
  return 'low';
}

const IMPORTANCE_BADGE = {
  high:   { label: 'Влиятельный', color: 'var(--at-high)', bg: 'rgba(124,58,237,0.08)', border: 'rgba(124,58,237,0.25)' },
  medium: { label: 'Обычный',     color: 'var(--at-med)', bg: 'rgba(37,99,235,0.08)',  border: 'rgba(37,99,235,0.2)'  },
  low:    { label: 'Минорный',    color: 'var(--at-low)', bg: 'rgba(107,114,128,0.06)', border: 'rgba(107,114,128,0.15)' },
};

function ImportanceBadge({ aspect }) {
  const level = calcImportance(aspect);
  const { label, color, bg, border } = IMPORTANCE_BADGE[level];
  return (
    <span style={{
      fontSize: 10, fontWeight: 600,
      padding: '2px 7px', borderRadius: 8,
      color, background: bg,
      border: `1px solid ${border}`,
      whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  );
}

const PLANET_GLYPHS = {
  Sun: '☉', Moon: '☽', Mercury: '☿', Venus: '♀', Mars: '♂',
  Jupiter: '♃', Saturn: '♄', Uranus: '♅', Neptune: '♆', Pluto: '♇',
  'North Node': '☊', Chiron: '⚷', Lilith: '⚸',
  Ascendant: 'AC', Midheaven: 'MC',
};

/**
 * Table of aspects between planets with importance indicator (F4).
 */
export default function AspectTable({ aspects }) {
  if (!aspects?.length) return null;

  const importanceOrder = { high: 0, medium: 1, low: 2 };
  const sorted = [...aspects].sort((a, b) => {
    const diff = importanceOrder[calcImportance(a)] - importanceOrder[calcImportance(b)];
    return diff !== 0 ? diff : (a.orb ?? 0) - (b.orb ?? 0);
  });

  return (
    <div className="p-6 at-scope">
      <style>{`.at-scope{--at-high:#7C3AED;--at-med:#2563EB;--at-low:#6B7280;} .dark .at-scope{--at-high:#A78BFA;--at-med:#6FA8DC;--at-low:#9B97B0;}`}</style>
      <h2 className="font-display text-lg font-bold mb-4 flex items-center gap-2">
        <span className="text-brand-accent">△</span>
        Аспекты
      </h2>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-brand-muted text-left border-b border-brand-accent/10">
              <th className="pb-2 pr-4">Планеты</th>
              <th className="pb-2 pr-4">Орб</th>
              <th className="pb-2">Важность</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((a, i) => {
              const aspColor = ASPECT_COLORS[a.aspect_type] || 'text-brand-muted';
              const g1 = PLANET_GLYPHS[a.planet1] || a.planet1.slice(0, 2);
              const g2 = PLANET_GLYPHS[a.planet2] || a.planet2.slice(0, 2);
              const aspSym = ASPECT_SYMBOLS[a.aspect_type] || '?';
              return (
                <tr key={i} className="border-b border-brand-accent/5 hover:bg-brand-accent/5 transition-colors">
                  <td className="py-2 pr-4">
                    <span
                      title={a.planet1}
                      style={{ fontSize: 17, lineHeight: 1, verticalAlign: 'middle' }}
                      className="text-brand-primary"
                    >
                      {g1}
                    </span>
                    <span
                      className={`mx-2 ${aspColor}`}
                      title={ASPECT_NAMES_RU[a.aspect_type]}
                      style={{ fontSize: 15, verticalAlign: 'middle' }}
                    >
                      {aspSym}
                    </span>
                    <span
                      title={a.planet2}
                      style={{ fontSize: 17, lineHeight: 1, verticalAlign: 'middle' }}
                      className="text-brand-primary"
                    >
                      {g2}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-brand-muted text-xs">
                    {a.orb?.toFixed(1)}°
                  </td>
                  <td className="py-2">
                    <ImportanceBadge aspect={a} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
