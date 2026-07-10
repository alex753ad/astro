import React from 'react';

const SIGN_GLYPHS = {
  Aries: '♈', Taurus: '♉', Gemini: '♊', Cancer: '♋',
  Leo: '♌', Virgo: '♍', Libra: '♎', Scorpio: '♏',
  Sagittarius: '♐', Capricorn: '♑', Aquarius: '♒', Pisces: '♓',
};

const PLANET_GLYPHS = {
  Sun: '☉', Moon: '☽', Mercury: '☿', Venus: '♀', Mars: '♂',
  Jupiter: '♃', Saturn: '♄', Uranus: '♅', Neptune: '♆', Pluto: '♇',
  'North Node': '☊',
};

const PLANET_NAMES_RU = {
  Sun: 'Солнце', Moon: 'Луна', Mercury: 'Меркурий', Venus: 'Венера',
  Mars: 'Марс', Jupiter: 'Юпитер', Saturn: 'Сатурн', Uranus: 'Уран',
  Neptune: 'Нептун', Pluto: 'Плутон', 'North Node': 'Сев. узел',
};

const SIGN_NAMES_RU = {
  Aries: 'Овен', Taurus: 'Телец', Gemini: 'Близнецы', Cancer: 'Рак',
  Leo: 'Лев', Virgo: 'Дева', Libra: 'Весы', Scorpio: 'Скорпион',
  Sagittarius: 'Стрелец', Capricorn: 'Козерог', Aquarius: 'Водолей', Pisces: 'Рыбы',
};

function degreeInSign(absoluteDeg) {
  return absoluteDeg % 30;
}

const SIGN_ORDER = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces'];
function signFromDeg(absoluteDeg) {
  return SIGN_ORDER[Math.floor(absoluteDeg / 30) % 12];
}

function theme(dark) {
  return {
    bg:      dark ? 'rgba(26,18,48,0.55)' : '#ffffff',
    fg:      dark ? '#E2DFF0'             : '#1E1A2E',
    accent:  dark ? '#A78BFA'             : '#7C3AED',
    muted:   dark ? '#9B97B0'             : '#7060A0',
    border:  dark ? 'rgba(139,92,246,0.15)' : 'rgba(139,92,246,0.1)',
  };
}

export default function ChartSummary({ planets, ascendant, midheaven, houses, timeUnknown, plain = false, dark = false }) {
  const t = theme(dark);

  const wrapStyle = plain
    ? { background: t.bg, color: t.fg, borderRadius: 8, padding: '16px 20px' }
    : { padding: '24px' };

  const headStyle = {
    fontSize: 16, fontWeight: 700, marginBottom: 16,
    display: 'flex', alignItems: 'center', gap: 8,
    color: t.fg,
  };

  const thStyle = {
    paddingBottom: 8, paddingRight: 12,
    color: t.muted, textAlign: 'left',
    fontSize: 13, fontWeight: 500,
    borderBottom: `1px solid ${t.border}`,
  };

  const tdBaseStyle = {
    padding: '7px 12px 7px 0',
    fontSize: 13,
    borderBottom: `1px solid ${t.border}`,
  };

  return (
    <div style={wrapStyle}>
      {/* ── Планеты ── */}
      <div style={headStyle}>
        <span style={{ color: t.accent }}>☉</span>
        Позиции планет
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              <th style={thStyle}>Планета</th>
              <th style={thStyle}>Знак</th>
              <th style={thStyle}>Градус</th>
              {!timeUnknown && <th style={thStyle}>Дом</th>}
            </tr>
          </thead>
          <tbody>
            {planets.map((p) => (
              <tr key={p.name}>
                <td style={{ ...tdBaseStyle, color: t.fg, fontWeight: 500 }}>
                  <span style={{ opacity: 0.7, marginRight: 6 }}>{PLANET_GLYPHS[p.name]}</span>
                  {PLANET_NAMES_RU[p.name] || p.name}
                  {p.retrograde && <span style={{ fontSize: 11, color: '#f87171', marginLeft: 4 }}>℞</span>}
                </td>
                <td style={{ ...tdBaseStyle, color: t.fg }}>
                  <span style={{ marginRight: 4 }}>{SIGN_GLYPHS[p.sign]}</span>
                  {SIGN_NAMES_RU[p.sign] || p.sign}
                </td>
                <td style={{ ...tdBaseStyle, color: t.muted }}>
                  {p.degree_in_sign?.toFixed(1)}°
                </td>
                {!timeUnknown && (
                  <td style={{ ...tdBaseStyle, color: t.muted }}>{p.house || '—'}</td>
                )}
              </tr>
            ))}

            {/* ASC / MC */}
            {ascendant && !timeUnknown && (
              <tr>
                <td style={{ ...tdBaseStyle, color: t.accent, fontWeight: 600 }}>ASC</td>
                <td style={{ ...tdBaseStyle, color: t.fg }}>
                  {SIGN_GLYPHS[ascendant.sign]} {SIGN_NAMES_RU[ascendant.sign]}
                </td>
                <td style={{ ...tdBaseStyle, color: t.muted }}>{ascendant.degree?.toFixed(1)}°</td>
                {!timeUnknown && <td style={{ ...tdBaseStyle, color: t.muted }}>1</td>}
              </tr>
            )}
            {midheaven && !timeUnknown && (
              <tr>
                <td style={{ ...tdBaseStyle, color: t.accent, fontWeight: 600 }}>MC</td>
                <td style={{ ...tdBaseStyle, color: t.fg }}>
                  {SIGN_GLYPHS[midheaven.sign]} {SIGN_NAMES_RU[midheaven.sign]}
                </td>
                <td style={{ ...tdBaseStyle, color: t.muted }}>{midheaven.degree?.toFixed(1)}°</td>
                {!timeUnknown && <td style={{ ...tdBaseStyle, color: t.muted }}>10</td>}
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Дома ── */}
      {!timeUnknown && houses?.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <div style={headStyle}>
            <span style={{ color: t.accent }}>⌂</span>
            Дома
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={thStyle}>Дом</th>
                  <th style={thStyle}>Знак</th>
                  <th style={thStyle}>Градус</th>
                </tr>
              </thead>
              <tbody>
                {houses.map((h, idx) => {
                  const absD = h.degree ?? h.longitude ?? 0;
                  const sign = h.sign || signFromDeg(absD);
                  const deg  = h.degree_in_sign != null ? h.degree_in_sign : degreeInSign(absD);
                  return (
                    <tr key={h.number ?? h.house ?? idx}>
                      <td style={{ ...tdBaseStyle, color: t.fg, fontWeight: 500 }}>{h.number ?? h.house ?? idx + 1}</td>
                      <td style={{ ...tdBaseStyle, color: t.fg }}>
                        <span style={{ marginRight: 4 }}>{SIGN_GLYPHS[sign]}</span>
                        {SIGN_NAMES_RU[sign] || sign}
                      </td>
                      <td style={{ ...tdBaseStyle, color: t.muted }}>{deg.toFixed(1)}°</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
