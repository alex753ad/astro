import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import MotionButton from "./MotionButton";
import { API_BASE } from "../config";
import { TIER_NAMES } from "../constants";

// ═══════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════

const MOCK_EVENTS = [
  { date: "2026-05-20", transit_planet: "Venus",   natal_planet: "Sun",    aspect_type: "trine",       orb: 0.4, exact_date: "2026-05-20T14:22", transit_sign: "Pisces",   natal_sign: "Capricorn" },
  { date: "2026-05-23", transit_planet: "Mercury", natal_planet: "Jupiter",aspect_type: "sextile",     orb: 1.1, exact_date: "2026-05-23T08:15", transit_sign: "Aries",    natal_sign: "Sagittarius" },
  { date: "2026-05-26", transit_planet: "Mars",    natal_planet: "Moon",   aspect_type: "square",      orb: 0.8, exact_date: "2026-05-26T19:40", transit_sign: "Cancer",   natal_sign: "Cancer" },
  { date: "2026-05-29", transit_planet: "Sun",     natal_planet: "Saturn", aspect_type: "square",      orb: 1.5, exact_date: "2026-05-29T06:10", transit_sign: "Aries",    natal_sign: "Capricorn" },
  { date: "2026-06-02", transit_planet: "Jupiter", natal_planet: "Sun",    aspect_type: "conjunction", orb: 0.2, exact_date: "2026-06-02T11:33", transit_sign: "Cancer",   natal_sign: "Capricorn" },
  { date: "2026-06-05", transit_planet: "Saturn",  natal_planet: "Venus",  aspect_type: "trine",       orb: 0.9, exact_date: "2026-06-05T22:05", transit_sign: "Aries",    natal_sign: "Aquarius" },
  { date: "2026-06-08", transit_planet: "Venus",   natal_planet: "Mars",   aspect_type: "opposition",  orb: 0.6, exact_date: "2026-06-08T16:48", transit_sign: "Aries",    natal_sign: "Taurus" },
  { date: "2026-06-11", transit_planet: "Mercury", natal_planet: "Neptune",aspect_type: "conjunction", orb: 1.3, exact_date: "2026-06-11T03:20", transit_sign: "Aries",    natal_sign: "Aquarius" },
  { date: "2026-06-14", transit_planet: "Uranus",  natal_planet: "Mercury",aspect_type: "square",      orb: 0.3, exact_date: "2026-06-14T09:55", transit_sign: "Gemini",   natal_sign: "Sagittarius" },
  { date: "2026-06-17", transit_planet: "Mars",    natal_planet: "Sun",    aspect_type: "opposition",  orb: 1.0, exact_date: "2026-06-17T12:30", transit_sign: "Cancer",   natal_sign: "Capricorn" },
  { date: "2026-06-20", transit_planet: "Neptune", natal_planet: "Moon",   aspect_type: "trine",       orb: 0.7, exact_date: "2026-06-20T07:15", transit_sign: "Aries",    natal_sign: "Cancer" },
  { date: "2026-06-23", transit_planet: "Pluto",   natal_planet: "Saturn", aspect_type: "conjunction", orb: 0.1, exact_date: "2026-06-23T18:40", transit_sign: "Aquarius", natal_sign: "Capricorn" },
  { date: "2026-06-26", transit_planet: "Sun",     natal_planet: "Uranus", aspect_type: "square",      orb: 1.8, exact_date: "2026-06-26T15:00", transit_sign: "Taurus",   natal_sign: "Aquarius" },
  { date: "2026-06-29", transit_planet: "Venus",   natal_planet: "Jupiter",aspect_type: "conjunction", orb: 0.5, exact_date: "2026-06-29T10:22", transit_sign: "Aries",    natal_sign: "Sagittarius" },
  { date: "2026-07-02", transit_planet: "Saturn",  natal_planet: "Moon",   aspect_type: "square",      orb: 1.2, exact_date: "2026-07-02T21:45", transit_sign: "Aries",    natal_sign: "Cancer" },
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

/* zodiac data-color, intentional */
const ASPECT_COLORS = {
  conjunction: "#C08020",
  sextile:     "#3068B0",
  square:      "var(--color-danger)",
  trine:       "#3068B0",
  opposition:  "var(--color-danger)",
};

const ASPECT_BG = {
  conjunction: "rgba(192,128,32,0.08)",
  sextile:     "rgba(48,104,176,0.08)",
  square:      "rgba(192,48,48,0.08)",
  trine:       "rgba(48,104,176,0.08)",
  opposition:  "rgba(192,48,48,0.08)",
};

/* zodiac data-color, intentional */
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

const SIGN_RU = {
  Aries: "Овен", Taurus: "Телец", Gemini: "Близнецы", Cancer: "Рак",
  Leo: "Лев", Virgo: "Дева", Libra: "Весы", Scorpio: "Скорпион",
  Sagittarius: "Стрелец", Capricorn: "Козерог", Aquarius: "Водолей", Pisces: "Рыбы",
};

const ALL_PLANETS = ["Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto"];
const ALL_ASPECTS = ["conjunction","sextile","square","trine","opposition"];

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr.includes("T") ? dateStr : dateStr + "T00:00:00");
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function formatExactTime(exactDate) {
  if (!exactDate) return "";
  const parts = exactDate.split("T");
  return parts[1] || "";
}

function isHarmonic(aspect) { return aspect === "trine" || aspect === "sextile"; }
function isTense(aspect)    { return aspect === "square" || aspect === "opposition"; }

// Заголовки доступа к карте: bearer (залогинен) и/или X-Chart-Token (аноним).
function chartAuthHeaders(extra = {}) {
  const token = typeof localStorage !== 'undefined' ? localStorage.getItem('astro_access_token') : null;
  const chartTok = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('chart_token') : null;
  return {
    ...extra,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(chartTok ? { 'X-Chart-Token': chartTok } : {}),
  };
}

// ── Помесячная догрузка транзитов ──────────────────────────

function addDaysISO(dateStr, days) {
  const d = new Date(dateStr + "T00:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function addMonthISO(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  return new Date(d.getFullYear(), d.getMonth() + 1, d.getDate()).toISOString().slice(0, 10);
}

function eventKey(e) {
  return `${e.peak_date || e.start_date || e.date}-${e.transit_planet}-${e.natal_planet}-${e.aspect_type}`;
}

function mergeEvents(prev, incoming) {
  const seen = new Set(prev.map(eventKey));
  const merged = prev.slice();
  for (const e of incoming) {
    const k = eventKey(e);
    if (!seen.has(k)) { seen.add(k); merged.push(e); }
  }
  return merged;
}

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
      background: "linear-gradient(90deg, var(--tt-border) 25%, var(--bg-card) 50%, var(--tt-border) 75%)",
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
      border: "1px solid var(--tt-border)", background: "var(--tt-card)",
      display: "flex", flexDirection: "column", gap: 8,
      borderLeft: "4px solid var(--tt-border2)",
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
    border: `1.5px solid ${active ? "var(--tt-acc-br)" : "var(--tt-border2)"}`,
    background: active ? "var(--tt-acc-bg)" : "transparent",
    color: active ? "var(--tt-acc-fg)" : "var(--tt-text2)",
    fontSize: 13, fontWeight: active ? 600 : 400,
    cursor: "pointer", transition: "all 0.2s ease",
    whiteSpace: "nowrap", userSelect: "none", fontFamily: "inherit",
  });

  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 10,
      padding: "14px 16px", background: "var(--tt-card)",
      borderRadius: 16, border: "1px solid var(--tt-border)",
      boxShadow: "0 4px 16px -4px rgba(224,195,252,0.2)",
    }}>
      <div>
        <button onClick={() => toggle("planets")} style={filterLabelStyle}>
          <span>Планеты</span>
          <span style={{ fontSize: 10, transform: expandedSection === "planets" ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>▼</span>
          {planetFilter.length > 0 && planetFilter.length < ALL_PLANETS.length && (
            <span style={{ background: "var(--accent-glow)", color: "var(--bg-card)", borderRadius: 10, padding: "1px 7px", fontSize: 11, fontWeight: 700 }}>{planetFilter.length}</span>
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
              style={{ flex: 1, accentColor: "var(--accent-glow)" }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--accent)", minWidth: 28 }}>{orbFilter}°</span>
          </div>
        )}
      </div>
      {(planetFilter.length > 0 || aspectFilter.length > 0 || orbFilter !== 2.0) && (
        <button onClick={() => { setPlanetFilter([]); setAspectFilter([]); setOrbFilter(2.0); }} style={{
          alignSelf: "flex-start", background: "none",
          border: "1px solid var(--tt-border2)", color: "var(--tt-text2)",
          borderRadius: 10, padding: "4px 12px", fontSize: 12,
          cursor: "pointer", fontFamily: "inherit",
        }}>Сбросить фильтры</button>
      )}
    </div>
  );
}

const filterLabelStyle = {
  background: "none", border: "none", color: "var(--tt-text2)",
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

  // Мышиное колесо крутит вертикаль — переводим его в горизонтальную прокрутку полосы.
  // React onWheel не всегда даёт preventDefault сработать (пассивные листенеры),
  // поэтому вешаем нативный обработчик с { passive: false }.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const handleWheel = (e) => {
      if (e.deltaY === 0) return;
      el.scrollLeft += e.deltaY;
      e.preventDefault();
    };
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, []);

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
            border: `1.5px solid ${active ? "var(--tt-acc-br)" : "var(--tt-border2)"}`,
            background: active ? "var(--tt-acc-bg)" : "var(--tt-card)",
            color: active ? "var(--tt-acc-fg)" : "var(--tt-text2)",
            cursor: "pointer", transition: "all 0.2s", fontFamily: "inherit",
          }}>
            <span style={{ fontSize: 11, opacity: 0.7 }}>{dt.toLocaleDateString("ru-RU", { weekday: "short" })}</span>
            <span style={{ fontSize: 15, fontWeight: active ? 700 : 500 }}>{dt.getDate()}</span>
            {count > 0 && <span style={{ width: 6, height: 6, borderRadius: 3, background: active ? "var(--tt-acc-br)" : "var(--tt-dot)" }} />}
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
    { label: "Всего",        value: events.length,                                          color: "var(--tt-s1-fg)", bg: "var(--tt-s1-bg)" },
    { label: "Гармоничных",  value: events.filter(e => isHarmonic(e.aspect_type)).length,   color: "var(--tt-s2-fg)", bg: "var(--tt-s2-bg)" },
    { label: "Напряжённых",  value: events.filter(e => isTense(e.aspect_type)).length,      color: "var(--tt-s3-fg)", bg: "var(--tt-s3-bg)" },
    { label: "Соединений",   value: events.filter(e => e.aspect_type === "conjunction").length, color: "var(--tt-s4-fg)", bg: "var(--tt-s4-bg)" },
  ];
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      {stats.map(({ label, value, color, bg }) => (
        <div key={label} style={{ flex: "1 1 80px", padding: "12px 14px", borderRadius: 14, border: "1px solid var(--tt-border)", background: bg, display: "flex", flexDirection: "column", gap: 3 }}>
          <span style={{ fontSize: 22, fontWeight: 800, color }}>{value}</span>
          <span style={{ fontSize: 11, color: "var(--tt-text2)" }}>{label}</span>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// FREE PLAN BANNER
// ═══════════════════════════════════════════════════════════

function FreePlanBanner({ lockedCount, featuredTransit, onUpgrade }) {
  let headline = `✨ Открыт разбор 2 самых значимых транзитов`;
  let sub = `Ещё ${lockedCount} транзитов с AI-разбором — на ${TIER_NAMES.pro}`;

  if (featuredTransit) {
    const tp = `${PLANET_GLYPHS[featuredTransit.transit_planet] || "★"} ${PLANET_LABELS_RU[featuredTransit.transit_planet] || featuredTransit.transit_planet}`;
    const asp = (ASPECT_LABELS_RU[featuredTransit.aspect_type] || featuredTransit.aspect_type).toLowerCase();
    const np = PLANET_LABELS_RU[featuredTransit.natal_planet] || featuredTransit.natal_planet;
    const tail = isHarmonic(featuredTransit.aspect_type)
      ? "один из лучших периодов месяца"
      : "важный период — Astrea подскажет, как пройти его мягче";
    headline = `${tp} ${asp} ваш ${np} — ${tail}`;
    sub = `Разбор этого и ещё ${lockedCount} периодов — на ${TIER_NAMES.pro}`;
  }

  return (
    <div style={{
      margin: "8px 0", padding: "16px 20px", borderRadius: 16,
      background: "var(--accent-muted)",
      border: "1.5px solid var(--border)",
      display: "flex", flexDirection: "column", gap: 10,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--accent)", marginBottom: 3 }}>
            {headline}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            {sub}
          </div>
        </div>
        <button onClick={onUpgrade} style={{
          padding: "9px 20px", borderRadius: 12, border: "none",
          background: "var(--accent)",
          color: "#fff", fontSize: 13, fontWeight: 700,
          cursor: "pointer", whiteSpace: "nowrap", fontFamily: "inherit",
          boxShadow: "0 4px 12px -2px rgba(144,96,200,0.4)",
        }}>
          Открыть {TIER_NAMES.pro}
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// EVENT CARD
// ═══════════════════════════════════════════════════════════

function EventCard({ event, index, isSelected, onClick, blurred, onUpgrade }) {
  const [hovered, setHovered] = useState(false);
  const aspectColor  = ASPECT_COLORS[event.aspect_type] || "var(--accent)";
  const aspectBg     = ASPECT_BG[event.aspect_type]    || "rgba(112,64,168,0.06)";
  const planetAccent = PLANET_ACCENT[event.transit_planet] || "var(--accent-glow)";
  const displayDate  = event.peak_date || event.exact_date || event.date || "";

  // Формируем текст для hover-попапа
  const hoverText = blurred
    ? `${PLANET_GLYPHS[event.transit_planet] || "★"} ${PLANET_LABELS_RU[event.transit_planet] || event.transit_planet} ${ASPECT_LABELS_RU[event.aspect_type]?.toLowerCase() || event.aspect_type} ${PLANET_LABELS_RU[event.natal_planet] || event.natal_planet} (${displayDate ? formatDate(displayDate) : ""}) — ${isHarmonic(event.aspect_type) ? "один из лучших периодов месяца" : "важный транзит для вашего развития"}. На ${TIER_NAMES.pro} — разбор, что это значит для вас и что сделать.`
    : "";

  return (
    <div
      className="tt-event-card"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: "13px 16px",
        borderBottom: "1px solid rgba(139,92,246,0.1)",
        background: isSelected
          ? "rgba(139,92,246,0.08)"
          : (hovered && !blurred ? "rgba(139,92,246,0.06)" : "transparent"),
        transition: "background 0.2s ease",
        animation: `fadeSlideIn 0.3s ease ${index * 0.04}s both`,
        // E2: список транзитов всегда виден; блокируется только AI-разбор (кнопка)
        pointerEvents: "auto",
        position: "relative",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--tt-text2)" }}>{displayDate ? formatDate(displayDate) : ""}</span>
          {event.exact_date && <span style={{ fontSize: 10, color: "var(--tt-text3)", opacity: 0.7 }}>{formatExactTime(event.exact_date)}</span>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {event.applying !== undefined && (
            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 8, border: `1px solid ${event.applying ? "rgba(48,104,176,0.3)" : "var(--tt-border2)"}`, color: event.applying ? "#3068B0" : "var(--tt-text2)", background: event.applying ? "rgba(48,104,176,0.06)" : "transparent" }}>
              {event.applying ? "→ точный" : "← отходит"}
            </span>
          )}
          <span style={{ fontSize: 11, color: "var(--tt-text3)", opacity: 0.7 }}>орб {(event.peak_orb ?? event.orb ?? 0).toFixed(1)}°</span>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 20, color: planetAccent }}>{PLANET_GLYPHS[event.transit_planet] || "★"}</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--tt-text)" }}>{PLANET_LABELS_RU[event.transit_planet] || event.transit_planet}</span>
        <span style={{ fontSize: 16, color: aspectColor, fontWeight: 700 }}>{ASPECT_SYMBOLS[event.aspect_type] || "·"}</span>
        <span style={{ fontSize: 13, color: "var(--tt-text2)" }}>{ASPECT_LABELS_RU[event.aspect_type] || event.aspect_type}</span>
        <span style={{ fontSize: 20 }}>{PLANET_GLYPHS[event.natal_planet] || "☽"}</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--tt-text)" }}>{PLANET_LABELS_RU[event.natal_planet] || event.natal_planet}</span>
      </div>
      {(event.transit_sign || event.natal_sign) && (
        <div style={{ marginTop: 5, fontSize: 12, color: "var(--tt-text3)" }}>{event.transit_degree != null ? `${event.transit_degree.toFixed(1)}° ` : ""}{SIGN_RU[event.transit_sign] || event.transit_sign} → {SIGN_RU[event.natal_sign] || event.natal_sign}</div>
      )}
      {blurred ? (
        <div style={{ marginTop: 10 }}>
          <button
            onClick={(e) => { e.stopPropagation(); onUpgrade && onUpgrade(); }}
            style={{
              padding: "5px 14px", borderRadius: 10,
              border: "1.5px solid var(--tt-border2)",
              background: "transparent", color: "var(--tt-text2)",
              fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
            }}
          >
            Разбор на {TIER_NAMES.pro}
          </button>
        </div>
      ) : (
        <div style={{ marginTop: 10 }}>
          <MotionButton
            level="secondary"
            onClick={(e) => { e.stopPropagation(); onClick(); }}
            style={{
              padding: "5px 14px",
              borderRadius: 10,
              border: `1.5px solid ${isSelected ? aspectColor : "var(--tt-border2)"}`,
              background: isSelected ? aspectColor : "transparent",
              color: isSelected ? "#fff" : aspectColor,
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              fontFamily: "inherit",
              transition: "all 0.2s ease",
            }}
          >
            Интерпретация
          </MotionButton>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// INTERPRETATION PANEL
// ═══════════════════════════════════════════════════════════

function InterpretationPanel({ event, chartId, onClose }) {
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

    if (!chartId) {
      setTimeout(() => {
        setText(`Интерпретация транзита: ${key}.\n\nЭтот аспект влияет на сферу жизни, связанную с натальной планетой. Рекомендуется обратить внимание на события этого периода.`);
        setLoading(false);
      }, 800);
      return;
    }

    const ctrl  = new AbortController();
    fetch(`${API_BASE}/chart/${chartId}/transits/event/interpret`, {
      method: "POST",
      headers: chartAuthHeaders({ "Content-Type": "application/json" }),
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
              if (d !== "[DONE]") { try { const p = JSON.parse(d); if (p.text) setText(prev => prev + p.text); } catch { setText(prev => prev + d); } }
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
    <div style={{ background: "var(--tt-card)", borderRadius: 18, border: "1px solid var(--tt-border2)", boxShadow: "0 8px 24px -6px rgba(224,195,252,0.30)", animation: "fadeSlideIn 0.3s ease" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--tt-border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--tt-text)" }}>{key}</div>
        <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--tt-text3)", fontSize: 18, cursor: "pointer", padding: "2px 6px", borderRadius: 8, fontFamily: "inherit" }}>✕</button>
      </div>
      <div ref={scrollRef} style={{ padding: 16, maxHeight: 400, overflowY: "auto" }}>
        {loading && !text && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[90, 70, 85, 60].map((w, i) => <Skeleton key={i} width={`${w}%`} height={13} />)}
          </div>
        )}
        {error && <div style={{ color: "var(--color-danger)", fontSize: 13 }}>{error}</div>}
        {text && (
          <div style={{ fontSize: 13, lineHeight: 1.75, color: "var(--tt-text)", whiteSpace: "pre-wrap" }}>
            {text}
            {loading && <span style={{ display: "inline-block", width: 6, height: 14, background: "var(--accent-glow)", marginLeft: 2, borderRadius: 2, animation: "blink 0.8s step-end infinite", verticalAlign: "text-bottom" }} />}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════

const TRANSITS_URL = (chartId, from, to) =>
  `${API_BASE}/chart/${chartId}/transits?from_date=${from}&to_date=${to}`;

export default function TransitTimeline({ chartId, onDateSelect, mockMode, userTier, onUpgrade }) {
  const [events,        setEvents]        = useState([]);
  const [loading,       setLoading]       = useState(true);   // первый запрос
  const [loadingMore,   setLoadingMore]   = useState(false);  // догрузка следующего месяца
  const [loadedUntil,   setLoadedUntil]   = useState(null);   // to_date последнего загруженного месяца
  const [reachedEnd,    setReachedEnd]    = useState(false);  // догрузили до горизонта тарифа
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [planetFilter,  setPlanetFilter]  = useState([]);
  const [aspectFilter,  setAspectFilter]  = useState([]);
  const [orbFilter,     setOrbFilter]     = useState(2.0);
  const [activeDate,    setActiveDate]    = useState(null);

  const isFree = !userTier || userTier === "free";
  const isLite = userTier === "lite";
  const isPremium = userTier === "premium";
  const hasFullAccess = userTier === "pro" || userTier === "premium";

  // Горизонт догрузки: Free нужен на 12 мес вперёд для блюр-тизера,
  // Premium — 24 мес, остальные платные — 2 мес (как раньше).
  const maxMonths = isFree ? 12 : (isPremium ? 24 : 2);
  const horizonEnd = useMemo(() => {
    const today = new Date();
    return new Date(today.getFullYear(), today.getMonth() + maxMonths, 0).toISOString().slice(0, 10);
  }, [maxMonths]);

  // ── Первый запрос: ближайший месяц — список появляется быстро ──
  useEffect(() => {
    setEvents([]);
    setLoadedUntil(null);
    setReachedEnd(false);

    if (!chartId || mockMode || chartId === 'anonymous') {
      setEvents(MOCK_EVENTS);
      setLoading(false);
      setReachedEnd(true);
      return;
    }

    setLoading(true);
    const today = new Date().toISOString().slice(0, 10);
    const to    = addMonthISO(today) > horizonEnd ? horizonEnd : addMonthISO(today);
    fetch(TRANSITS_URL(chartId, today, to), {
      headers: chartAuthHeaders(),
    })
      .then(r => r.json())
      .then(data => {
        setEvents(data.events || []);
        setLoadedUntil(to);
        if (to >= horizonEnd) setReachedEnd(true);
        setLoading(false);
      })
      .catch(() => { setEvents(MOCK_EVENTS); setLoading(false); setReachedEnd(true); });
  }, [chartId, mockMode, horizonEnd]);

  // ── Догрузка следующего месяца (по прокрутке — см. sentinel ниже) ──
  const loadMore = useCallback(() => {
    if (loadingMore || reachedEnd || loading || !chartId || mockMode || chartId === 'anonymous' || loadedUntil == null) return;
    if (loadedUntil >= horizonEnd) { setReachedEnd(true); return; }

    setLoadingMore(true);
    const from = addDaysISO(loadedUntil, 1);
    const to   = addMonthISO(from) > horizonEnd ? horizonEnd : addMonthISO(from);

    fetch(TRANSITS_URL(chartId, from, to), {
      headers: chartAuthHeaders(),
    })
      .then(r => r.json())
      .then(data => {
        setEvents(prev => mergeEvents(prev, data.events || []));
        setLoadedUntil(to);
        if (to >= horizonEnd) setReachedEnd(true);
      })
      .catch(() => {}) // оставляем loadedUntil как есть — следующий триггер повторит тот же диапазон
      .finally(() => setLoadingMore(false));
  }, [loadingMore, reachedEnd, loading, chartId, mockMode, loadedUntil, horizonEnd]);

  // ── Free: догружаем до горизонта в фоне, не дожидаясь скролла —
  //    иначе счётчик FreePlanBanner/блюр-тизер занижен, пока пользователь не долистал ──
  useEffect(() => {
    if (!isFree || loading || loadingMore || reachedEnd || loadedUntil == null) return;
    const t = setTimeout(loadMore, 400);
    return () => clearTimeout(t);
  }, [isFree, loading, loadingMore, reachedEnd, loadedUntil, loadMore]);

  // ── Sentinel для скролл-догрузки (все тарифы) ──
  const sentinelRef = useRef(null);
  useEffect(() => {
    if (loading || reachedEnd || !sentinelRef.current) return;
    const el = sentinelRef.current;
    const observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadMore(); },
      { rootMargin: '400px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [loading, reachedEnd, loadMore]);

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
      const eventDate = e.date || e.start_date || e.peak_date;
      const isAfterTwoWeeks = eventDate ? eventDate > twoWeeksFromNow : false;
      const isPositive = ['jupiter', 'venus'].includes(e.transit_planet.toLowerCase()) &&
                         ['trine', 'sextile'].includes(e.aspect_type);
      return isAfterTwoWeeks && isPositive;
    });
  }, [events, twoWeeksFromNow, hasFullAccess, isLite]);

  // E2: у Free AI-разбор открыт только у топ-2 значимых транзитов (free_unlocked с бэка).
  // Сам список событий виден всегда — «visible» тут = «разбор разблокирован».
  const isEventVisible = useCallback((event) => {
    if (hasFullAccess || isLite) return true;
    return !!event.free_unlocked;
  }, [hasFullAccess, isLite]);

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

  // Счётчики StatsSummary — статистика текущего календарного месяца (тот же
  // месяц, что в заголовке «Транзиты — <месяц год>»), не всего загруженного диапазона.
  const currentMonthEvents = useMemo(() => {
    const now = new Date();
    return events.filter(e => {
      const dateStr = e.peak_date || e.start_date || e.date;
      if (!dateStr) return false;
      const d = new Date(dateStr + "T00:00:00");
      return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
    });
  }, [events]);

  const dates            = useMemo(() => [...new Set(events.map(e => e.peak_date || e.date))].sort(), [events]);
  const eventCountByDate = useMemo(() => {
    const counts = {};
    events.forEach(e => { counts[e.peak_date || e.date] = (counts[e.peak_date || e.date] || 0) + 1; });
    return counts;
  }, [events]);

  const handleUpgrade = useCallback(() => {
    if (onUpgrade) onUpgrade('lite_to_pro');
  }, [onUpgrade]);

  const handleEventClick = useCallback((event) => {
    if (isLite) {
      handleUpgrade();
      return;
    }
    setSelectedEvent(prev => prev === event ? null : event);
  }, [isLite, handleUpgrade]);

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
        const resp = await fetch(`${API_BASE}/chart/${chartId}/transits/positions?on_date=${next}`, {
          headers: chartAuthHeaders(),
        });
        if (resp.ok) { const data = await resp.json(); positions = data.planets || []; }
      } catch {}
    }
    onDateSelect(next, dayEvents, positions);
  }, [activeDate, events, onDateSelect, chartId, mockMode]);

  return (
    <div className="tt-scope" style={{ fontFamily: "'Space Grotesk', 'DM Sans', system-ui, sans-serif", maxWidth: 900, margin: "0 auto", padding: "24px 16px", color: "var(--tt-text)" }}>
      <style>{`
        .tt-scope {
          --tt-card: var(--bg-card); --tt-text: var(--text-primary); --tt-text2: var(--text-secondary);
          --tt-text3: var(--text-secondary); --tt-border: var(--border); --tt-border2: var(--border);
          --tt-acc-bg: var(--accent-muted); --tt-acc-fg: var(--accent); --tt-acc-br: var(--accent-glow); --tt-dot: var(--border);
          --tt-s1-bg: var(--accent-muted); --tt-s1-fg: var(--accent);
          --tt-s2-bg: rgba(48,104,176,0.08); --tt-s2-fg: #3068B0;
          --tt-s3-bg: rgba(192,48,48,0.08); --tt-s3-fg: var(--color-danger);
          --tt-s4-bg: rgba(192,128,32,0.08); --tt-s4-fg: #C08020;
        }
        .dark .tt-scope {
          --tt-card: rgba(26,18,48,0.60); --tt-text: var(--text-primary); --tt-text2: var(--text-secondary);
          --tt-text3: var(--text-secondary); --tt-border: rgba(139,92,246,0.14); --tt-border2: rgba(139,92,246,0.20);
          --tt-acc-bg: rgba(139,92,246,0.22); --tt-acc-fg: var(--accent-glow); --tt-acc-br: rgba(139,92,246,0.55); --tt-dot: rgba(139,92,246,0.45);
          --tt-s1-bg: rgba(139,92,246,0.14); --tt-s1-fg: var(--accent-glow);
          --tt-s2-bg: rgba(52,152,219,0.16); --tt-s2-fg: var(--color-air);
          --tt-s3-bg: rgba(248,113,113,0.15); --tt-s3-fg: var(--color-danger);
          --tt-s4-bg: rgba(251,191,36,0.15); --tt-s4-fg: var(--color-warning);
        }
        @keyframes shimmer     { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        @keyframes fadeSlideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes blink       { 50% { opacity: 0; } }
        .tt-event-card { transition: transform 0.2s ease, box-shadow 0.2s ease; }
        .tt-event-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.12); }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--tt-border); border-radius: 3px; }
        button:focus-visible { outline: 2px solid var(--accent-glow); outline-offset: 2px; }
        input[type="range"] { height: 4px; border-radius: 2px; }
      `}</style>

      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, margin: 0, color: "var(--accent)", letterSpacing: "-0.02em" }}>
          Транзиты
        </h1>
        <p style={{ fontSize: 14, color: "var(--tt-text2)", margin: "6px 0 0" }}>
          {new Date().toLocaleDateString("ru-RU", { month: "long", year: "numeric" })}
        </p>
      </div>

      {!loading && <StatsSummary events={currentMonthEvents} />}

      {!loading && dates.length > 0 && (
        <div style={{ margin: "16px 0" }}>
          <DateNav dates={dates} activeDate={activeDate} onDateClick={d => handleDateClick(d)} eventCountByDate={eventCountByDate} />
        </div>
      )}

      <div style={{ margin: "12px 0 16px" }}>
        <FilterBar planetFilter={planetFilter} setPlanetFilter={setPlanetFilter} aspectFilter={aspectFilter} setAspectFilter={setAspectFilter} orbFilter={orbFilter} setOrbFilter={setOrbFilter} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: selectedEvent ? "1fr 1fr" : "1fr", gap: 16, alignItems: "start", transition: "grid-template-columns 0.3s ease" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => <EventCardSkeleton key={i} />)
          ) : filteredEvents.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: "var(--tt-text2)", fontSize: 14, borderRadius: 16, border: "1.5px dashed var(--tt-border2)", background: "var(--bg)" }}>
              Нет транзитов с текущими фильтрами.<br />
              <span style={{ fontSize: 12, opacity: 0.7 }}>Попробуйте увеличить орб или сбросить фильтры.</span>
            </div>
          ) : (
            filteredEvents.map((event, idx) => {
              const globalIdx = events.indexOf(event);
              const visible = isEventVisible(event, globalIdx);
              return (
                <EventCard
                  key={eventKey(event)}
                  event={event} index={idx}
                  isSelected={selectedEvent === event}
                  onClick={() => handleEventClick(event)}
                  blurred={!visible}
                  onUpgrade={handleUpgrade}
                />
              );
            })
          )}
          {!loading && loadingMore && (
            <>
              <EventCardSkeleton />
              <EventCardSkeleton />
            </>
          )}
          {!loading && !reachedEnd && <div ref={sentinelRef} style={{ height: 1 }} />}
        </div>
        {selectedEvent && (
          <div style={{ position: "sticky", top: 24 }}>
            <InterpretationPanel event={selectedEvent} chartId={chartId} onClose={() => setSelectedEvent(null)} />
          </div>
        )}
      </div>

      {!loading && isFree && hiddenCount > 0 && (
        <FreePlanBanner
          lockedCount={hiddenCount}
          featuredTransit={events[featuredTransitIndex]}
          onUpgrade={handleUpgrade}
        />
      )}

      {!loading && (
        <div style={{ marginTop: 32, padding: "16px 0", borderTop: "1px solid var(--tt-border)", fontSize: 12, color: "var(--tt-text3)", textAlign: "center", opacity: 0.8 }}>
          Транзитные орбы: соединение/оппозиция ≤ 2° · квадрат ≤ 2° · трин/секстиль ≤ 1.5°<br />
          Нажмите на транзит для AI-интерпретации
        </div>
      )}
    </div>
  );
}
