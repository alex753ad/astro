/**
 * NatalChart — Professional natal chart wheel.
 * Redesign: «Дыхание космоса» — пастельная светлая тема.
 *
 * Изменения:
 * - Пастельные цвета секторов стихий (коралловый / оливковый / кремовый / голубой)
 * - Белая заливка внутреннего круга
 * - Белые подложки под планетами (r=12, fill="#FFFFFF")
 * - Тонкие пастельные границы кольца
 * - Светлый фон карты (#FDFBF9)
 */

import { useMemo } from 'react';

// ── Astrology data ─────────────────────────────────────────

const PLANET_GLYPHS = {
  Sun: '☉', Moon: '☽', Mercury: '☿', Venus: '♀', Mars: '♂',
  Jupiter: '♃', Saturn: '♄', Uranus: '♅', Neptune: '♆', Pluto: '♇',
  'North Node': '☊',
};

const PLANET_COLORS = {
  Sun:          '#D4840A',
  Moon:         '#7A8BA0',
  Mercury:      '#7060C0',
  Venus:        '#C04870',
  Mars:         '#B83030',
  Jupiter:      '#3868B0',
  Saturn:       '#6A6050',
  Uranus:       '#2090A8',
  Neptune:      '#6050B8',
  Pluto:        '#902020',
  'North Node': '#308858',
};

const SIGN_GLYPHS = ['♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓'];

// Element: 0=Fire, 1=Earth, 2=Air, 3=Water
// Пастельная тема «Дыхание космоса»
const ELEMENT_COLORS = {
  //          Огонь-коралл   Земля-олива    Воздух-крем    Вода-голубой
  fill:   ['#FCCFBE',      '#D4E8C8',     '#FAF0D0',     '#C8DCF0'],
  stroke: ['#D07050',      '#60905A',     '#C09040',     '#5080B0'],
  text:   ['#A04020',      '#3A6830',     '#806020',     '#2060A0'],
};
const SIGN_ELEMENT = [0,1,2,3, 0,1,2,3, 0,1,2,3];

const ASPECT_COLORS = {
  conjunction: '#C09020',
  sextile:     '#4070B0',
  trine:       '#4070B0',
  square:      '#B03030',
  opposition:  '#B03030',
};

const ROMAN = ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII'];

// ── Math helpers ──────────────────────────────────────────

function polarToXY(cx, cy, r, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) };
}

function lonToXY(cx, cy, r, longitude, ascLon = 0) {
  return polarToXY(cx, cy, r, 180 + (longitude - ascLon));
}

function sectorPath(cx, cy, rOuter, rInner, lon1, lon2, ascLon) {
  const a1 = 180 + (lon1 - ascLon);
  const a2 = 180 + (lon2 - ascLon);
  const p1 = polarToXY(cx, cy, rOuter, a1);
  const p2 = polarToXY(cx, cy, rOuter, a2);
  const p3 = polarToXY(cx, cy, rInner, a2);
  const p4 = polarToXY(cx, cy, rInner, a1);
  const large = Math.abs(lon2 - lon1) > 180 ? 1 : 0;
  return [
    `M ${p1.x} ${p1.y}`,
    `A ${rOuter} ${rOuter} 0 ${large} 1 ${p2.x} ${p2.y}`,
    `L ${p3.x} ${p3.y}`,
    `A ${rInner} ${rInner} 0 ${large} 0 ${p4.x} ${p4.y}`,
    'Z'
  ].join(' ');
}

function pushApart(positions, minGapDeg = 8) {
  const result = positions.map(p => ({ ...p }));
  for (let iter = 0; iter < 50; iter++) {
    let moved = false;
    for (let i = 0; i < result.length; i++) {
      for (let j = i + 1; j < result.length; j++) {
        let diff = result[j].displayLon - result[i].displayLon;
        while (diff >  180) diff -= 360;
        while (diff < -180) diff += 360;
        const absDiff = Math.abs(diff);
        if (absDiff < minGapDeg) {
          const push = (minGapDeg - absDiff) / 2 + 0.1;
          if (diff >= 0) { result[i].displayLon -= push; result[j].displayLon += push; }
          else           { result[i].displayLon += push; result[j].displayLon -= push; }
          moved = true;
        }
      }
    }
    if (!moved) break;
  }
  return result;
}

// ═══════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════

export default function NatalChart({
  planets = [], houses = [], aspects = [],
  ascendant, midheaven, timeUnknown, transitPlanets = [],
}) {
  const SIZE    = 560;
  const cx      = SIZE / 2;
  const cy      = SIZE / 2;
  const PADDING = transitPlanets.length > 0 ? 38 : 4;
  const VSIZE   = SIZE + PADDING * 2;

  const R_OUT     = SIZE / 2 - 4;
  const R_ZOD_OUT = R_OUT;
  const R_ZOD_IN  = R_OUT * 0.89;
  const R_ZOD_MID = (R_ZOD_OUT + R_ZOD_IN) / 2;

  const R_TICK_OUT = R_ZOD_IN;
  const R_TICK_IN  = R_ZOD_IN * 0.962;

  const R_PLANET   = R_OUT * 0.645;
  const R_HOUSE_IN = R_OUT * 0.56;
  const R_ASPECT   = R_OUT * 0.52;
  const R_NUM      = R_OUT * 0.665;
  const R_TRANSIT  = R_ZOD_OUT + 22;

  const SIGN_ORDER = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo',
                      'Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces'];

  const ascLon = ascendant?.longitude ?? 0;
  const mcLon  = midheaven?.longitude  ?? (ascLon + 90);

  const planetPositions = useMemo(() =>
    pushApart(planets.map(p => ({ ...p, displayLon: p.longitude }))),
  [planets]);

  const houseCusps = useMemo(() => {
    if (timeUnknown || houses.length === 0) return [];
    return houses.map(h => ({ number: h.number, lon: h.degree }));
  }, [houses, timeUnknown]);

  return (
    <svg
      viewBox={`${-PADDING} ${-PADDING} ${VSIZE} ${VSIZE}`}
      width="100%"
      height="100%"
      preserveAspectRatio="xMidYMid meet"
      style={{ display: 'block', maxWidth: 560, margin: '0 auto', background: 'transparent' }}
      aria-label="Натальная карта"
      role="img"
      fontFamily="'Segoe UI', system-ui, sans-serif"
    >
      {/* ── Основной фон карты (пастельный, не белый) ── */}
      <circle cx={cx} cy={cy} r={R_ZOD_OUT} fill="#FDFBF9" stroke="none" />

      {/* ── Полные сектора стихий от внешнего края до круга домов (прозрачный слой) ── */}
      {SIGN_GLYPHS.map((_, i) => {
        const el = SIGN_ELEMENT[i];
        return (
          <path
            key={`sector-full-${i}`}
            d={sectorPath(cx, cy, R_ZOD_OUT, R_HOUSE_IN, i * 30, (i + 1) * 30, ascLon)}
            fill={ELEMENT_COLORS.fill[el]}
            stroke="none"
            opacity={0.30}
          />
        );
      })}

      {/* ── Пастельные сектора зодиакального кольца (непрозрачные) ── */}
      {SIGN_GLYPHS.map((glyph, i) => {
        const el     = SIGN_ELEMENT[i];
        const midLon = i * 30 + 15;
        const midPos = lonToXY(cx, cy, R_ZOD_MID, midLon, ascLon);
        return (
          <g key={`sign-${i}`}>
            <path
              d={sectorPath(cx, cy, R_ZOD_OUT, R_ZOD_IN, i * 30, (i + 1) * 30, ascLon)}
              fill={ELEMENT_COLORS.fill[el]}
              stroke="none"
              opacity={1}
            />
            <text
              x={midPos.x} y={midPos.y}
              textAnchor="middle" dominantBaseline="central"
              fontSize={11} fontWeight="600"
              fill={ELEMENT_COLORS.text[el]}
            >
              {glyph}
            </text>
          </g>
        );
      })}

      {/* ── Радиальные линии-разделители знаков ── */}
      {Array.from({ length: 12 }, (_, i) => {
        const p1 = lonToXY(cx, cy, R_ZOD_OUT, i * 30, ascLon);
        const p2 = lonToXY(cx, cy, R_ZOD_IN,  i * 30, ascLon);
        return (
          <line key={`zdiv-${i}`}
            x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
            stroke="#C8B8A8" strokeWidth={0.75}
          />
        );
      })}

      {/* ── Внешняя и внутренняя границы зодиакального кольца ── */}
      <circle cx={cx} cy={cy} r={R_ZOD_OUT} fill="none" stroke="#D0C0B0" strokeWidth={1.5} />
      <circle cx={cx} cy={cy} r={R_ZOD_IN}  fill="none" stroke="#C8B8A8" strokeWidth={1} />

      {/* ── Шкала градусов ── */}
      {Array.from({ length: 360 }, (_, deg) => {
        const isTen  = deg % 10 === 0;
        const isFive = !isTen && deg % 5 === 0;
        const tickLen = isTen ? R_ZOD_IN * 0.052 : isFive ? R_ZOD_IN * 0.033 : R_ZOD_IN * 0.016;
        const svgDeg  = 180 + (deg - ascLon);
        const p1 = polarToXY(cx, cy, R_TICK_OUT,           svgDeg);
        const p2 = polarToXY(cx, cy, R_TICK_OUT - tickLen, svgDeg);
        return (
          <line
            key={`tick-${deg}`}
            x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
            stroke={isTen ? '#A09080' : '#C8B8A8'}
            strokeWidth={isTen ? 0.9 : isFive ? 0.65 : 0.35}
          />
        );
      })}

      {/* ── Граница шкалы градусов ── */}
      <circle cx={cx} cy={cy} r={R_TICK_IN} fill="#FDFBF9" stroke="#D0C4B8" strokeWidth={0.5} />

      {/* ── Линии домов (от внутреннего круга до внешнего края зодиака) ── */}
      {!timeUnknown && houseCusps.length === 12 && houseCusps.map((house, i) => {
        const nextHouse = houseCusps[(i + 1) % 12];
        let lon1 = house.lon;
        let lon2 = nextHouse.lon;
        if (lon2 <= lon1) lon2 += 360;

        const isAngular = [1, 4, 7, 10].includes(house.number);
        const midLon = lon1 + (lon2 - lon1) / 2;
        const numPos = lonToXY(cx, cy, R_NUM, midLon, ascLon);
        const p1 = lonToXY(cx, cy, R_HOUSE_IN, house.lon, ascLon);
        const p2 = lonToXY(cx, cy, R_ZOD_OUT,  house.lon, ascLon);

        return (
          <g key={`house-${house.number}`}>
            <line
              x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
              stroke={isAngular ? '#9070C0' : '#C0B0A0'}
              strokeWidth={isAngular ? 1.5 : 0.75}
            />
            <text
              x={numPos.x} y={numPos.y}
              textAnchor="middle" dominantBaseline="central"
              fontSize={8.5} fill="#A090C0" fontStyle="italic"
            >
              {ROMAN[house.number - 1]}
            </text>
          </g>
        );
      })}

      {/* ── Внутренний круг (область аспектов) — белая заливка ── */}
      <circle cx={cx} cy={cy} r={R_HOUSE_IN} fill="#FFFFFF" stroke="#D8C8E0" strokeWidth={0.75} />

      {/* ── Линии аспектов ── */}
      {aspects
        .filter(asp => ['conjunction','sextile','trine','square','opposition'].includes(asp.aspect_type))
        .map((asp, i) => {
          const p1 = planets.find(p => p.name === asp.planet1);
          const p2 = planets.find(p => p.name === asp.planet2);
          if (!p1 || !p2) return null;
          const pt1     = lonToXY(cx, cy, R_ASPECT, p1.longitude, ascLon);
          const pt2     = lonToXY(cx, cy, R_ASPECT, p2.longitude, ascLon);
          const color   = ASPECT_COLORS[asp.aspect_type];
          const isHarm  = asp.aspect_type === 'trine' || asp.aspect_type === 'sextile';
          const opacity = isHarm ? 0.45 : asp.aspect_type === 'conjunction' ? 0.65 : 0.55;
          return (
            <line
              key={i}
              x1={pt1.x} y1={pt1.y} x2={pt2.x} y2={pt2.y}
              stroke={color}
              strokeWidth={asp.orb < 1 ? 1.5 : asp.orb < 3 ? 1.0 : 0.6}
              strokeOpacity={opacity}
              strokeDasharray={!asp.applying ? '4 3' : 'none'}
            />
          );
        })}

      {/* ── Центральная точка ── */}
      <circle cx={cx} cy={cy} r={2.5} fill="#C0A8D8" />

      {/* ── Планеты ── */}
      {planetPositions.map((planet) => {
        const glyphPos = lonToXY(cx, cy, R_PLANET, planet.displayLon, ascLon);
        const realPos  = lonToXY(cx, cy, R_TICK_IN - 4, planet.longitude, ascLon);
        const color    = PLANET_COLORS[planet.name] || '#606060';
        const showLine = Math.abs(planet.displayLon - planet.longitude) > 2;

        return (
          <g key={planet.name}>
            {/* Тик на шкале градусов */}
            {(() => {
              const t1 = lonToXY(cx, cy, R_TICK_IN + 1, planet.longitude, ascLon);
              const t2 = lonToXY(cx, cy, R_TICK_IN - 5, planet.longitude, ascLon);
              return <line x1={t1.x} y1={t1.y} x2={t2.x} y2={t2.y} stroke={color} strokeWidth={1.5} />;
            })()}

            {showLine && (
              <line
                x1={realPos.x} y1={realPos.y}
                x2={glyphPos.x} y2={glyphPos.y}
                stroke={color} strokeWidth={0.5} strokeOpacity={0.35}
              />
            )}

            {/* Белая подложка под планетой — выделяется поверх линий аспектов */}
            <circle cx={glyphPos.x} cy={glyphPos.y} r={12} fill="#FFFFFF" />

            {/* Цветной обод планеты */}
            <circle cx={glyphPos.x} cy={glyphPos.y} r={12}
              fill="none" stroke={color} strokeWidth={0.75} />

            <text
              x={glyphPos.x} y={glyphPos.y}
              textAnchor="middle" dominantBaseline="central"
              fontSize={12} fontWeight="600" fill={color}
            >
              {PLANET_GLYPHS[planet.name] || '?'}
            </text>

            {/* Градус */}
            {(() => {
              const degPos = lonToXY(cx, cy, R_PLANET - 16, planet.displayLon, ascLon);
              return (
                <text x={degPos.x} y={degPos.y}
                  textAnchor="middle" dominantBaseline="central"
                  fontSize={7} fill={color} opacity={0.75}
                >
                  {Math.floor(planet.degree_in_sign)}°
                </text>
              );
            })()}

            {planet.retrograde && (
              <text x={glyphPos.x + 9} y={glyphPos.y - 8}
                fontSize={8} fill="#C04040" fontWeight="700">℞</text>
            )}
          </g>
        );
      })}

      {/* ── Метки ASC / DSC / MC / IC снаружи кольца ── */}
      {!timeUnknown && ascendant && (
        <>
          {[
            { lon: ascLon,                label: 'Asc', color: '#8040A0' },
            { lon: (ascLon + 180) % 360,  label: 'Dsc', color: '#8040A0' },
            ...(midheaven ? [
              { lon: mcLon,               label: 'MC',  color: '#3060A0' },
              { lon: (mcLon + 180) % 360, label: 'IC',  color: '#3060A0' },
            ] : []),
          ].map(({ lon, label, color }) => {
            const pos = lonToXY(cx, cy, R_ZOD_OUT + 14, lon, ascLon);
            return (
              <text key={label} x={pos.x} y={pos.y}
                textAnchor="middle" dominantBaseline="central"
                fontSize={9} fontWeight="700" fill={color}>
                {label}
              </text>
            );
          })}
        </>
      )}

      {/* ── Время неизвестно ── */}
      {timeUnknown && (
        <text x={cx} y={cy + R_HOUSE_IN - 20} textAnchor="middle"
          fontSize={10} fill="#B0A0C0" fontStyle="italic">
          Время неизвестно — дома не показаны
        </text>
      )}

      {/* ── Транзитное внешнее кольцо ── */}
      {transitPlanets.length > 0 && (() => {
        const withLon = transitPlanets.map(tp => ({
          ...tp,
          longitude: (tp.longitude != null && tp.longitude !== 0)
            ? tp.longitude
            : (SIGN_ORDER.indexOf(tp.transit_sign) * 30 + 15),
        }));
        const spread = pushApart(withLon.map(p => ({ ...p, displayLon: p.longitude })));

        return (
          <g>
            {/* Внешнее кольцо транзитов — светлое */}
            <circle cx={cx} cy={cy} r={R_TRANSIT + 16}
              fill="rgba(253,251,249,0.80)"
              stroke="rgba(224,195,252,0.50)"
              strokeWidth={1} strokeDasharray="3 3" />

            {/* Линии аспектов транзит → натал */}
            {spread.map((tp, i) => {
              if (!tp.aspect_type || !tp.natal_planet) return null;
              const natalPlanet = planets.find(p => p.name === tp.natal_planet);
              if (!natalPlanet) return null;
              const ptTransit = lonToXY(cx, cy, R_TRANSIT, tp.displayLon, ascLon);
              const ptNatal   = lonToXY(cx, cy, R_ASPECT,  natalPlanet.longitude, ascLon);
              const color     = ASPECT_COLORS[tp.aspect_type] || '#A898CC';
              return (
                <line key={`tl-${i}`}
                  x1={ptTransit.x} y1={ptTransit.y}
                  x2={ptNatal.x}   y2={ptNatal.y}
                  stroke={color} strokeWidth={1} strokeOpacity={0.45}
                  strokeDasharray="4 3"
                />
              );
            })}

            {/* Транзитные планеты */}
            {spread.map((tp, i) => {
              const pos       = lonToXY(cx, cy, R_TRANSIT, tp.displayLon, ascLon);
              const color     = PLANET_COLORS[tp.name] || '#A070C0';
              const hasAspect = !!tp.aspect_type;
              return (
                <g key={`tg-${i}`}>
                  {(() => {
                    const inner = lonToXY(cx, cy, R_ZOD_OUT, tp.longitude, ascLon);
                    return <line x1={inner.x} y1={inner.y} x2={pos.x} y2={pos.y}
                      stroke={color} strokeWidth={0.5} strokeOpacity={0.25} />;
                  })()}

                  {/* Белая подложка транзитной планеты */}
                  <circle cx={pos.x} cy={pos.y} r={12} fill="#FFFFFF" />
                  <circle cx={pos.x} cy={pos.y} r={12}
                    fill="none"
                    stroke={color}
                    strokeWidth={hasAspect ? 2 : 1}
                    strokeOpacity={1}
                  />
                  <text x={pos.x} y={pos.y}
                    textAnchor="middle" dominantBaseline="central"
                    fontSize={13} fontWeight="700"
                    fill={color}>
                    {PLANET_GLYPHS[tp.name] || '?'}
                  </text>

                  {tp.retrograde && (
                    <text x={pos.x + 10} y={pos.y - 9}
                      fontSize={8} fill="#C04040" fontWeight="700">℞</text>
                  )}
                </g>
              );
            })}
          </g>
        );
      })()}
    </svg>
  );
}
