import { useState, useEffect, useRef, useMemo, useCallback } from "react";

// ═══════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════

const MOCK_EVENTS = [
  { date: "2026-04-03", transit_planet: "Venus",   natal_planet: "Sun",    aspect_type: "trine",       orb: 0.4, exact_date: "2026-04-03T14:22", transit_sign: "Pisces",   natal_sign: "Capricorn" },
  { date: "2026-04-05", transit_planet: "Mercury", natal_planet: "Jupiter",aspect_type: "sextile",     orb: 1.1, exact_date: "2026-04-05T08:15", transit_sign: "Aries",    natal_sign: "Sagittarius" },
  { date: "2026-04-07", transit_planet: "Mars",    natal_planet: "Moon",   aspect_type: "square",      orb: 0.8, exact_date: "2026-04-07T19:40", transit_sign: "Cancer",   natal_sign: "Cancer" },
  { date: "2026-04-09", transit_planet: "Sun",     natal_planet: "Saturn", aspect_type: "square",      orb: 1.5, exact_date: "2026-04-09T06:10", transit_sign: "Aries",    natal_sign: "Capricorn" },
  { date: "2026-04-11", transit_planet: "Jupiter", natal_planet: "Sun",    aspect_type: "conjunction", orb: 0.2, exact_date: "2026-04-11T11:33", transit_sign: "Cancer",   natal_sign: "Capricorn" },
  { date: "2026-04-13", transit_planet: "Saturn",  natal_planet: "Venus",  aspect_type: "trine",       orb: 0.9, exact_date: "2026-04-13T22:05", transit_sign: "Aries",    natal_sign: "Aquarius" },
  { date: "2026-04-15", transit_planet: "Venus",   natal_planet: "Mars",   aspect_type: "opposition",  orb: 0.6, exact_date: "2026-04-15T16:48", transit_sign: "Aries",    natal_sign: "Taurus" },
  { date: "2026-04-17", transit_planet: "Mercury", natal_planet: "Neptune",aspect_type: "conjunction", orb: 1.3, exact_date: "2026-04-17T03:20", transit_sign: "Aries",    natal_sign: "Aquarius" },
  { date: "2026-04-18", transit_planet: "Uranus",  natal_planet: "Mercury",aspect_type: "square",      orb: 0.3, exact_date: "2026-04-18T09:55", transit_sign: "Gemini",   natal_sign: "Sagittarius" },
  { date: "2026-04-20", transit_planet: "Mars",    natal_planet: "Sun",    aspect_type: "opposition",  orb: 1.0, exact_date: "2026-04-20T12:30", transit_sign: "Cancer",   natal_sign: "Capricorn" },
  { date: "2026-04-22", transit_planet: "Neptune", natal_planet: "Moon",   aspect_type: "trine",       orb: 0.7, exact_date: "2026-04-22T07:15", transit_sign: "Aries",    natal_sign: "Cancer" },
  { date: "2026-04-24", transit_planet: "Pluto",   natal_planet: "Saturn", aspect_type: "conjunction", orb: 0.1, exact_date: "2026-04-24T18:40", transit_sign: "Aquarius", natal_sign: "Capricorn" },
  { date: "2026-04-26", transit_planet: "Sun",     natal_planet: "Uranus", aspect_type: "square",      orb: 1.8, exact_date: "2026-04-26T15:00", transit_sign: "Taurus",   natal_sign: "Aquarius" },
  { date: "2026-04-28", transit_planet: "Venus",   natal_planet: "Jupiter",aspect_type: "conjunction", orb: 0.5, exact_date: "2026-04-28T10:22", transit_sign: "Aries",    natal_sign: "Sagittarius" },
  { date: "2026-04-30", transit_planet: "Saturn",  natal_planet: "Moon",   aspect_type: "square",      orb: 1.2, exact_date: "2026-04-30T21:45", transit_sign: "Aries",    natal_sign: "Cancer" },
];

const MOCK_INTERPRETATIONS = {
  "Jupiter conjunction Sun": "Транзит Юпитера в соединении с вашим натальным Солнцем — один из самых благоприятных транзитов, который случается раз в 12 лет.\n\nЭто период расширения возможностей, когда ваша уверенность в себе растёт, а жизнь словно открывает перед вами новые двери. Юпитер усиливает всё, к чему прикасается, и в данном случае он усиливает вашу жизненную силу, самовыражение и чувство цели.\n\nОбратите внимание на возможности в сфере карьеры и личного развития. Это не время скромничать — Юпитер вознаграждает смелость и оптимизм.\n\nРекомендация: используйте этот период для запуска проектов, которые давно откладывали. Энергия благоприятствует масштабному мышлению.",
  "Pluto conjunction Saturn": "Транзит Плутона в соединении с вашим натальным Сатурном — глубокий и трансформирующий процесс, который затрагивает сами основы вашей жизненной структуры.\n\nСатурн отвечает за правила, границы, дисциплину и то, как вы организуете свою жизнь. Плутон приходит и проверяет: насколько эти структуры подлинны?\n\nЭтот транзит может ощущаться как давление со стороны обстоятельств: карьерные изменения, перестройка жизненных приоритетов. Но его цель — не разрушение, а обновление.\n\nТо, что выдержит этот транзит, станет несокрушимым фундаментом для следующего этапа вашей жизни.",
  "Uranus square Mercury": "Транзит Урана в квадрате к вашему натальному Меркурию вносит электрическое напряжение в сферу мышления и коммуникации.\n\nВы можете обнаружить, что привычные способы думать и общаться перестают работать. Неожиданные идеи, внезапные озарения, но также нервозность и рассеянность — всё это проявления этого аспекта.\n\nРекомендация: записывайте идеи, но не торопитесь с их реализацией. Перепроверяйте важные документы и договоры.",
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
  conjunction: "#C08020",
  sextile:     "#3068B0",
  square:      "#C03030",
  trine:       "#3068B0",
  opposition:  "#C03030",
};

const ASPECT_BG = {
  conjunction: "rgba(192,128,32,0.08)",
  sextile:     "rgba(48,104,176,0.08)",
  square:      "rgba(192,48,48,0.08)",
  trine:       "rgba(48,104,176,0.08)",
  opposition:  "rgba(192,48,48,0.08)",
};

const PLANET_ACCENT = {
  Sun:          "#D4840A",
  Moon:         "#7A8BA0",
  Mercury:      "#7060C0",
  Venus:        "#C04870",
  Mars:         "#B83030",
  Jupiter:      "#3868B0",
  Saturn:       "#6A6050",
  Uranus:       "#2090A8",
  Neptune:      "#6050B8",
  Pluto:        "#902020",
  "North Node": "#308858",
};

const ASPECT_LABELS_RU = {
  conjunction: "Соединение", sextile: "Секстиль", square: "Квадрат",
  trine: "Трин", opposition: "Оппозиция",
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

function isHarmonic(aspect) { return aspect === "trine" || aspect === "sextile"; }
function isTense(aspect)    { return aspect === "square" || aspect === "opposition"; }

// Возвращает индекс события, которое открыто для free-пользователей
// (первый транзит Венеры или Юпитера с позитивным аспектом)
function getFreeUnlockedIndex(events) {
  const idx = events.findIndex(
    e => (e.transit_planet === "Venus" || e.transit_planet === "Jupiter") && isHarmonic(e.aspect_type)
  );
  return idx >= 0 ? idx : 0; // fallback — первое событие
}

// ═══════════════════════════════════════════════════════════
// SKELETON LOADER
// ═══════════════════════════════════════════════════════════

function Skeleton({ width = "100%", height = 16, radius = 8, style = {} }) {
  return (
    <div style={{
      width, height, borderRadius: radius,
      background: "linear-gradient(90deg, #F0EAF8 25%, #F8F3FF 50%, #F0EAF8 75%)",
      backgroundSize: "200% 100%",
      animation: "shimmer 1.8s ease-in-out infinite",
      ...style,
    }} />
  );
}

function EventCardSkeleton() {
  return (
    <div style={{
      padding: "16px 18px", borderRadius: 16,
      border: "1px solid #F0EAF8", background: "#FFFFFF",
      display: "flex", flexDirection: "column", gap: 8,
      borderLeft: "4px solid #E8DEF8",
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
  const toggle = (s) => setExpandedSection(prev => prev === s ? null : s);

  const chipStyle = (active) => ({
    padding: "5px 13px", borderRadius: 20,
    border: `1.5px solid ${active ? "#C0A0E8" : "#E8DEF8"}`,
    background: active ? "#F0E8FF" : "transparent",
    color: active ? "#7040A8" : "#9080B0",
    fontSize: 13, fontWeight: active ? 600 : 400,
    cursor: "pointer", transition: "all 0.2s ease",
    whiteSpace: "nowrap", userSelect: "none", fontFamily: "inherit",
  });

  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 10,
      padding: "14px 16px", background: "#FFFFFF",
      borderRadius: 16, border: "1px solid #F0EAF8",
      boxShadow: "0 4px 16px -4px rgba(224,195,252,0.2)",
    }}>
      <div>
        <button onClick={() => toggle("planets")} style={filterLabelStyle}>
          <span>Планеты</span>
          <span style={{ fontSize: 10, transform: expandedSection === "planets" ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>▼</span>
          {planetFilter.length > 0 && planetFilter.length < ALL_PLANETS.length && (
            <span style={{ background: "#C0A0E8", color: "#fff", borderRadius: 10, padding: "1px 7px", fontSize: 11, fontWeight: 700 }}>{planetFilter.length}</span>
          )}
        </button>
        {expandedSection === "planets" && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {ALL_PLANETS.map(p => (
              <button key={p} style={chipStyle(planetFilter.includes(p))} onClick={() =>
                setPlanetFilter(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p])
              }>{PLANET_GLYPHS[p]} {PLANET_LABELS_RU[p]}</button>
            ))}
          </div>
        )}
      </div>
      <div>
        <button onClick={() => toggle("aspects")} style={filterLabelStyle}>
          <span>Аспекты</span>
          <span style={{ fontSize: 10, transform: expandedSection === "aspects" ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>▼</span>
        </button>
        {expandedSection === "aspects" && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {ALL_ASPECTS.map(a => (
              <button key={a} style={chipStyle(aspectFilter.includes(a))} onClick={() =>
                setAspectFilter(prev => prev.includes(a) ? prev.filter(x => x !== a) : [...prev, a])
              }><span style={{ color: ASPECT_COLORS[a] }}>{ASPECT_SYMBOLS[a]}</span> {ASPECT_LABELS_RU[a]}</button>
            ))}
          </div>
        )}
      </div>
      <div>
        <button onClick={() => toggle("orb")} style={filterLabelStyle}>
          <span>Орб ≤ {orbFilter}°</span>
          <span style={{ fontSize: 10, transform: expandedSection === "orb" ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>▼</span>
        </button>
        {expandedSection === "orb" && (
          <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 12 }}>
            <input type="range" min={0.5} max={3} step={0.5} value={orbFilter}
              onChange={e => setOrbFilter(Number(e.target.value))}
              style={{ flex: 1, accentColor: "#C0A0E8" }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: "#5A3880", minWidth: 28 }}>{orbFilter}°</span>
          </div>
        )}
      </div>
      {(planetFilter.length > 0 || aspectFilter.length > 0 || orbFilter !== 2.0) && (
        <button onClick={() => { setPlanetFilter([]); setAspectFilter([]); setOrbFilter(2.0); }} style={{
          alignSelf: "flex-start", background: "none",
          border: "1px solid #E8DEF8", color: "#9080B0",
          borderRadius: 10, padding: "4px 12px", fontSize: 12,
          cursor: "pointer", fontFamily: "inherit",
        }}>Сбросить фильтры</button>
      )}
    </div>
  );
}

const filterLabelStyle = {
  background: "none", border: "none", color: "#9080B0",
  fontSize: 12, fontWeight: 600, letterSpacing: "0.05em",
  textTransform: "uppercase", cursor: "pointer", padding: 0,
  display: "flex", alignItems: "center", gap: 6, fontFamily: "inherit",
};

// ═══════════════════════════════════════════════════════════
// DATE NAV
// ═══════════════════════════════════════════════════════════

function DateNav({ dates, activeDate, onDateClick, eventCountByDate }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (activeDate && scrollRef.current) {
      const idx = dates.indexOf(activeDate);
      if (idx >= 0) scrollRef.current.children[idx]?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    }
  }, [activeDate, dates]);

  return (
    <div ref={scrollRef} style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 6, scrollbarWidth: "none", msOverflowStyle: "none" }}>
      {dates.map(d => {
        const active  = d === activeDate;
        const count   = eventCountByDate[d] || 0;
        const dt      = new Date(d + "T00:00:00");
        return (
          <button key={d} onClick={() => onDateClick(d)} style={{
            minWidth: 48, flexShrink: 0,
            display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
            padding: "8px 6px", borderRadius: 12,
            border: `1.5px solid ${active ? "#C0A0E8" : "#E8DEF8"}`,
            background: active ? "#F0E8FF" : "#FFFFFF",
            color: active ? "#7040A8" : "#9080B0",
            cursor: "pointer", transition: "all 0.2s", fontFamily: "inherit",
          }}>
            <span style={{ fontSize: 11, opacity: 0.7 }}>{dt.toLocaleDateString("ru-RU", { weekday: "short" })}</span>
            <span style={{ fontSize: 15, fontWeight: active ? 700 : 500 }}>{dt.getDate()}</span>
            {count > 0 && <span style={{ width: 6, height: 6, borderRadius: 3, background: active ? "#C0A0E8" : "#D8CEF0" }} />}
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
  const stats = [
    { label: "Всего",        value: events.length,                                          color: "#7040A8", bg: "#F5F0FF" },
    { label: "Гармоничных",  value: events.filter(e => isHarmonic(e.aspect_type)).length,   color: "#3068B0", bg: "#EAF1FF" },
    { label: "Напряжённых",  value: events.filter(e => isTense(e.aspect_type)).length,      color: "#C03030", bg: "#FFF0F0" },
    { label: "Соединений",   value: events.filter(e => e.aspect_type === "conjunction").length, color: "#C08020", bg: "#FFF8E8" },
  ];
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      {stats.map(({ label, value, color, bg }) => (
        <div key={label} style={{ flex: "1 1 80px", padding: "12px 14px", borderRadius: 14, border: "1px solid #F0EAF8", background: bg, display: "flex", flexDirection: "column", gap: 3 }}>
          <span style={{ fontSize: 22, fontWeight: 800, color }}>{value}</span>
          <span style={{ fontSize: 11, color: "#9080B0" }}>{label}</span>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// FREE PLAN BANNER
// ═══════════════════════════════════════════════════════════

function FreePlanBanner({ lockedCount, featuredTransit, onUpgrade }) {
  return (
    <div style={{
      margin: "8px 0", padding: "16px 20px", borderRadius: 16,
      background: "linear-gradient(135deg, #F5F0FF, #FFF0F8)",
      border: "1.5px solid #E0D0F8",
      display: "flex", flexDirection: "column", gap: 10,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#5A2880", marginBottom: 3 }}>
            ✨ Ещё {lockedCount} активных транзитов скрыто
          </div>
          <div style={{ fontSize: 12, color: "#9070B0" }}>
            Перейдите на Pro, чтобы видеть полный прогноз с AI-интерпретациями
          </div>
        </div>
        <button onClick={onUpgrade} style={{
          padding: "9px 20px", borderRadius: 12, border: "none",
          background: "linear-gradient(135deg, #9060C8, #C060A0)",
          color: "#fff", fontSize: 13, fontWeight: 700,
          cursor: "pointer", whiteSpace: "nowrap", fontFamily: "inherit",
          boxShadow: "0 4px 12px -2px rgba(144,96,200,0.4)",
        }}>
          Открыть Pro
        </button>
      </div>
      {featuredTransit && (
        <div onClick={onUpgrade} style={{
          padding: "10px 14px", borderRadius: 12, cursor: "pointer",
          background: "rgba(48,104,176,0.06)", border: "1px solid rgba(48,104,176,0.15)",
        }}>
          <span style={{ fontSize: 13, color: "#3068B0", fontWeight: 600 }}>
            {PLANET_GLYPHS[featuredTransit.transit_planet]} {PLANET_LABELS_RU[featuredTransit.transit_planet]}{" "}
            {ASPECT_LABELS_RU[featuredTransit.aspect_type]?.toLowerCase()}{" "}
            {PLANET_LABELS_RU[featuredTransit.natal_planet]}
          </span>
          <span style={{ fontSize: 12, color: "#6090C0", marginLeft: 8 }}>
            — один из лучших периодов. Разблокировать?
          </span>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// EVENT CARD
// ═══════════════════════════════════════════════════════════

function EventCard({ event, index, isSelected, onClick, blurred, onUpgrade }) {
  const [hovered, setHovered] = useState(false);
  const aspectColor  = ASPECT_COLORS[event.aspect_type] || "#7040A8";
  const aspectBg     = ASPECT_BG[event.aspect_type]    || "rgba(112,64,168,0.06)";
  const planetAccent = PLANET_ACCENT[event.transit_planet] || "#C0A0E8";
  const displayDate  = event.peak_date || event.exact_date || event.date || "";

  // Формируем текст для hover-попапа
  const hoverText = blurred
    ? `${PLANET_GLYPHS[event.transit_planet] || "★"} ${PLANET_LABELS_RU[event.transit_planet] || event.transit_planet} ${ASPECT_LABELS_RU[event.aspect_type]?.toLowerCase() || event.aspect_type} ${PLANET_LABELS_RU[event.natal_planet] || event.natal_planet} (${displayDate ? formatDate(displayDate) : ""}) — ${isHarmonic(event.aspect_type) ? "один из лучших периодов года" : "важный транзит для вашего развития"}. Разблокировать?`
    : "";

  return (
    <div
      onClick={blurred ? onUpgrade : onClick}
      onMouseEnter={() => blurred && setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: "14px 16px", borderRadius: 16, cursor: "pointer",
        border: `1px solid ${isSelected ? "#D0B8F0" : "#F0EAF8"}`,
        borderLeft: `4px solid ${planetAccent}`,
        background: isSelected ? aspectBg : "#FFFFFF",
        boxShadow: isSelected ? "0 8px 20px -6px rgba(224,195,252,0.35)" : "0 2px 8px -4px rgba(200,180,240,0.15)",
        transition: "all 0.2s ease",
        animation: `fadeSlideIn 0.3s ease ${index * 0.04}s both`,
        // blur для заблокированных карточек — 80% opacity + blur
        filter: blurred ? "blur(5px)" : "none",
        opacity: blurred ? 0.4 : 1,
        userSelect: blurred ? "none" : "auto",
        pointerEvents: "auto",
        position: "relative",
      }}
    >
      {/* Hover-попап на заблюренных карточках */}
      {blurred && hovered && (
        <div style={{
          position: "absolute", inset: 0, zIndex: 10,
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: "12px 16px", borderRadius: 16,
          background: "rgba(255,255,255,0.97)",
          border: "1.5px solid #E0D0F8",
          boxShadow: "0 8px 24px -4px rgba(144,96,200,0.25)",
          filter: "none", opacity: 1,
          animation: "fadeSlideIn 0.2s ease",
        }}>
          <span style={{ fontSize: 13, color: "#5A2880", fontWeight: 500, lineHeight: 1.5, textAlign: "center" }}>
            {hoverText}
          </span>
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "#9080B0" }}>{displayDate ? formatDate(displayDate) : ""}</span>
          {event.exact_date && <span style={{ fontSize: 10, color: "#B0A0C8", opacity: 0.7 }}>{formatExactTime(event.exact_date)}</span>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {event.applying !== undefined && (
            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 8, border: `1px solid ${event.applying ? "rgba(48,104,176,0.3)" : "#E8DEF8"}`, color: event.applying ? "#3068B0" : "#9080B0", background: event.applying ? "rgba(48,104,176,0.06)" : "transparent" }}>
              {event.applying ? "→ точный" : "← отходит"}
            </span>
          )}
          <span style={{ fontSize: 11, color: "#B0A0C8", opacity: 0.7 }}>орб {(event.peak_orb ?? event.orb ?? 0).toFixed(1)}°</span>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 20 }}>{PLANET_GLYPHS[event.transit_planet] || "★"}</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: "#2D2540" }}>{PLANET_LABELS_RU[event.transit_planet] || event.transit_planet}</span>
        <span style={{ fontSize: 16, color: aspectColor, fontWeight: 700 }}>{ASPECT_SYMBOLS[event.aspect_type] || "·"}</span>
        <span style={{ fontSize: 13, color: "#9080B0" }}>{ASPECT_LABELS_RU[event.aspect_type] || event.aspect_type}</span>
        <span style={{ fontSize: 20 }}>{PLANET_GLYPHS[event.natal_planet] || "☽"}</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: "#2D2540" }}>{PLANET_LABELS_RU[event.natal_planet] || event.natal_planet}</span>
      </div>
      {(event.transit_sign || event.natal_sign) && (
        <div style={{ marginTop: 5, fontSize: 12, color: "#B0A0C8" }}>{event.transit_sign} → {event.natal_sign}</div>
      )}
      {isSelected && !blurred && <div style={{ marginTop: 8, fontSize: 11, color: aspectColor, fontWeight: 600 }}>Нажмите для интерпретации ↓</div>}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// INTERPRETATION PANEL
// ═══════════════════════════════════════════════════════════

function InterpretationPanel({ event, onClose }) {
  const [text, setText]       = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const scrollRef = useRef(null);

  const key     = `${PLANET_LABELS_RU[event.transit_planet] || event.transit_planet} ${ASPECT_LABELS_RU[event.aspect_type] || event.aspect_type} ${PLANET_LABELS_RU[event.natal_planet] || event.natal_planet}`;
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
        setText(`Интерпретация транзита: ${key}.\n\nЭтот аспект влияет на сферу жизни, связанную с натальной планетой. Рекомендуется обратить внимание на события этого периода.`);
        setLoading(false);
      }, 800);
      return;
    }

    const token = localStorage.getItem('astro_access_token');
    const ctrl  = new AbortController();
    fetch(`https://astro-production-abcc.up.railway.app/api/v1/chart/${event.chartId}/transits/event/interpret`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ transit_planet: event.transit_planet, natal_planet: event.natal_planet, aspect_type: event.aspect_type }),
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
    <div style={{ background: "#FFFFFF", borderRadius: 18, border: "1px solid #E8DEF8", boxShadow: "0 8px 24px -6px rgba(224,195,252,0.30)", animation: "fadeSlideIn 0.3s ease" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #F0EAF8", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#2D2540" }}>{key}</div>
        <button onClick={onClose} style={{ background: "none", border: "none", color: "#B0A0C8", fontSize: 18, cursor: "pointer", padding: "2px 6px", borderRadius: 8, fontFamily: "inherit" }}>✕</button>
      </div>
      <div ref={scrollRef} style={{ padding: 16, maxHeight: 400, overflowY: "auto" }}>
        {loading && !text && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[90, 70, 85, 60].map((w, i) => <Skeleton key={i} width={`${w}%`} height={13} />)}
          </div>
        )}
        {error && <div style={{ color: "#C03030", fontSize: 13 }}>{error}</div>}
        {text && (
          <div style={{ fontSize: 13, lineHeight: 1.75, color: "#2D2540", whiteSpace: "pre-wrap" }}>
            {text}
            {loading && <span style={{ display: "inline-block", width: 6, height: 14, background: "#C0A0E8", marginLeft: 2, borderRadius: 2, animation: "blink 0.8s step-end infinite", verticalAlign: "text-bottom" }} />}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════

export default function TransitTimeline({ chartId, onDateSelect, mockMode, userTier, onUpgrade }) {
  const [events,        setEvents]        = useState([]);
  const [loading,       setLoading]       = useState(true);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [planetFilter,  setPlanetFilter]  = useState([]);
  const [aspectFilter,  setAspectFilter]  = useState([]);
  const [orbFilter,     setOrbFilter]     = useState(2.0);
  const [activeDate,    setActiveDate]    = useState(null);

  const isFree = userTier === "free";
  const isLite = userTier === "lite";
  const hasFullAccess = userTier === "pro" || userTier === "premium";

  useEffect(() => {
    if (!chartId || mockMode || chartId === 'anonymous') { setEvents(MOCK_EVENTS); setLoading(false); return; }
    setLoading(true);
    const today = new Date();
    const from  = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);
    const to    = new Date(today.getFullYear(), today.getMonth() + 2, 0).toISOString().slice(0, 10);
    const token = localStorage.getItem('astro_access_token');
    fetch(`https://astro-production-abcc.up.railway.app/api/v1/chart/${chartId}/transits?from_date=${from}&to_date=${to}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.json())
      .then(data => { setEvents(data.events || []); setLoading(false); })
      .catch(() => { setEvents(MOCK_EVENTS); setLoading(false); });
  }, [chartId, mockMode]);

  // ── Логика видимости транзитов ──
  // Free: первые 2 недели + 1 позитивный транзит (Venus/Jupiter trine/sextile)
  // Lite: все транзиты видны (без AI-интерпретации)
  // Pro/Premium: полный доступ
  const twoWeeksFromNow = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + 14);
    return d.toISOString().slice(0, 10);
  }, []);

  const featuredTransitIndex = useMemo(() => {
    if (hasFullAccess || isLite) return -1;
    return events.findIndex(e => {
      const eventDate = e.start_date || e.peak_date || e.date;
      const isAfterTwoWeeks = eventDate > twoWeeksFromNow;
      const isPositive = ['jupiter', 'venus'].includes(e.transit_planet.toLowerCase()) &&
                         ['trine', 'sextile'].includes(e.aspect_type);
      return isAfterTwoWeeks && isPositive;
    });
  }, [events, twoWeeksFromNow, hasFullAccess, isLite]);

  const isEventVisible = useCallback((event, idx) => {
    if (hasFullAccess || isLite) return true;
    // Free: visible if within 2 weeks
    const eventDate = event.start_date || event.peak_date || event.date;
    if (eventDate <= twoWeeksFromNow) return true;
    // Free: featured positive transit is visible
    if (idx === featuredTransitIndex) return true;
    return false;
  }, [hasFullAccess, isLite, twoWeeksFromNow, featuredTransitIndex]);

  const filteredEvents = useMemo(() => {
    return events.filter(e => {
      if (planetFilter.length > 0 && !planetFilter.includes(e.transit_planet)) return false;
      if (aspectFilter.length > 0 && !aspectFilter.includes(e.aspect_type))    return false;
      if ((e.peak_orb ?? e.orb) > orbFilter) return false;
      if (activeDate) {
        const s  = e.start_date || e.date;
        const en = e.end_date   || e.date;
        if (activeDate < s || activeDate > en) return false;
      }
      return true;
    });
  }, [events, planetFilter, aspectFilter, orbFilter, activeDate]);

  const hiddenCount = useMemo(() => {
    if (hasFullAccess || isLite) return 0;
    return filteredEvents.filter((e, idx) => !isEventVisible(e, events.indexOf(e))).length;
  }, [filteredEvents, events, hasFullAccess, isLite, isEventVisible]);

  const dates            = useMemo(() => [...new Set(events.map(e => e.peak_date || e.date))].sort(), [events]);
  const eventCountByDate = useMemo(() => {
    const counts = {};
    events.forEach(e => { counts[e.peak_date || e.date] = (counts[e.peak_date || e.date] || 0) + 1; });
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
    if (chartId && chartId !== 'anonymous' && !mockMode) {
      try {
        const token = localStorage.getItem('astro_access_token');
        const resp = await fetch(`https://astro-production-abcc.up.railway.app/api/v1/chart/${chartId}/transits/positions?on_date=${next}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (resp.ok) { const data = await resp.json(); positions = data.planets || []; }
      } catch {}
    }
    onDateSelect(next, dayEvents, positions);
  }, [activeDate, events, onDateSelect, chartId, mockMode]);

  const handleUpgrade = useCallback(() => {
    if (onUpgrade) onUpgrade('lite_to_pro');
  }, [onUpgrade]);

  return (
    <div style={{ fontFamily: "'Space Grotesk', 'DM Sans', system-ui, sans-serif", maxWidth: 900, margin: "0 auto", padding: "24px 16px", color: "#2D2540" }}>
      <style>{`
        @keyframes shimmer     { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        @keyframes fadeSlideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes blink       { 50% { opacity: 0; } }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #E8DEF8; border-radius: 3px; }
        button:focus-visible { outline: 2px solid #C0A0E8; outline-offset: 2px; }
        input[type="range"] { height: 4px; border-radius: 2px; }
      `}</style>

      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, margin: 0, background: "linear-gradient(135deg, #9060C8, #E080B0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", letterSpacing: "-0.02em" }}>
          Транзиты
        </h1>
        <p style={{ fontSize: 14, color: "#9080B0", margin: "6px 0 0" }}>
          {new Date().toLocaleDateString("ru-RU", { month: "long", year: "numeric" })}
        </p>
      </div>

      {!loading && <StatsSummary events={filteredEvents} />}

      {!loading && dates.length > 0 && (
        <div style={{ margin: "16px 0" }}>
          <DateNav dates={dates} activeDate={activeDate} onDateClick={d => handleDateClick(d)} eventCountByDate={eventCountByDate} />
        </div>
      )}

      <div style={{ margin: "12px 0 16px" }}>
        <FilterBar planetFilter={planetFilter} setPlanetFilter={setPlanetFilter} aspectFilter={aspectFilter} setAspectFilter={setAspectFilter} orbFilter={orbFilter} setOrbFilter={setOrbFilter} />
      </div>

      {!loading && isFree && hiddenCount > 0 && (
        <FreePlanBanner
          lockedCount={hiddenCount}
          featuredTransit={featuredTransitIndex >= 0 ? events[featuredTransitIndex] : null}
          onUpgrade={handleUpgrade}
        />
      )}

      <div style={{ display: "grid", gridTemplateColumns: selectedEvent ? "1fr 1fr" : "1fr", gap: 16, alignItems: "start", transition: "grid-template-columns 0.3s ease" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => <EventCardSkeleton key={i} />)
          ) : filteredEvents.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: "#9080B0", fontSize: 14, borderRadius: 16, border: "1.5px dashed #E8DEF8", background: "#FDFBF9" }}>
              Нет транзитов с текущими фильтрами.<br />
              <span style={{ fontSize: 12, opacity: 0.7 }}>Попробуйте увеличить орб или сбросить фильтры.</span>
            </div>
          ) : (
            filteredEvents.map((event, idx) => {
              const globalIdx = events.indexOf(event);
              const visible = isEventVisible(event, globalIdx);
              return (
                <EventCard
                  key={`${event.peak_date||event.start_date||event.date}-${event.transit_planet}-${event.natal_planet}-${event.aspect_type}`}
                  event={event} index={idx}
                  isSelected={selectedEvent === event}
                  onClick={() => handleEventClick(event)}
                  blurred={!visible}
                  onUpgrade={handleUpgrade}
                />
              );
            })
          )}
        </div>
        {selectedEvent && (
          <div style={{ position: "sticky", top: 24 }}>
            <InterpretationPanel event={selectedEvent} onClose={() => setSelectedEvent(null)} />
          </div>
        )}
      </div>

      {!loading && (
        <div style={{ marginTop: 32, padding: "16px 0", borderTop: "1px solid #F0EAF8", fontSize: 12, color: "#B0A0C8", textAlign: "center", opacity: 0.8 }}>
          Транзитные орбы: соединение/оппозиция ≤ 2° · квадрат ≤ 2° · трин/секстиль ≤ 1.5°<br />
          Нажмите на транзит для AI-интерпретации
        </div>
      )}
    </div>
  );
}
