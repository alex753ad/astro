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

// Вычислить градус внутри знака из абсолютного эклиптического градуса (0–360)
function degreeInSign(absoluteDeg) {
  return absoluteDeg % 30;
}

// Определить знак по абсолютному градусу
const SIGN_ORDER = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces'];
function signFromDeg(absoluteDeg) {
  return SIGN_ORDER[Math.floor(absoluteDeg / 30) % 12];
}

/**
 * Table of planet positions + houses table.
 */
export default function ChartSummary({ planets, ascendant, midheaven, houses, timeUnknown, plain = false }) {
  return (
    <div className={plain ? 'cs-scope' : 'glass-card'} style={plain ? { background: 'var(--cs-bg, #fff)', color: 'var(--cs-fg)', borderRadius: 8, padding: '16px 20px' } : { padding: '24px' }}>
      {plain && <style>{`.dark .cs-scope { --cs-bg: rgba(26,18,48,0.55); --cs-fg: #E2DFF0; }`}</style>}
      {/* ── Планеты ── */}
      <h2 className="font-display text-lg font-bold mb-4 flex items-center gap-2">
        <span className="text-brand-accent">☉</span>
        Позиции планет
      </h2>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-brand-muted text-left border-b border-brand-accent/10">
              <th className="pb-2 pr-3">Планета</th>
              <th className="pb-2 pr-3">Знак</th>
              <th className="pb-2 pr-3">Градус</th>
              {!timeUnknown && <th className="pb-2">Дом</th>}
            </tr>
          </thead>
          <tbody>
            {planets.map((p) => (
              <tr key={p.name} className="border-b border-brand-accent/5 hover:bg-brand-accent/5 transition-colors">
                <td className="py-2 pr-3 font-medium flex items-center gap-2">
                  <span className="text-base opacity-70">{PLANET_GLYPHS[p.name]}</span>
                  <span>{PLANET_NAMES_RU[p.name] || p.name}</span>
                  {p.retrograde && <span className="text-xs text-red-400" title="Ретроградный">℞</span>}
                </td>
                <td className="py-2 pr-3">
                  <span className="mr-1">{SIGN_GLYPHS[p.sign]}</span>
                  {SIGN_NAMES_RU[p.sign] || p.sign}
                </td>
                <td className="py-2 pr-3 text-brand-muted">
                  {p.degree_in_sign?.toFixed(1)}°
                </td>
                {!timeUnknown && (
                  <td className="py-2 text-brand-muted">{p.house || '—'}</td>
                )}
              </tr>
            ))}

            {/* ASC / MC */}
            {ascendant && !timeUnknown && (
              <tr className="border-b border-brand-accent/5">
                <td className="py-2 pr-3 font-medium text-brand-glow">ASC</td>
                <td className="py-2 pr-3">
                  {SIGN_GLYPHS[ascendant.sign]} {SIGN_NAMES_RU[ascendant.sign]}
                </td>
                <td className="py-2 pr-3 text-brand-muted">{ascendant.degree?.toFixed(1)}°</td>
                {!timeUnknown && <td className="py-2">1</td>}
              </tr>
            )}
            {midheaven && !timeUnknown && (
              <tr>
                <td className="py-2 pr-3 font-medium text-brand-glow">MC</td>
                <td className="py-2 pr-3">
                  {SIGN_GLYPHS[midheaven.sign]} {SIGN_NAMES_RU[midheaven.sign]}
                </td>
                <td className="py-2 pr-3 text-brand-muted">{midheaven.degree?.toFixed(1)}°</td>
                {!timeUnknown && <td className="py-2">10</td>}
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Дома ── */}
      {!timeUnknown && houses?.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h2 className="font-display text-lg font-bold mb-4 flex items-center gap-2">
            <span className="text-brand-accent">⌂</span>
            Дома
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-brand-muted text-left border-b border-brand-accent/10">
                  <th className="pb-2 pr-3">Дом</th>
                  <th className="pb-2 pr-3">Знак</th>
                  <th className="pb-2">Градус</th>
                </tr>
              </thead>
              <tbody>
                {houses.map((h, idx) => {
                  const absD = h.degree ?? h.longitude ?? 0;
                  const sign = h.sign || signFromDeg(absD);
                  const deg  = h.degree_in_sign != null ? h.degree_in_sign : degreeInSign(absD);
                  return (
                    <tr key={h.number ?? h.house ?? idx} className="border-b border-brand-accent/5 hover:bg-brand-accent/5 transition-colors">
                      <td className="py-2 pr-3 font-medium">{h.number ?? h.house ?? idx + 1}</td>
                      <td className="py-2 pr-3">
                        <span className="mr-1">{SIGN_GLYPHS[sign]}</span>
                        {SIGN_NAMES_RU[sign] || sign}
                      </td>
                      <td className="py-2 text-brand-muted">{deg.toFixed(1)}°</td>
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
