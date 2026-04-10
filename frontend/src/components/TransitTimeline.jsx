import { useState, useEffect, useRef, useMemo, useCallback } from "react";

// ═══════════════════════════════════════════════════════════
// MOCK DATA (replace with API calls in production)
// ═══════════════════════════════════════════════════════════

const MOCK_EVENTS = [
  { date: "2026-04-03", transit_planet: "Venus", natal_planet: "Sun", aspect_type: "trine", orb: 0.4, exact_date: "2026-04-03T14:22", transit_sign: "Pisces", natal_sign: "Capricorn" },
  { date: "2026-04-05", transit_planet: "Mercury", natal_planet: "Jupiter", aspect_type: "sextile", orb: 1.1, exact_date: "2026-04-05T08:15", transit_sign: "Aries", natal_sign: "Sagittarius" },
  { date: "2026-04-07", transit_planet: "Mars", natal_planet: "Moon", aspect_type: "square", orb: 0.8, exact_date: "2026-04-07T19:40", transit_sign: "Cancer", natal_sign: "Cancer" },
  { date: "2026-04-09", transit_planet: "Sun", natal_planet: "Saturn", aspect_type: "square", orb: 1.5, exact_date: "2026-04-09T06:10", transit_sign: "Aries", natal_sign: "Capricorn" },
  { date: "2026-04-11", transit_planet: "Jupiter", natal_planet: "Sun", aspect_type: "conjunction", orb: 0.2, exact_date: "2026-04-11T11:33", transit_sign: "Cancer", natal_sign: "Capricorn" },
  { date: "2026-04-13", transit_planet: "Saturn", natal_planet: "Venus", aspect_type: "trine", orb: 0.9, exact_date: "2026-04-13T22:05", transit_sign: "Aries", natal_sign: "Aquarius" },
  { date: "2026-04-15", transit_planet: "Venus", natal_planet: "Mars", aspect_type: "opposition", orb: 0.6, exact_date: "2026-04-15T16:48", transit_sign: "Aries", natal_sign: "Taurus" },
  { date: "2026-04-17", transit_planet: "Mercury", natal_planet: "Neptune", aspect_type: "conjunction", orb: 1.3, exact_date: "2026-04-17T03:20", transit_sign: "Aries", natal_sign: "Aquarius" },
  { date: "2026-04-18", transit_planet: "Uranus", natal_planet: "Mercury", aspect_type: "square", orb: 0.3, exact_date: "2026-04-18T09:55", transit_sign: "Gemini", natal_sign: "Sagittarius" },
  { date: "2026-04-20", transit_planet: "Mars", natal_planet: "Sun", aspect_type: "opposition", orb: 1.0, exact_date: "2026-04-20T12:30", transit_sign: "Cancer", natal_sign: "Capricorn" },
  { date: "2026-04-22", transit_planet: "Neptune", natal_planet: "Moon", aspect_type: "trine", orb: 0.7, exact_date: "2026-04-22T07:15", transit_sign: "Aries", natal_sign: "Cancer" },
  { date: "2026-04-24", transit_planet: "Pluto", natal_planet: "Saturn", aspect_type: "conjunction", orb: 0.1, exact_date: "2026-04-24T18:40", transit_sign: "Aquarius", natal_sign: "Capricorn" },
  { date: "2026-04-26", transit_planet: "Sun", natal_planet: "Uranus", aspect_type: "square", orb: 1.8, exact_date: "2026-04-26T15:00", transit_sign: "Taurus", natal_sign: "Aquarius" },
  { date: "2026-04-28", transit_planet: "Venus", natal_planet: "Jupiter", aspect_type: "conjunction", orb: 0.5, exact_date: "2026-04-28T10:22", transit_sign: "Aries", natal_sign: "Sagittarius" },
  { date: "2026-04-30", transit_planet: "Saturn", natal_planet: "Moon", aspect_type: "square", orb: 1.2, exact_date: "2026-04-30T21:45", transit_sign: "Aries", natal_sign: "Cancer" },
];

const MOCK_INTERPRETATIONS = {
  "Jupiter conjunction Sun": "Транзит Юпитера в соединении с вашим натальным Солнцем — один из самых благоприятных транзитов, который случается раз в 12 лет.\n\nЭто период расширения возможностей, когда ваша уверенность в себе растёт, а жизнь словно открывает перед вами новые двери. Юпитер усиливает всё, к чему прикасается, и в данном случае он усиливает вашу жизненную силу, самовыражение и чувство цели.\n\nОбратите внимание на возможности в сфере карьеры и личного развития. Это не время скромничать — Юпитер вознаграждает смелость и оптимизм. Путешествия, обучение, юридические дела — всё это находится под покровительством этого транзита.\n\nРекомендация: используйте этот период для запуска проектов, которые давно откладывали. Энергия благоприятствует масштабному мышлению.",
  "Pluto conjunction Saturn": "Транзит Плутона в соединении с вашим натальным Сатурном — глубокий и трансформирующий процесс, который затрагивает сами основы вашей жизненной структуры.\n\nСатурн отвечает за правила, границы, дисциплину и то, как вы организуете свою жизнь. Плутон приходит и проверяет: насколько эти структуры подлинны? Что построено на прочном фундаменте, а что — на страхе?\n\nЭтот транзит может ощущаться как давление со стороны обстоятельств: карьерные изменения, перестройка жизненных приоритетов, столкновение с авторитетами. Но его цель — не разрушение, а обновление.\n\nТо, что выдержит этот транзит, станет несокрушимым фундаментом для следующего этапа вашей жизни. Отпустите то, что держится только на привычке.",
  "Uranus square Mercury": "Транзит Урана в квадрате к вашему натальному Меркурию вносит электрическое напряжение в сферу мышления и коммуникации.\n\nВы можете обнаружить, что привычные способы думать и общаться перестают работать. Неожиданные идеи, внезапные озарения, но также нервозность и рассеянность — всё это проявления этого аспекта.\n\nВажные решения лучше не принимать импульсивно. Дайте новым идеям «отлежаться» хотя бы несколько дней. При этом будьте открыты к нестандартным решениям — Уран часто приносит гениальные прозрения именно через дискомфорт.\n\nРекомендация: записывайте идеи, но не торопитесь с их реализацией. Перепроверяйте важные документы и договоры.",
};

// ═══════════════════════════════════════════════════════════
// CONSTANTS & HELPERS
// ═══════════════════════════════════════════════════════════

const PLANET_GLYPHS = {
  Sun: "☉", Moon: "☽", Mercury: "☿", Venus: "♀", Mars: "♂",
  Jupiter: "♃", Saturn: "♄", Uranus: "♅", Neptune: "♆", Pluto: "♇",
  "North Node": "☊",
};

const ASPECT_SYMBOLS = {
  conjunction: "☌", sextile: "⚹", square: "□", trine: "△", opposition: "☍",
};

const ASPECT_COLORS = {
  conjunction: "#F59E0B",
  sextile: "#3B82F6",
  square: "#EF4444",
  trine: "#3B82F6",
  opposition: "#EF4444",
};

const ASPECT_BG = {
  conjunction: "rgba(245,158,11,0.08)",
  sextile: "rgba(59,130,246,0.08)",
  square: "rgba(239,68,68,0.08)",
  trine: "rgba(59,130,246,0.08)",
  opposition: "rgba(239,68,68,0.08)",
};

const ASPECT_LABELS_RU = {
  conjunction: "Соединение",
  sextile: "Секстиль",
  square: "Квадрат",
  trine: "Трин",
  opposition: "Оппозиция",
};

const PLANET_LABELS_RU = {
  Sun: "Солнце", Moon: "Луна", Mercury: "Меркурий", Venus: "Венера",
  Mars: "Марс", Jupiter: "Юпитер", Saturn: "Сатурн", Uranus: "Уран",
  Neptune: "Нептун", Pluto: "Плутон", "North Node": "Сев. Узел",
};

const ALL_PLANETS = ["Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto"];
const ALL_ASPECTS = ["conjunction","sextile","square","trine","opposition"];

function formatDate(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function formatExactTime(exactDate) {
  if (!exactDate) return "";
  const parts = exactDate.split("T");
  return parts[1] || "";
}

function isHarmonic(aspect) {
  return aspect === "trine" || aspect === "sextile";
}

function isTense(aspect) {
  return aspect === "square" || aspect === "opposition";
}

// ═══════════════════════════════════════════════════════════
// SKELETON LOADER
// ═══════════════════════════════════════════════════════════

function Skeleton({ width = "100%", height = 16, radius = 6, style = {} }) {
  return (
    <div style={{
      width, height, borderRadius: radius,
      background: "linear-gradient(90deg, var(--sk1) 25%, var(--sk2) 50%, var(--sk1) 75%)",
      backgroundSize: "200% 100%",
      animation: "shimmer 1.8s ease-in-out infinite",
      ...style,
    }} />
  );
}

function EventCardSkeleton() {
  return (
    <div style={{
      padding: "14px 16px", borderRadius: 10,
      border: "1px solid var(--border)",
      background: "var(--card-bg)",
      display: "flex", flexDirection: "column", gap: 8,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <Skeleton width={80} height={12} />
        <Skeleton width={40} height={12} />
      </div>
      <Skeleton width="70%" height={18} />
      <Skeleton width="50%" height={12} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// FILTER BAR
// ═══════════════════════════════════════════════════════════

function FilterBar({ planetFilter, setPlanetFilter, aspectFilter, setAspectFilter, orbFilter, setOrbFilter }) {
  const [expandedSection, setExpandedSection] = useState(null);

  const toggle = (section) => setExpandedSection(prev => prev === section ? null : section);

  const chipStyle = (active) => ({
    padding: "5px 12px",
    borderRadius: 20,
    border: `1.5px solid ${active ? "var(--accent)" : "var(--border)"}`,
    background: active ? "var(--accent-bg)" : "transparent",
    color: active ? "var(--accent)" : "var(--text-secondary)",
    fontSize: 13,
    fontWeight: active ? 600 : 400,
    cursor: "pointer",
    transition: "all 0.2s ease",
    whiteSpace: "nowrap",
    userSelect: "none",
  });

  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 10,
      padding: "12px 16px",
      background: "var(--card-bg)",
      borderRadius: 12,
      border: "1px solid var(--border)",
    }}>
      {/* Planet filter */}
      <div>
        <button
          onClick={() => toggle("planets")}
          style={{
            background: "none", border: "none", color: "var(--text-secondary)",
            fontSize: 12, fontWeight: 600, letterSpacing: "0.05em",
            textTransform: "uppercase", cursor: "pointer", padding: 0,
            display: "flex", alignItems: "center", gap: 6,
          }}
        >
          <span>Планеты</span>
          <span style={{ fontSize: 10, transform: expandedSection === "planets" ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>▼</span>
          {planetFilter.length > 0 && planetFilter.length < ALL_PLANETS.length && (
            <span style={{
              background: "var(--accent)", color: "#fff",
              borderRadius: 10, padding: "1px 7px", fontSize: 11, fontWeight: 700,
            }}>{planetFilter.length}</span>
          )}
        </button>
        {expandedSection === "planets" && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {ALL_PLANETS.map(p => (
              <button key={p} style={chipStyle(planetFilter.includes(p))} onClick={() => {
                setPlanetFilter(prev =>
                  prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]
                );
              }}>
                {PLANET_GLYPHS[p]} {PLANET_LABELS_RU[p]}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Aspect filter */}
      <div>
        <button
          onClick={() => toggle("aspects")}
          style={{
            background: "none", border: "none", color: "var(--text-secondary)",
            fontSize: 12, fontWeight: 600, letterSpacing: "0.05em",
            textTransform: "uppercase", cursor: "pointer", padding: 0,
            display: "flex", alignItems: "center", gap: 6,
          }}
        >
          <span>Аспекты</span>
          <span style={{ fontSize: 10, transform: expandedSection === "aspects" ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>▼</span>
        </button>
        {expandedSection === "aspects" && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {ALL_ASPECTS.map(a => (
              <button key={a} style={chipStyle(aspectFilter.includes(a))} onClick={() => {
                setAspectFilter(prev =>
                  prev.includes(a) ? prev.filter(x => x !== a) : [...prev, a]
                );
              }}>
                <span style={{ color: ASPECT_COLORS[a] }}>{ASPECT_SYMBOLS[a]}</span> {ASPECT_LABELS_RU[a]}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Orb filter */}
      <div>
        <button
          onClick={() => toggle("orb")}
          style={{
            background: "none", border: "none", color: "var(--text-secondary)",
            fontSize: 12, fontWeight: 600, letterSpacing: "0.05em",
            textTransform: "uppercase", cursor: "pointer", padding: 0,
            display: "flex", alignItems: "center", gap: 6,
          }}
        >
          <span>Орб ≤ {orbFilter}°</span>
          <span style={{ fontSize: 10, transform: expandedSection === "orb" ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>▼</span>
        </button>
        {expandedSection === "orb" && (
          <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 12 }}>
            <input
              type="range" min={0.5} max={3} step={0.5}
              value={orbFilter}
              onChange={e => setOrbFilter(Number(e.target.value))}
              style={{ flex: 1 }}
            />
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", minWidth: 28 }}>{orbFilter}°</span>
          </div>
        )}
      </div>

      {/* Reset */}
      {(planetFilter.length > 0 || aspectFilter.length > 0 || orbFilter !== 2.0) && (
        <button
          onClick={() => { setPlanetFilter([]); setAspectFilter([]); setOrbFilter(2.0); }}
          style={{
            alignSelf: "flex-start", background: "none",
            border: "1px solid var(--border)", color: "var(--text-secondary)",
            borderRadius: 8, padding: "4px 12px", fontSize: 12, cursor: "pointer",
          }}
        >
          Сбросить фильтры
        </button>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// DATE NAV
// ═══════════════════════════════════════════════════════════

function DateNav({ dates, activeDate, onDateClick, eventCountByDate }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (activeDate && scrollRef.current) {
      const idx = dates.indexOf(activeDate);
      if (idx >= 0) {
        const el = scrollRef.current.children[idx];
        el?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
      }
    }
  }, [activeDate, dates]);

  return (
    <div ref={scrollRef} style={{
      display: "flex", gap: 6, overflowX: "auto", paddingBottom: 6,
      scrollbarWidth: "none",
      msOverflowStyle: "none",
    }}>
      {dates.map(d => {
        const active = d === activeDate;
        const count  = eventCountByDate[d] || 0;
        const dt     = new Date(d + "T00:00:00");
        const dayNum = dt.getDate();
        const dayName = dt.toLocaleDateString("ru-RU", { weekday: "short" });

        return (
          <button
            key={d}
            onClick={() => onDateClick(d)}
            style={{
              minWidth: 48, flexShrink: 0,
              display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
              padding: "8px 6px", borderRadius: 10,
              border: `1.5px solid ${active ? "var(--accent)" : "var(--border)"}`,
              background: active ? "var(--accent-bg)" : "var(--card-bg)",
              color: active ? "var(--accent)" : "var(--text-secondary)",
              cursor: "pointer", transition: "all 0.2s",
              fontFamily: "inherit",
            }}
          >
            <span style={{ fontSize: 11, opacity: 0.7 }}>{dayName}</span>
            <span style={{ fontSize: 15, fontWeight: active ? 700 : 500 }}>{dayNum}</span>
            {count > 0 && (
              <span style={{
                width: 6, height: 6, borderRadius: 3,
                background: active ? "var(--accent)" : "var(--border)",
              }} />
            )}
          </button>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// STATS SUMMARY
// ═══════════════════════════════════════════════════════════

function StatsSummary({ events }) {
  const harmonicCount = events.filter(e => isHarmonic(e.aspect_type)).length;
  const tenseCount    = events.filter(e => isTense(e.aspect_type)).length;
  const conjCount     = events.filter(e => e.aspect_type === "conjunction").length;

  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      {[
        { label: "Всего", value: events.length, color: "var(--accent)" },
        { label: "Гармоничных", value: harmonicCount, color: "#3B82F6" },
        { label: "Напряжённых", value: tenseCount, color: "#EF4444" },
        { label: "Соединений", value: conjCount, color: "#F59E0B" },
      ].map(({ label, value, color }) => (
        <div key={label} style={{
          flex: "1 1 80px",
          padding: "10px 14px",
          borderRadius: 10, border: "1px solid var(--border)",
          background: "var(--card-bg)",
          display: "flex", flexDirection: "column", gap: 3,
        }}>
          <span style={{ fontSize: 20, fontWeight: 800, color }}>{value}</span>
          <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{label}</span>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// EVENT CARD
// ═══════════════════════════════════════════════════════════

function EventCard({ event, index, isSelected, onClick }) {
  const aspectColor = ASPECT_COLORS[event.aspect_type] || "var(--accent)";
  const aspectBg    = ASPECT_BG[event.aspect_type]    || "var(--accent-bg)";
  const displayDate = event.peak_date || event.exact_date || event.date || "";

  return (
    <div
      onClick={onClick}
      style={{
        padding: "14px 16px", borderRadius: 10, cursor: "pointer",
        border: `1px solid ${isSelected ? aspectColor : "var(--border)"}`,
        background: isSelected ? aspectBg : "var(--card-bg)",
        transition: "all 0.2s ease",
        animation: `fadeSlideIn 0.3s ease ${index * 0.04}s both`,
      }}
    >
      {/* Top row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            fontSize: 11, fontWeight: 600,
            color: "var(--text-secondary)",
            letterSpacing: "0.04em",
          }}>
            {displayDate ? formatDate(displayDate) : ""}
          </span>
          {event.exact_date && (
            <span style={{ fontSize: 10, color: "var(--text-secondary)", opacity: 0.6 }}>
              {formatExactTime(event.exact_date)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {event.applying !== undefined && (
            <span style={{
              fontSize: 10, padding: "2px 7px", borderRadius: 8,
              border: `1px solid ${event.applying ? "rgba(59,130,246,0.3)" : "var(--border)"}`,
              color: event.applying ? "#3B82F6" : "var(--text-secondary)",
              background: event.applying ? "rgba(59,130,246,0.06)" : "transparent",
            }}>
              {event.applying ? "→ точный" : "← отходит"}
            </span>
          )}
          <span style={{ fontSize: 11, color: "var(--text-secondary)", opacity: 0.6 }}>
            орб {(event.peak_orb ?? event.orb ?? 0).toFixed(1)}°
          </span>
        </div>
      </div>

      {/* Planet pair */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 20 }}>{PLANET_GLYPHS[event.transit_planet] || "★"}</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
          {PLANET_LABELS_RU[event.transit_planet] || event.transit_planet}
        </span>
        <span style={{ fontSize: 16, color: aspectColor, fontWeight: 700 }}>
          {ASPECT_SYMBOLS[event.aspect_type] || "·"}
        </span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {ASPECT_LABELS_RU[event.aspect_type] || event.aspect_type}
        </span>
        <span style={{ fontSize: 20 }}>{PLANET_GLYPHS[event.natal_planet] || "☽"}</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
          {PLANET_LABELS_RU[event.natal_planet] || event.natal_planet}
        </span>
      </div>

      {/* Signs */}
      {(event.transit_sign || event.natal_sign) && (
        <div style={{ marginTop: 5, fontSize: 12, color: "var(--text-secondary)" }}>
          {event.transit_sign} → {event.natal_sign}
        </div>
      )}

      {isSelected && (
        <div style={{ marginTop: 8, fontSize: 11, color: aspectColor, fontWeight: 600 }}>
          Нажмите для интерпретации ↓
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// INTERPRETATION PANEL
// ═══════════════════════════════════════════════════════════

const SPHERE_ICONS = { work: "💼", love: "💕", health: "🌿", finance: "💰", personal: "✨", social: "🤝", spiritual: "🔮" };
const SPHERE_LABELS = { work: "Работа", love: "Отношения", health: "Здоровье", finance: "Финансы", personal: "Личность", social: "Социум", spiritual: "Духовность" };

function InterpretationPanel({ event, onClose }) {
  const [text, setText]       = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const scrollRef = useRef(null);

  const key = `${PLANET_LABELS_RU[event.transit_planet] || event.transit_planet} ${ASPECT_LABELS_RU[event.aspect_type] || event.aspect_type} ${PLANET_LABELS_RU[event.natal_planet] || event.natal_planet}`;
  const mockKey = `${event.transit_planet} ${event.aspect_type} ${event.natal_planet}`;

  useEffect(() => {
    setText(""); setLoading(true); setError(null);

    if (MOCK_INTERPRETATIONS[mockKey]) {
      let i = 0;
      const mock = MOCK_INTERPRETATIONS[mockKey];
      const interval = setInterval(() => {
        i += 3;
        setText(mock.slice(0, i));
        if (i >= mock.length) { clearInterval(interval); setLoading(false); }
      }, 12);
      return () => clearInterval(interval);
    }

    if (!event.chartId) {
      setTimeout(() => {
        setText(`Интерпретация транзита: ${key}.\n\nЭтот аспект влияет на сферу жизни, связанную с натальной планетой. Рекомендуется обратить внимание на события этого периода и использовать энергию транзита осознанно.`);
        setLoading(false);
      }, 800);
      return;
    }

    const token = localStorage.getItem('astro_access_token');
    const ctrl  = new AbortController();
    fetch(`/api/v1/chart/${event.chartId}/transits/event/interpret`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        transit_planet: event.transit_planet,
        natal_planet:   event.natal_planet,
        aspect_type:    event.aspect_type,
      }),
      signal: ctrl.signal,
    })
      .then(async r => {
        if (!r.ok) throw new Error(r.statusText);
        const reader = r.body.getReader();
        const dec    = new TextDecoder();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = dec.decode(value);
          chunk.split("\n").forEach(line => {
            if (line.startsWith("data: ")) {
              const d = line.slice(6).trim();
              if (d !== "[DONE]") setText(p => p + d);
            }
          });
        }
        setLoading(false);
      })
      .catch(e => { if (e.name !== "AbortError") setError(e.message); setLoading(false); });

    return () => ctrl.abort();
  }, [event]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [text]);

  return (
    <div style={{
      background: "var(--card-bg)", borderRadius: 14,
      border: "1px solid var(--border)",
      animation: "fadeSlideIn 0.3s ease",
    }}>
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid var(--border)",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{key}</div>
        <button onClick={onClose} style={{
          background: "none", border: "none", color: "var(--text-secondary)",
          fontSize: 18, cursor: "pointer", padding: "2px 6px", borderRadius: 6,
        }}>✕</button>
      </div>
      <div ref={scrollRef} style={{ padding: 16, maxHeight: 400, overflowY: "auto" }}>
        {loading && !text && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[90, 70, 85, 60].map((w, i) => <Skeleton key={i} width={`${w}%`} height={13} />)}
          </div>
        )}
        {error && <div style={{ color: "#EF4444", fontSize: 13 }}>{error}</div>}
        {text && (
          <div style={{ fontSize: 13, lineHeight: 1.75, color: "var(--text-primary)", whiteSpace: "pre-wrap" }}>
            {text}
            {loading && (
              <span style={{
                display: "inline-block", width: 6, height: 14,
                background: "var(--accent)", marginLeft: 2, borderRadius: 2,
                animation: "blink 0.8s step-end infinite", verticalAlign: "text-bottom",
              }} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════

export default function TransitTimeline({ chartId, onDateSelect }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [planetFilter, setPlanetFilter] = useState([]);
  const [aspectFilter, setAspectFilter] = useState([]);
  const [orbFilter, setOrbFilter] = useState(2.0);
  const [activeDate, setActiveDate] = useState(null);

  // Load transits from API
  useEffect(() => {
    if (!chartId) {
      setEvents(MOCK_EVENTS);
      setLoading(false);
      return;
    }
    setLoading(true);
    const today = new Date();
    const from = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);
    const to   = new Date(today.getFullYear(), today.getMonth() + 2, 0).toISOString().slice(0, 10);
    fetch(`/api/v1/chart/${chartId}/transits?from_date=${from}&to_date=${to}`)
      .then(r => r.json())
      .then(data => { setEvents(data.events || []); setLoading(false); })
      .catch(() => { setEvents([]); setLoading(false); });
  }, [chartId]);

  const filteredEvents = useMemo(() => {
    return events.filter(e => {
      if (planetFilter.length > 0 && !planetFilter.includes(e.transit_planet)) return false;
      if (aspectFilter.length > 0 && !aspectFilter.includes(e.aspect_type)) return false;
      if ((e.peak_orb ?? e.orb) > orbFilter) return false;
      if (activeDate) {
        const s  = e.start_date || e.date;
        const en = e.end_date   || e.date;
        if (activeDate < s || activeDate > en) return false;
      }
      return true;
    });
  }, [events, planetFilter, aspectFilter, orbFilter, activeDate]);

  const dates = useMemo(() => [...new Set(events.map(e => e.peak_date || e.date))].sort(), [events]);
  const eventCountByDate = useMemo(() => {
    const counts = {};
    events.forEach(e => { counts[e.peak_date||e.date] = (counts[e.peak_date||e.date] || 0) + 1; });
    return counts;
  }, [events]);

  const handleEventClick = useCallback((event) => {
    setSelectedEvent(prev => prev === event ? null : event);
  }, []);

  const handleDateClick = useCallback(async (d) => {
    const next = activeDate === d ? null : d;
    setActiveDate(next);
    if (!onDateSelect) return;
    if (!next) { onDateSelect(null, [], []); return; }

    const dayEvents = events.filter(e => {
      const s  = e.start_date || e.date;
      const en = e.end_date   || e.date;
      return next >= s && next <= en;
    });

    let positions = [];
    if (chartId) {
      try {
        const resp = await fetch(`/api/v1/chart/${chartId}/transits/positions?on_date=${next}`);
        if (resp.ok) {
          const data = await resp.json();
          positions = data.planets || [];
        }
      } catch {}
    }
    onDateSelect(next, dayEvents, positions);
  }, [activeDate, events, onDateSelect, chartId]);

  return (
    <div style={{
      fontFamily: "'DM Sans', 'Segoe UI', system-ui, sans-serif",
      maxWidth: 900,
      margin: "0 auto",
      padding: "24px 16px",
      color: "var(--text-primary)",
    }}>
      <style>{`
        :root {
          --bg: #0C0E14;
          --card-bg: #141620;
          --border: #1E2235;
          --text-primary: #E8EAF0;
          --text-secondary: #8B8FA3;
          --accent: #7C6CFF;
          --accent-bg: rgba(124,108,255,0.1);
          --sk1: #1A1D2E;
          --sk2: #242840;
        }
        @media (prefers-color-scheme: light) {
          :root {
            --bg: #F7F7FB;
            --card-bg: #FFFFFF;
            --border: #E4E5EC;
            --text-primary: #1A1C24;
            --text-secondary: #6B6F80;
            --accent: #6551E8;
            --accent-bg: rgba(101,81,232,0.08);
            --sk1: #EEEEF3;
            --sk2: #E0E1EA;
          }
        }
        body { background: var(--bg); margin: 0; }
        @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        @keyframes fadeSlideIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes blink { 50% { opacity: 0; } }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
        input[type="range"] { height: 4px; border-radius: 2px; appearance: auto; }
      `}</style>

      {/* Title */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{
          fontSize: 26, fontWeight: 700, margin: 0,
          background: "linear-gradient(135deg, var(--accent), #A78BFA)",
          WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
          letterSpacing: "-0.02em",
        }}>
          Транзиты
        </h1>
        <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: "6px 0 0" }}>
          {new Date().toLocaleDateString("ru-RU", { month: "long", year: "numeric" })}
        </p>
      </div>

      {!loading && <StatsSummary events={filteredEvents} />}

      {!loading && dates.length > 0 && (
        <div style={{ margin: "16px 0" }}>
          <DateNav
            dates={dates}
            activeDate={activeDate}
            onDateClick={d => handleDateClick(d)}
            eventCountByDate={eventCountByDate}
          />
        </div>
      )}

      <div style={{ margin: "12px 0 16px" }}>
        <FilterBar
          planetFilter={planetFilter} setPlanetFilter={setPlanetFilter}
          aspectFilter={aspectFilter} setAspectFilter={setAspectFilter}
          orbFilter={orbFilter} setOrbFilter={setOrbFilter}
        />
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: selectedEvent ? "1fr 1fr" : "1fr",
        gap: 16, alignItems: "start",
        transition: "grid-template-columns 0.3s ease",
      }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => <EventCardSkeleton key={i} />)
          ) : filteredEvents.length === 0 ? (
            <div style={{
              padding: 40, textAlign: "center", color: "var(--text-secondary)",
              fontSize: 14, borderRadius: 12, border: "1px dashed var(--border)",
            }}>
              Нет транзитов с текущими фильтрами.
              <br />
              <span style={{ fontSize: 12, opacity: 0.7 }}>Попробуйте увеличить орб или сбросить фильтры.</span>
            </div>
          ) : (
            filteredEvents.map((event, idx) => (
              <EventCard
                key={`${event.peak_date||event.start_date||event.date}-${event.transit_planet}-${event.natal_planet}-${event.aspect_type}`}
                event={event} index={idx}
                isSelected={selectedEvent === event}
                onClick={() => handleEventClick(event)}
              />
            ))
          )}
        </div>

        {selectedEvent && (
          <div style={{ position: "sticky", top: 24 }}>
            <InterpretationPanel event={selectedEvent} onClose={() => setSelectedEvent(null)} />
          </div>
        )}
      </div>

      {!loading && (
        <div style={{
          marginTop: 32, padding: "16px 0",
          borderTop: "1px solid var(--border)",
          fontSize: 12, color: "var(--text-secondary)", textAlign: "center", opacity: 0.6,
        }}>
          Транзитные орбы: соединение/оппозиция ≤ 2° • квадрат ≤ 2° • трин/секстиль ≤ 1.5°
          <br />
          Нажмите на транзит для AI-интерпретации
        </div>
      )}
    </div>
  );
}
