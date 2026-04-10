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
// SKELETON LOADER (Phase 3.3 — Loading states)
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
            <span
              onClick={() => setPlanetFilter([])}
              style={chipStyle(planetFilter.length === 0)}
            >Все</span>
            {ALL_PLANETS.map(p => (
              <span
                key={p}
                onClick={() => {
                  setPlanetFilter(prev =>
                    prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]
                  );
                }}
                style={chipStyle(planetFilter.includes(p))}
              >
                {PLANET_GLYPHS[p]} {PLANET_LABELS_RU[p]}
              </span>
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
            <span onClick={() => setAspectFilter([])} style={chipStyle(aspectFilter.length === 0)}>Все</span>
            {ALL_ASPECTS.map(a => (
              <span
                key={a}
                onClick={() => {
                  setAspectFilter(prev =>
                    prev.includes(a) ? prev.filter(x => x !== a) : [...prev, a]
                  );
                }}
                style={{
                  ...chipStyle(aspectFilter.includes(a)),
                  borderColor: aspectFilter.includes(a) ? ASPECT_COLORS[a] : "var(--border)",
                  color: aspectFilter.includes(a) ? ASPECT_COLORS[a] : "var(--text-secondary)",
                  background: aspectFilter.includes(a) ? ASPECT_BG[a] : "transparent",
                }}
              >
                {ASPECT_SYMBOLS[a]} {ASPECT_LABELS_RU[a]}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Orb filter */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Орб ≤ {orbFilter}°
        </span>
        <input
          type="range"
          min={0.1} max={2.5} step={0.1}
          value={orbFilter}
          onChange={e => setOrbFilter(parseFloat(e.target.value))}
          aria-label="Maximum orb filter"
          style={{ flex: 1, accentColor: "var(--accent)" }}
        />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// EVENT CARD
// ═══════════════════════════════════════════════════════════

function EventCard({ event, isSelected, onClick, index }) {
  const color = ASPECT_COLORS[event.aspect_type];
  const bg = ASPECT_BG[event.aspect_type];
  const significance = event.orb < 0.5 ? "high" : event.orb < 1.0 ? "medium" : "normal";

  return (
    <button
      onClick={onClick}
      aria-label={`${event.transit_planet} ${ASPECT_LABELS_RU[event.aspect_type]} ${event.natal_planet}, ${formatDate(event.date)}`}
      aria-pressed={isSelected}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        padding: "14px 16px",
        borderRadius: 12,
        border: `1.5px solid ${isSelected ? color : "var(--border)"}`,
        background: isSelected ? bg : "var(--card-bg)",
        cursor: "pointer",
        textAlign: "left",
        transition: "all 0.25s cubic-bezier(0.4,0,0.2,1)",
        transform: isSelected ? "scale(1.02)" : "scale(1)",
        boxShadow: isSelected ? `0 4px 20px ${color}22` : "none",
        animation: `fadeSlideIn 0.35s ease ${index * 0.04}s both`,
        width: "100%",
        fontFamily: "inherit",
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "var(--text-secondary)", fontWeight: 500 }}>
          {formatDate(event.date)}
          {event.exact_date && (
            <span style={{ marginLeft: 6, opacity: 0.6 }}>
              {formatExactTime(event.exact_date)}
            </span>
          )}
        </span>
        <span style={{
          fontSize: 11,
          padding: "2px 8px",
          borderRadius: 8,
          background: bg,
          color,
          fontWeight: 600,
        }}>
          {event.orb.toFixed(1)}°
        </span>
      </div>

      {/* Main aspect line */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 20 }}>{PLANET_GLYPHS[event.transit_planet]}</span>
        <span style={{
          fontSize: 18, color, fontWeight: 700,
          textShadow: significance === "high" ? `0 0 8px ${color}44` : "none",
        }}>
          {ASPECT_SYMBOLS[event.aspect_type]}
        </span>
        <span style={{ fontSize: 20 }}>{PLANET_GLYPHS[event.natal_planet]}</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginLeft: 4 }}>
          {PLANET_LABELS_RU[event.transit_planet]}
          <span style={{ color: "var(--text-secondary)", fontWeight: 400 }}> → </span>
          {PLANET_LABELS_RU[event.natal_planet]}
        </span>
      </div>

      {/* Aspect label */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-secondary)" }}>
        <span style={{ color, fontWeight: 500 }}>{ASPECT_LABELS_RU[event.aspect_type]}</span>
        <span>•</span>
        <span>{event.transit_sign}</span>

        {significance === "high" && (
          <span style={{
            marginLeft: "auto",
            fontSize: 10,
            padding: "2px 8px",
            borderRadius: 8,
            background: `${color}18`,
            color,
            fontWeight: 600,
            letterSpacing: "0.03em",
          }}>
            ● ТОЧНЫЙ
          </span>
        )}
      </div>
    </button>
  );
}

// ═══════════════════════════════════════════════════════════
// INTERPRETATION PANEL
// ═══════════════════════════════════════════════════════════

function InterpretationPanel({ event, onClose }) {
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(true);
  const textRef = useRef(null);

  useEffect(() => {
    if (!event) return;
    setText("");
    setStreaming(true);

    // Simulate SSE streaming (replace with real API call)
    const key = `${event.transit_planet} ${event.aspect_type} ${event.natal_planet}`;
    const fullText = MOCK_INTERPRETATIONS[key] ||
      `Транзит ${PLANET_LABELS_RU[event.transit_planet]} в ${ASPECT_LABELS_RU[event.aspect_type].toLowerCase()} к натальному ${PLANET_LABELS_RU[event.natal_planet]}.\n\nЭтот аспект активизирует темы, связанные с энергией ${PLANET_LABELS_RU[event.natal_planet]} в вашей карте. Обратите внимание на события и внутренние процессы в этот период.\n\nОрб ${event.orb.toFixed(1)}° указывает на ${event.orb < 1.0 ? "сильное" : "умеренное"} влияние этого транзита.`;

    let idx = 0;
    const speed = 12; // chars per tick
    const interval = setInterval(() => {
      idx += speed;
      if (idx >= fullText.length) {
        setText(fullText);
        setStreaming(false);
        clearInterval(interval);
      } else {
        setText(fullText.slice(0, idx));
      }
    }, 30);

    return () => clearInterval(interval);
  }, [event]);

  useEffect(() => {
    if (textRef.current) {
      textRef.current.scrollTop = textRef.current.scrollHeight;
    }
  }, [text]);

  if (!event) return null;

  const color = ASPECT_COLORS[event.aspect_type];

  return (
    <div style={{
      background: "var(--card-bg)",
      borderRadius: 14,
      border: "1px solid var(--border)",
      overflow: "hidden",
      animation: "fadeSlideIn 0.3s ease",
      display: "flex",
      flexDirection: "column",
    }}>
      {/* Header */}
      <div style={{
        padding: "16px 20px",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        background: `linear-gradient(135deg, ${color}08, transparent)`,
      }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 22 }}>{PLANET_GLYPHS[event.transit_planet]}</span>
            <span style={{ fontSize: 20, color, fontWeight: 700 }}>{ASPECT_SYMBOLS[event.aspect_type]}</span>
            <span style={{ fontSize: 22 }}>{PLANET_GLYPHS[event.natal_planet]}</span>
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>
            {PLANET_LABELS_RU[event.transit_planet]} {ASPECT_LABELS_RU[event.aspect_type].toLowerCase()} {PLANET_LABELS_RU[event.natal_planet]}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
            {formatDate(event.date)} • {event.transit_sign} • Орб {event.orb.toFixed(1)}°
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="Закрыть"
          style={{
            background: "none", border: "none", color: "var(--text-secondary)",
            fontSize: 22, cursor: "pointer", padding: "4px 8px",
            borderRadius: 8, transition: "background 0.2s",
          }}
          onMouseEnter={e => e.target.style.background = "var(--border)"}
          onMouseLeave={e => e.target.style.background = "none"}
        >
          ✕
        </button>
      </div>

      {/* Body — interpretation text */}
      <div
        ref={textRef}
        style={{
          padding: "20px",
          fontSize: 14.5,
          lineHeight: 1.75,
          color: "var(--text-primary)",
          maxHeight: 360,
          overflowY: "auto",
          whiteSpace: "pre-wrap",
        }}
      >
        {text}
        {streaming && (
          <span style={{
            display: "inline-block",
            width: 7,
            height: 18,
            background: color,
            marginLeft: 2,
            borderRadius: 2,
            animation: "blink 0.8s step-end infinite",
            verticalAlign: "text-bottom",
          }} />
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// DATE NAVIGATION BAR
// ═══════════════════════════════════════════════════════════

function DateNav({ dates, activeDate, onDateClick, eventCountByDate }) {
  const scrollRef = useRef(null);

  return (
    <div
      ref={scrollRef}
      style={{
        display: "flex",
        gap: 4,
        overflowX: "auto",
        padding: "8px 0",
        scrollbarWidth: "none",
      }}
      role="tablist"
      aria-label="Transit dates"
    >
      {dates.map(d => {
        const count = eventCountByDate[d] || 0;
        const isActive = d === activeDate;
        return (
          <button
            key={d}
            role="tab"
            aria-selected={isActive}
            onClick={() => onDateClick(d)}
            style={{
              padding: "6px 14px",
              borderRadius: 10,
              border: `1.5px solid ${isActive ? "var(--accent)" : "transparent"}`,
              background: isActive ? "var(--accent-bg)" : "transparent",
              color: isActive ? "var(--accent)" : "var(--text-secondary)",
              fontSize: 13,
              fontWeight: isActive ? 600 : 400,
              cursor: "pointer",
              whiteSpace: "nowrap",
              transition: "all 0.2s ease",
              fontFamily: "inherit",
              position: "relative",
            }}
          >
            {formatDate(d)}
            {count > 1 && (
              <span style={{
                position: "absolute",
                top: -4, right: -4,
                width: 16, height: 16,
                borderRadius: 8,
                background: "var(--accent)",
                color: "#fff",
                fontSize: 10,
                fontWeight: 700,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}>{count}</span>
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
  const tenseCount = events.filter(e => isTense(e.aspect_type)).length;
  const conjCount = events.filter(e => e.aspect_type === "conjunction").length;
  const tightest = events.length > 0 ? [...events].sort((a, b) => a.orb - b.orb)[0] : null;

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
      gap: 10,
    }}>
      {[
        { label: "Всего", value: events.length, color: "var(--accent)" },
        { label: "Гармоничных", value: harmonicCount, color: "#3B82F6" },
        { label: "Напряжённых", value: tenseCount, color: "#EF4444" },
        { label: "Соединений", value: conjCount, color: "#F59E0B" },
      ].map(s => (
        <div key={s.label} style={{
          padding: "12px 14px",
          borderRadius: 10,
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
          textAlign: "center",
        }}>
          <div style={{ fontSize: 24, fontWeight: 700, color: s.color }}>{s.value}</div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2, fontWeight: 500, letterSpacing: "0.02em" }}>
            {s.label}
          </div>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════

export default function TransitTimeline() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [planetFilter, setPlanetFilter] = useState([]);
  const [aspectFilter, setAspectFilter] = useState([]);
  const [orbFilter, setOrbFilter] = useState(2.0);
  const [activeDate, setActiveDate] = useState(null);

  // Simulate loading
  useEffect(() => {
    const timer = setTimeout(() => {
      setEvents(MOCK_EVENTS);
      setLoading(false);
    }, 1200);
    return () => clearTimeout(timer);
  }, []);

  // Filtered events
  const filteredEvents = useMemo(() => {
    return events.filter(e => {
      if (planetFilter.length > 0 && !planetFilter.includes(e.transit_planet)) return false;
      if (aspectFilter.length > 0 && !aspectFilter.includes(e.aspect_type)) return false;
      if (e.orb > orbFilter) return false;
      if (activeDate && e.date !== activeDate) return false;
      return true;
    });
  }, [events, planetFilter, aspectFilter, orbFilter, activeDate]);

  // Unique dates for nav
  const dates = useMemo(() => [...new Set(events.map(e => e.date))].sort(), [events]);
  const eventCountByDate = useMemo(() => {
    const counts = {};
    events.forEach(e => { counts[e.date] = (counts[e.date] || 0) + 1; });
    return counts;
  }, [events]);

  const handleEventClick = useCallback((event) => {
    setSelectedEvent(prev => prev === event ? null : event);
  }, []);

  return (
    <div style={{
      fontFamily: "'DM Sans', 'Segoe UI', system-ui, sans-serif",
      maxWidth: 900,
      margin: "0 auto",
      padding: "24px 16px",
      color: "var(--text-primary)",
      minHeight: "100vh",
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

        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }

        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @keyframes blink {
          50% { opacity: 0; }
        }

        * { box-sizing: border-box; }

        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

        button:focus-visible {
          outline: 2px solid var(--accent);
          outline-offset: 2px;
        }

        input[type="range"] {
          height: 4px;
          border-radius: 2px;
          appearance: auto;
        }
      `}</style>

      {/* Title */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{
          fontSize: 26, fontWeight: 700, margin: 0,
          background: "linear-gradient(135deg, var(--accent), #A78BFA)",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          letterSpacing: "-0.02em",
        }}>
          Транзиты
        </h1>
        <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: "6px 0 0" }}>
          Апрель 2026 • 30 дней
        </p>
      </div>

      {/* Stats */}
      {!loading && <StatsSummary events={filteredEvents} />}

      {/* Date nav */}
      {!loading && dates.length > 0 && (
        <div style={{ margin: "16px 0" }}>
          <DateNav
            dates={dates}
            activeDate={activeDate}
            onDateClick={d => setActiveDate(prev => prev === d ? null : d)}
            eventCountByDate={eventCountByDate}
          />
        </div>
      )}

      {/* Filters */}
      <div style={{ margin: "12px 0 16px" }}>
        <FilterBar
          planetFilter={planetFilter}
          setPlanetFilter={setPlanetFilter}
          aspectFilter={aspectFilter}
          setAspectFilter={setAspectFilter}
          orbFilter={orbFilter}
          setOrbFilter={setOrbFilter}
        />
      </div>

      {/* Layout: events list + interpretation panel */}
      <div style={{
        display: "grid",
        gridTemplateColumns: selectedEvent ? "1fr 1fr" : "1fr",
        gap: 16,
        alignItems: "start",
        transition: "grid-template-columns 0.3s ease",
      }}>
        {/* Events list */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => <EventCardSkeleton key={i} />)
          ) : filteredEvents.length === 0 ? (
            <div style={{
              padding: 40,
              textAlign: "center",
              color: "var(--text-secondary)",
              fontSize: 14,
              borderRadius: 12,
              border: "1px dashed var(--border)",
            }}>
              Нет транзитов с текущими фильтрами.
              <br />
              <span style={{ fontSize: 12, opacity: 0.7 }}>
                Попробуйте увеличить орб или сбросить фильтры.
              </span>
            </div>
          ) : (
            filteredEvents.map((event, idx) => (
              <EventCard
                key={`${event.date}-${event.transit_planet}-${event.natal_planet}-${event.aspect_type}`}
                event={event}
                index={idx}
                isSelected={selectedEvent === event}
                onClick={() => handleEventClick(event)}
              />
            ))
          )}
        </div>

        {/* Interpretation panel */}
        {selectedEvent && (
          <div style={{ position: "sticky", top: 24 }}>
            <InterpretationPanel
              event={selectedEvent}
              onClose={() => setSelectedEvent(null)}
            />
          </div>
        )}
      </div>

      {/* Footer */}
      {!loading && (
        <div style={{
          marginTop: 32,
          padding: "16px 0",
          borderTop: "1px solid var(--border)",
          fontSize: 12,
          color: "var(--text-secondary)",
          textAlign: "center",
          opacity: 0.6,
        }}>
          Транзитные орбы: соединение/оппозиция ≤ 2° • квадрат ≤ 2° • трин/секстиль ≤ 1.5°
          <br />
          Нажмите на транзит для AI-интерпретации
        </div>
      )}
    </div>
  );
}
