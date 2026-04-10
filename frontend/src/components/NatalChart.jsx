/**
 * NatalChart — Professional natal chart wheel.
 *
 * Changes v2:
 * 1. House cusp lines extend all the way through zodiac to outer edge
 * 2. Zodiac ring width reduced by 50% (thinner band, same outer radius)
 * 3. Degree tick scale added inside zodiac ring (1°, 5°, 10° ticks)
 */

import { useMemo } from 'react';

// ── Astrology data ────────────────────────────────────────

const PLANET_GLYPHS = {
  Sun: '☉', Moon: '☽', Mercury: '☿', Venus: '♀', Mars: '♂',
  Jupiter: '♃', Saturn: '♄', Uranus: '♅', Neptune: '♆', Pluto: '♇',
  'North Node': '☊',
};

const PLANET_COLORS = {
  Sun: '#E8A020', Moon: '#9BA8B8', Mercury: '#8B7EC8',
  Venus: '#D4607A', Mars: '#C84040', Jupiter: '#4878C0',
  Saturn: '#7A7060', Uranus: '#30A8B8', Neptune: '#7060C0',
  Pluto: '#A02828', 'North Node': '#40A870',
};

const SIGN_GLYPHS = ['♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓'];

// Element: 0=Fire, 1=Earth, 2=Air, 3=Water
const ELEMENT_COLORS = {
  fill:   ['#F8D8D0','#D0E8D0','#F8EDD0','#C8DCF0'],
  stroke: ['#C06040','#407850','#A08030','#3060A0'],
  text:   ['#903020','#306030','#806020','#204880'],
};
const SIGN_ELEMENT = [0,1,2,3, 0,1,2,3, 0,1,2,3];

const ASPECT_COLORS = {
  conjunction: '#D4A020',
  sextile:     '#2060B0',
  trine:       '#2060B0',
  square:      '#B02020',
  opposition:  '#B02020',
};

const ROMAN = ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII'];

// ── Math helpers ──────────────────────────────────────────
// ASC at 9 o'clock (180°). Longitude increases CCW on screen.
// SVG angle = 180 + (longitude - ascLon)

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
        while (diff > 180) diff -= 360;
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

export default function NatalChart({ planets = [], houses = [], aspects = [], ascendant, midheaven, timeUnknown, transitPlanets = [] }) {
  const SIZE = 560;
  const cx = SIZE / 2;
  const cy = SIZE / 2;
  // Extra padding for transit outer ring (38px on each side)
  const PADDING = transitPlanets.length > 0 ? 38 : 4;
  const VSIZE = SIZE + PADDING * 2;

  const R_OUT      = SIZE / 2 - 4;   // outer chart edge

  // Zodiac ring: original width ≈ 22% of R_OUT (R_ZOD_IN was 0.78).
  // Reduced by 50% → new width ≈ 11% → R_ZOD_IN = 0.89
  const R_ZOD_OUT  = R_OUT;          // zodiac outer edge (unchanged)
  const R_ZOD_IN   = R_OUT * 0.89;   // zodiac inner edge (thinner ring)
  const R_ZOD_MID  = (R_ZOD_OUT + R_ZOD_IN) / 2; // glyph midpoint

  // Degree tick scale band just inside the zodiac ring
  const R_TICK_OUT = R_ZOD_IN;
  const R_TICK_IN  = R_ZOD_IN * 0.962; // ~3.8% band for ticks

  // Rings inside tick scale
  const R_PLANET   = R_OUT * 0.645;
  const R_HOUSE_IN = R_OUT * 0.56;
  const R_ASPECT   = R_OUT * 0.52;
  const R_NUM      = R_OUT * 0.665;

  // Transit outer ring (outside zodiac)
  const R_TRANSIT  = R_ZOD_OUT + 22;

  const SIGN_ORDER = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo',
                      'Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces'];

  const ascLon = ascendant?.longitude ?? 0;
  const mcLon  = midheaven?.longitude  ?? (ascLon + 90);

  const planetPositions = useMemo(() => {
    return pushApart(planets.map(p => ({ ...p, displayLon: p.longitude })));
  }, [planets]);

  const houseCusps = useMemo(() => {
    if (timeUnknown || houses.length === 0) return [];
    return houses.map(h => ({ number: h.number, lon: h.degree }));
  }, [houses, timeUnknown]);

  return (
    <svg
      viewBox={`${-PADDING} ${-PADDING} ${VSIZE} ${VSIZE}`}
      width="100%"
      style={{ display: 'block', maxWidth: 560, margin: '0 auto', background: 'transparent' }}
      aria-label="Натальная карта"
      role="img"
      fontFamily="'Segoe UI', system-ui, sans-serif"
    >
      {/* ── Background fill for entire chart area ── */}
      <circle cx={cx} cy={cy} r={R_ZOD_OUT} fill="#F8F6F0" stroke="none" />

      {/* ── Full-depth element sectors: outer edge → inner house circle (behind everything) ── */}
      {SIGN_GLYPHS.map((_, i) => {
        const lon1 = i * 30;
        const lon2 = (i + 1) * 30;
        const el   = SIGN_ELEMENT[i];
        return (
          <path
            key={`sector-full-${i}`}
            d={sectorPath(cx, cy, R_ZOD_OUT, R_HOUSE_IN, lon1, lon2, ascLon)}
            fill={ELEMENT_COLORS.fill[el]}
            stroke="none"
            opacity={0.35}
          />
        );
      })}

      {/* ── Zodiac sign sectors — full opacity ring (on top of transparent inner fill) ── */}
      {SIGN_GLYPHS.map((glyph, i) => {
        const lon1   = i * 30;
        const lon2   = (i + 1) * 30;
        const el     = SIGN_ELEMENT[i];
        const midLon = i * 30 + 15;
        const midPos = lonToXY(cx, cy, R_ZOD_MID, midLon, ascLon);
        return (
          <g key={`sign-${i}`}>
            {/* Fill sector fully, no stroke (prevents inter-sector gaps) */}
            <path
              d={sectorPath(cx, cy, R_ZOD_OUT, R_ZOD_IN, lon1, lon2, ascLon)}
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

      {/* ── Zodiac sign divider lines (radial, on top of sectors) ── */}
      {Array.from({ length: 12 }, (_, i) => {
        const lon = i * 30;
        const p1 = lonToXY(cx, cy, R_ZOD_OUT, lon, ascLon);
        const p2 = lonToXY(cx, cy, R_ZOD_IN,  lon, ascLon);
        return (
          <line key={`zdiv-${i}`}
            x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
            stroke="#B8A070" strokeWidth={0.75}
          />
        );
      })}

      {/* ── Outer zodiac border circle (on top to seal the ring) ── */}
      <circle cx={cx} cy={cy} r={R_ZOD_OUT} fill="none" stroke="#C0B898" strokeWidth={1.5} />

      {/* ── Zodiac inner border ── */}
      <circle cx={cx} cy={cy} r={R_ZOD_IN} fill="none" stroke="#B8A878" strokeWidth={1} />

      {/* ── Degree tick scale ── */}
      {Array.from({ length: 360 }, (_, deg) => {
        const isTen  = deg % 10 === 0;
        const isFive = !isTen && deg % 5 === 0;
        const tickLen = isTen ? R_ZOD_IN * 0.052 : isFive ? R_ZOD_IN * 0.033 : R_ZOD_IN * 0.016;
        const rOut  = R_TICK_OUT;
        const rIn   = R_TICK_OUT - tickLen;
        const svgDeg = 180 + (deg - ascLon);
        const p1 = polarToXY(cx, cy, rOut, svgDeg);
        const p2 = polarToXY(cx, cy, rIn,  svgDeg);
        return (
          <line
            key={`tick-${deg}`}
            x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
            stroke={isTen ? '#887060' : '#C0B090'}
            strokeWidth={isTen ? 0.9 : isFive ? 0.65 : 0.35}
          />
        );
      })}

      {/* ── Tick scale inner ring ── */}
      <circle cx={cx} cy={cy} r={R_TICK_IN} fill="#FAFAF7" stroke="#C8B890" strokeWidth={0.5} />

      {/* ── House cusp lines (extended from house inner circle through to outer zodiac edge) ── */}
      {!timeUnknown && houseCusps.length === 12 && houseCusps.map((house, i) => {
        const nextHouse = houseCusps[(i + 1) % 12];
        const lon1 = house.lon;
        let lon2 = nextHouse.lon;
        if (lon2 <= lon1) lon2 += 360;

        const isAngular = [1,4,7,10].includes(house.number);
        const midLon = lon1 + (lon2 - lon1) / 2;
        const numPos = lonToXY(cx, cy, R_NUM, midLon, ascLon);

        // Cusp line: from inner house circle all the way to outer zodiac edge
        const p1 = lonToXY(cx, cy, R_HOUSE_IN, house.lon, ascLon);
        const p2 = lonToXY(cx, cy, R_ZOD_OUT,  house.lon, ascLon);

        return (
          <g key={`house-${house.number}`}>
            <line
              x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
              stroke={isAngular ? '#604080' : '#B0A090'}
              strokeWidth={isAngular ? 1.5 : 0.75}
            />
            <text
              x={numPos.x} y={numPos.y}
              textAnchor="middle" dominantBaseline="central"
              fontSize={8.5} fill="#907860" fontStyle="italic"
            >
              {ROMAN[house.number - 1]}
            </text>
          </g>
        );
      })}

      {/* ── Inner circle (aspect area background) ── */}
      <circle cx={cx} cy={cy} r={R_HOUSE_IN} fill="#F5F2EC" stroke="#C0B080" strokeWidth={0.75} />

      {/* ── Aspect lines ── */}
      {aspects
        .filter(asp => ['conjunction','sextile','trine','square','opposition'].includes(asp.aspect_type))
        .map((asp, i) => {
          const p1 = planets.find(p => p.name === asp.planet1);
          const p2 = planets.find(p => p.name === asp.planet2);
          if (!p1 || !p2) return null;
          const pt1 = lonToXY(cx, cy, R_ASPECT, p1.longitude, ascLon);
          const pt2 = lonToXY(cx, cy, R_ASPECT, p2.longitude, ascLon);
          const color = ASPECT_COLORS[asp.aspect_type];
          const isHarmonic = asp.aspect_type === 'trine' || asp.aspect_type === 'sextile';
          const opacity = isHarmonic ? 0.5 : asp.aspect_type === 'conjunction' ? 0.7 : 0.6;
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

      {/* ── Center dot ── */}
      <circle cx={cx} cy={cy} r={2.5} fill="#807060" />

      {/* ── Planet glyphs ── */}
      {planetPositions.map((planet) => {
        const glyphPos = lonToXY(cx, cy, R_PLANET, planet.displayLon, ascLon);
        const realPos  = lonToXY(cx, cy, R_TICK_IN - 4, planet.longitude, ascLon);
        const color = PLANET_COLORS[planet.name] || '#606060';
        const showLine = Math.abs(planet.displayLon - planet.longitude) > 2;

        return (
          <g key={planet.name}>
            {/* Tick on tick-scale inner border */}
            {(() => {
              const t1 = lonToXY(cx, cy, R_TICK_IN + 1, planet.longitude, ascLon);
              const t2 = lonToXY(cx, cy, R_TICK_IN - 5, planet.longitude, ascLon);
              return <line x1={t1.x} y1={t1.y} x2={t2.x} y2={t2.y} stroke={color} strokeWidth={1.5} />;
            })()}

            {showLine && (
              <line
                x1={realPos.x} y1={realPos.y}
                x2={glyphPos.x} y2={glyphPos.y}
                stroke={color} strokeWidth={0.5} strokeOpacity={0.4}
              />
            )}

            <circle cx={glyphPos.x} cy={glyphPos.y} r={10}
              fill="rgba(248,246,240,0.9)" stroke={color} strokeWidth={0.75} />

            <text
              x={glyphPos.x} y={glyphPos.y}
              textAnchor="middle" dominantBaseline="central"
              fontSize={12} fontWeight="600" fill={color}
            >
              {PLANET_GLYPHS[planet.name] || '?'}
            </text>

            {/* Degree label */}
            {(() => {
              const degPos = lonToXY(cx, cy, R_PLANET - 16, planet.displayLon, ascLon);
              return (
                <text x={degPos.x} y={degPos.y}
                  textAnchor="middle" dominantBaseline="central"
                  fontSize={7} fill={color} opacity={0.8}
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

      {/* ── ASC / DSC / MC / IC labels (outside zodiac ring) ── */}
      {!timeUnknown && ascendant && (
        <>
          {[
            { lon: ascLon,                label: 'Asc', color: '#803060' },
            { lon: (ascLon + 180) % 360,  label: 'Dsc', color: '#803060' },
            ...(midheaven ? [
              { lon: mcLon,               label: 'MC',  color: '#204880' },
              { lon: (mcLon + 180) % 360, label: 'IC',  color: '#204880' },
            ] : []),
          ].map(({ lon, label, color }) => {
            const pos = lonToXY(cx, cy, R_ZOD_OUT + 14, lon, ascLon);
            return (
              <text key={label} x={pos.x} y={pos.y}
                textAnchor="middle" dominantBaseline="central"
                fontSize={9} fontWeight="700" fill={color}>{label}</text>
            );
          })}
        </>
      )}

      {/* ── Time unknown notice ── */}
      {timeUnknown && (
        <text x={cx} y={cy + R_HOUSE_IN - 20} textAnchor="middle"
          fontSize={10} fill="#A09070" fontStyle="italic">
          Время неизвестно — дома не показаны
        </text>
      )}

      {/* ── Transit outer ring ── */}
      {transitPlanets.length > 0 && (() => {
        // Use real longitude if available, else approximate from sign
        const withLon = transitPlanets.map(tp => ({
          ...tp,
          longitude: (tp.longitude != null && tp.longitude !== 0)
            ? tp.longitude
            : (SIGN_ORDER.indexOf(tp.transit_sign) * 30 + 15),
        }));
        const spread = pushApart(withLon.map(p => ({ ...p, displayLon: p.longitude })));

        return (
          <g>
            {/* Outer ring background circle */}
            <circle cx={cx} cy={cy} r={R_TRANSIT + 16}
              fill="rgba(20,15,50,0.45)" stroke="rgba(124,108,255,0.3)"
              strokeWidth={1} strokeDasharray="3 3" />

            {/* Aspect lines: transit planet → natal planet */}
            {spread.map((tp, i) => {
              if (!tp.aspect_type || !tp.natal_planet) return null;
              const natalPlanet = planets.find(p => p.name === tp.natal_planet);
              if (!natalPlanet) return null;
              const ptTransit = lonToXY(cx, cy, R_TRANSIT, tp.displayLon, ascLon);
              const ptNatal   = lonToXY(cx, cy, R_ASPECT,  natalPlanet.longitude, ascLon);
              const color = ASPECT_COLORS[tp.aspect_type] || '#8888AA';
              return (
                <line key={`tl-${i}`}
                  x1={ptTransit.x} y1={ptTransit.y}
                  x2={ptNatal.x}   y2={ptNatal.y}
                  stroke={color} strokeWidth={1} strokeOpacity={0.55}
                  strokeDasharray="4 3"
                />
              );
            })}

            {/* Transit planet glyphs — all planets on the outer ring */}
            {spread.map((tp, i) => {
              const pos        = lonToXY(cx, cy, R_TRANSIT, tp.displayLon, ascLon);
              const color      = PLANET_COLORS[tp.name] || '#A070C0';
              const hasAspect  = !!tp.aspect_type;
              return (
                <g key={`tg-${i}`}>
                  {/* Degree line from zodiac edge to planet */}
                  {(() => {
                    const inner = lonToXY(cx, cy, R_ZOD_OUT, tp.longitude, ascLon);
                    return <line x1={inner.x} y1={inner.y} x2={pos.x} y2={pos.y}
                      stroke={color} strokeWidth={0.5} strokeOpacity={0.3} />;
                  })()}

                  <circle cx={pos.x} cy={pos.y} r={12}
                    fill="rgba(12,10,30,0.92)"
                    stroke={color}
                    strokeWidth={hasAspect ? 2 : 1}
                    strokeOpacity={hasAspect ? 1 : 0.45}
                  />
                  <text x={pos.x} y={pos.y}
                    textAnchor="middle" dominantBaseline="central"
                    fontSize={13} fontWeight="700"
                    fill={color} fillOpacity={hasAspect ? 1 : 0.5}>
                    {PLANET_GLYPHS[tp.name] || '?'}
                  </text>

                  {/* Retrograde marker */}
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
