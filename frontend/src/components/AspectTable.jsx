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
  high:   { label: 'Влиятельный', color: '#7C3AED', bg: 'rgba(124,58,237,0.08)', border: 'rgba(124,58,237,0.25)' },
  medium: { label: 'Обычный',     color: '#2563EB', bg: 'rgba(37,99,235,0.08)',  border: 'rgba(37,99,235,0.2)'  },
  low:    { label: 'Минорный',    color: '#6B7280', bg: 'rgba(107,114,128,0.06)', border: 'rgba(107,114,128,0.15)' },
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

/**
 * Table of aspects between planets with importance indicator (F4).
 */
export default function AspectTable({ aspects }) {
  if (!aspects?.length) return null;

  // Sort: high first, then medium, then low, then by orb
  const importanceOrder = { high: 0, medium: 1, low: 2 };
  const sorted = [...aspects].sort((a, b) => {
    const diff = importanceOrder[calcImportance(a)] - importanceOrder[calcImportance(b)];
    return diff !== 0 ? diff : (a.orb ?? 0) - (b.orb ?? 0);
  });

  return (
    <div className="glass-card p-6">
      <h2 className="font-display text-lg font-bold mb-4 flex items-center gap-2">
        <span className="text-brand-accent">△</span>
        Аспекты
      </h2>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-brand-muted text-left border-b border-brand-accent/10">
              <th className="pb-2 pr-3">Планеты</th>
              <th className="pb-2 pr-3">Аспект</th>
              <th className="pb-2 pr-3">Орб</th>
              <th className="pb-2 pr-3">Тип</th>
              <th className="pb-2">Важность</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((a, i) => (
              <tr key={i} className="border-b border-brand-accent/5 hover:bg-brand-accent/5 transition-colors">
                <td className="py-1.5 pr-3">
                  {a.planet1} — {a.planet2}
                </td>
                <td className={`py-1.5 pr-3 ${ASPECT_COLORS[a.aspect_type]}`}>
                  <span className="mr-1">{ASPECT_SYMBOLS[a.aspect_type]}</span>
                  {ASPECT_NAMES_RU[a.aspect_type]}
                </td>
                <td className="py-1.5 pr-3 text-brand-muted">
                  {a.orb?.toFixed(1)}°
                </td>
                <td className="py-1.5 pr-3 text-brand-muted text-xs">
                  {a.applying ? 'применяющийся' : 'разделяющийся'}
                </td>
                <td className="py-1.5">
                  <ImportanceBadge aspect={a} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
