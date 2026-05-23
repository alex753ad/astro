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

/**
 * Table of aspects between planets.
 */
export default function AspectTable({ aspects }) {
  if (!aspects?.length) return null;

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
              <th className="pb-2">Тип</th>
            </tr>
          </thead>
          <tbody>
            {aspects.map((a, i) => (
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
                <td className="py-1.5 text-brand-muted text-xs">
                  {a.applying ? 'применяющийся' : 'разделяющийся'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
