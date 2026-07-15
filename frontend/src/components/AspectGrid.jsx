/**
 * AspectGrid.jsx — треугольная матрица аспектов
 */
import React from 'react';

const PLANET_ORDER = [
  'Sun','Moon','Mercury','Venus','Mars','Jupiter',
  'Saturn','Uranus','Neptune','Pluto','Chiron','Lilith',
  'North Node','Ascendant','Midheaven',
];

const GLYPHS = {
  Sun:'☉', Moon:'☽', Mercury:'☿', Venus:'♀', Mars:'♂',
  Jupiter:'♃', Saturn:'♄', Uranus:'♅', Neptune:'♆', Pluto:'♇',
  'North Node':'☊', Chiron:'⚷', Lilith:'⚸',
  Ascendant:'AC', Midheaven:'MC',
};

const ASPECT_SYMBOL = {
  conjunction:'☌', sextile:'⚹', square:'□',
  trine:'△', opposition:'☍', quincunx:'⑁',
};

const PLANET_RU = {
  Sun:'Солнце', Moon:'Луна', Mercury:'Меркурий', Venus:'Венера', Mars:'Марс',
  Jupiter:'Юпитер', Saturn:'Сатурн', Uranus:'Уран', Neptune:'Нептун', Pluto:'Плутон',
  'North Node':'Северный узел', Chiron:'Хирон', Lilith:'Лилит',
  Ascendant:'Асцендент', Midheaven:'MC',
};

const ASPECT_RU = {
  conjunction:'соединение', sextile:'секстиль', square:'квадрат',
  trine:'трин', opposition:'оппозиция', quincunx:'квинконс',
};

const ASPECT_COLOR = {
  conjunction: '#d4a843',
  sextile:     '#4a9de0',
  trine:       '#4ec98a',
  square:      '#d94f4f',
  opposition:  '#c84080',
  quincunx:    '#a06cc8',
};

export default function AspectGrid({ aspects = [], planets = [] }) {
  // determine which planets actually appear in the chart
  const present = new Set(planets.map(p => p.name));
  const order = PLANET_ORDER.filter(n => present.has(n) || n === 'Ascendant' || n === 'Midheaven');

  // build aspect lookup  { "Sun|Moon": { type, orb } }
  const lookup = {};
  aspects.forEach(a => {
    const key1 = `${a.planet1}|${a.planet2}`;
    const key2 = `${a.planet2}|${a.planet1}`;
    const val = { type: a.aspect_type, orb: a.orb };
    lookup[key1] = val;
    lookup[key2] = val;
  });

  const n = order.length;
  const CELL = 26; // px

  return (
    <div style={s.wrap}>
      <div style={s.label}>Матрица аспектов</div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', tableLayout: 'fixed' }}>
          <tbody>
            {order.map((rowPlanet, i) => (
              <tr key={rowPlanet}>
                {order.slice(0, i + 1).map((colPlanet, j) => {
                  const isDiag = i === j;
                  const asp = isDiag ? null : lookup[`${rowPlanet}|${colPlanet}`];
                  return (
                    <td
                      key={colPlanet}
                      title={asp ? `${PLANET_RU[rowPlanet] || rowPlanet} ${ASPECT_RU[asp.type] || asp.type} ${PLANET_RU[colPlanet] || colPlanet} (орб ${asp.orb?.toFixed(1)}°)` : (isDiag ? (PLANET_RU[rowPlanet] || rowPlanet) : '')}
                      style={{
                        width: CELL, height: CELL,
                        border: '0.5px solid rgba(139,143,163,0.25)',
                        textAlign: 'center',
                        verticalAlign: 'middle',
                        background: isDiag ? 'var(--color-background-tertiary)' : 'transparent',
                        fontSize: isDiag ? '11px' : '13px',
                        fontWeight: isDiag ? '600' : '400',
                        color: isDiag
                          ? 'var(--color-text-secondary)'
                          : asp ? ASPECT_COLOR[asp.type] : 'transparent',
                        cursor: asp ? 'default' : 'default',
                        userSelect: 'none',
                        padding: 0,
                        lineHeight: 1,
                      }}
                    >
                      {isDiag
                        ? (GLYPHS[rowPlanet] || rowPlanet.slice(0, 2))
                        : (asp ? (ASPECT_SYMBOL[asp.type] || asp.type[0]) : '')}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const s = {
  wrap: {
    display: 'inline-block',
  },
  label: {
    fontSize: '11px',
    fontWeight: '500',
    letterSpacing: '0.07em',
    textTransform: 'uppercase',
    color: 'var(--color-text-tertiary)',
    marginBottom: '10px',
  },
};
