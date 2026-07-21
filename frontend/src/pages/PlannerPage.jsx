import { useState, useEffect, useRef, useMemo, Fragment } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import MotionButton from "../components/MotionButton";
import { authFetch } from "../api/client";
import { BACKEND_BASE as API_BASE } from "../config";
const GCAL_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const GCAL_SCOPE = "https://www.googleapis.com/auth/calendar.events";

function getMonthName(date) {
  return date.toLocaleString("ru-RU", { month: "long", year: "numeric" });
}

/* zodiac data-color, intentional */
// Плоские акцентные цвета планет — для бордеров/бейджей (не для кружков, см. PlanetDot ниже).
const PLANET_COLORS = {
  sun: "#FDD85D", moon: "#8E8E96", mercury: "#3498DB", venus: "#EC4899",
  mars: "#E74C3C", jupiter: "#9B59B6", saturn: "#1E3A6E", uranus: "#1ABC9C",
  neptune: "#3F3D9E", pluto: "#7C3AED",
};

/* zodiac data-color, intentional */
// Градиентные пары для кружков планет: radial-gradient(circle at 34% 30%, c1, c2).
const PLANET_DOT_GRADIENTS = {
  sun:     { c1: "#FFE896", c2: "#FDD85D" }, // рендерится особо — см. PlanetDot (плоское + свечение)
  moon:    { c1: "#C8C8CE", c2: "#8E8E96" },
  mercury: { c1: "#8FD3F4", c2: "#3498DB" },
  venus:   { c1: "#FF9EC4", c2: "#EC4899" },
  mars:    { c1: "#FF6B5A", c2: "#E74C3C" },
  jupiter: { c1: "#C9A7F0", c2: "#9B59B6" },
  saturn:  { c1: "#3F5C8A", c2: "#1E3A6E" },
  uranus:  { c1: "#7FE7D8", c2: "#1ABC9C" },
  neptune: { c1: "#7C86E0", c2: "#3F3D9E" },
  pluto:   { c1: "#B98BE0", c2: "#7C3AED" },
};

/* zodiac data-color, intentional */
// Фазы Луны, затмения и узлы — не планеты, но рендерятся тем же PlanetDot.
const PHASE_DOT_STYLES = {
  new_moon:      { c1: "#5A5A64", c2: "#2E2E36" },
  full_moon:     { solid: "#FDC05D" },
  solar_eclipse: { solid: "#1a1230", ring: "#FFE000" },
  lunar_eclipse: { solid: "#1a1230", ring: "#FFE000" },
  north_node:    { c1: "#FFB86B", c2: "#E8842A", node: "☊" },
  south_node:    { c1: "#FFB86B", c2: "#E8842A", node: "☋" },
};

// Тип не распознан (неизвестная планета/фаза) — нейтральный серый кружок.
const FALLBACK_DOT_GRADIENT = { c1: "#A6A6B0", c2: "#6E6E78" };

// Кружок планеты/фазы: градиентная заливка + опциональные символ узла и ретро-метка.
function PlanetDot({ type, size = 18, retro = false, node }) {
  const style = PLANET_DOT_GRADIENTS[type] || PHASE_DOT_STYLES[type] || FALLBACK_DOT_GRADIENT;
  const symbol = node ?? style.node;

  let background, boxShadow, border;
  if (style.solid) {
    background = style.solid;
    if (style.ring) border = `${Math.max(1, size * 0.11)}px solid ${style.ring}`;
  } else if (type === "sun") {
    background = `radial-gradient(circle at 50% 42%, ${style.c1}, ${style.c2} 70%)`;
    boxShadow = "0 0 5px rgba(253,216,93,0.5)";
  } else {
    background = `radial-gradient(circle at 34% 30%, ${style.c1}, ${style.c2})`;
  }

  return (
    <span style={{
      position: "relative", display: "inline-block", flexShrink: 0,
      width: size, height: size, borderRadius: "50%",
      background, boxShadow, border,
    }}>
      {symbol && (
        <span style={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "#fff", fontSize: size * 0.55, lineHeight: 1,
        }}>{symbol}</span>
      )}
      {retro && (
        <span style={{
          position: "absolute", bottom: -3, right: -(size * 0.3),
          fontSize: size * 0.5, color: "#E11D0C", fontFamily: "Georgia, serif", fontWeight: 700,
          textShadow: "-1px 0 #fff, 1px 0 #fff, 0 -1px #fff, 0 1px #fff",
        }}>R</span>
      )}
    </span>
  );
}

// ── Таймлайн: события месяца ──────────────────────────────────────────────────

// Знак в предложный падеж («в Раке», «в Водолее»)
const SIGN_PREP = {
  "Овен": "Овне", "Телец": "Тельце", "Близнецы": "Близнецах", "Рак": "Раке",
  "Лев": "Льве", "Дева": "Деве", "Весы": "Весах", "Скорпион": "Скорпионе",
  "Стрелец": "Стрельце", "Козерог": "Козероге", "Водолей": "Водолее", "Рыбы": "Рыбах",
};
const signPrep = (s) => SIGN_PREP[s] || s || "";

function phaseTooltip(type, sign, fallback) {
  const inSign = sign ? ` в ${signPrep(sign)}` : "";
  switch (type) {
    case "new_moon":      return `Новолуние${inSign}`;
    case "full_moon":     return `Полнолуние${inSign}`;
    case "solar_eclipse": return `Солнечное затмение${inSign}`;
    case "lunar_eclipse": return `Лунное затмение${inSign}`;
    default:              return fallback || "";
  }
}

// Тип A — переход планеты в дом (дата старта периода, кроме первого).
// Тип B — фазы/затмения из /calendar/lunar + ретро (когда бэкенд начнёт отдавать).
function buildTimeline(planData, phases) {
  const events = [];

  (planData?.month_sections || []).forEach((sec) => {
    (sec.periods || []).forEach((p, i) => {
      if (i === 0) return; // старт месяца — не переход внутри месяца
      const start = (p.period || "").split("—")[0].trim(); // "23.07"
      const [dd, mm] = start.split(".").map(Number);
      if (!dd) return;
      events.push({
        id: `${sec.planet}-${i}`, kind: "passage", date: start, day: dd, mon: mm,
        planet: sec.planet, name: sec.planet_name, house: p.house,
      });
    });
  });

  (phases || []).forEach((ph, i) => {
    const [, mm, dd] = (ph.date || "").split("-").map(Number);
    if (!dd) return;
    events.push({
      id: `phase-${i}`, kind: "phase", day: dd, mon: mm,
      date: `${String(dd).padStart(2, "0")}.${String(mm).padStart(2, "0")}`,
      phaseType: ph.type,
      tooltip: phaseTooltip(ph.type, ph.sign, ph.description),
    });
  });

  // Станции ретроградности: бэк отдаёт planet (слаг) вместе с датой станции —
  // рисуем кружок ЭТОЙ планеты с меткой retro, отдельного ℞-узла больше нет.
  (planData?.retrogrades || []).forEach((r, i) => {
    const [dd, mm] = (r.date || "").split(".").map(Number);
    if (!dd) return;
    events.push({
      id: `retro-${i}`, kind: "phase", day: dd, mon: mm, date: r.date, planet: r.planet,
      tooltip: r.label || `${r.status === "end" ? "Окончание" : "Начало"} ретро ${r.planet_name || ""}`.trim(),
    });
  });

  return events.sort((a, b) => (a.mon - b.mon) || (a.day - b.day));
}

// ── Встроенный Google Calendar OAuth + export ─────────────────────────────────

function useGcalExport() {
  const tokenRef = useRef(null);
  const [status, setStatus] = useState("idle"); // idle | loading | success | error

  function getToken() {
    return new Promise((resolve, reject) => {
      if (tokenRef.current && tokenRef.current.expiry > Date.now()) {
        return resolve(tokenRef.current.token);
      }
      if (!GCAL_CLIENT_ID) {
        return reject(new Error("VITE_GOOGLE_CLIENT_ID не задан в .env"));
      }
      const params = new URLSearchParams({
        client_id: GCAL_CLIENT_ID,
        redirect_uri: window.location.origin,
        response_type: "token",
        scope: GCAL_SCOPE,
        prompt: "select_account",
      });
      const popup = window.open(
        `https://accounts.google.com/o/oauth2/v2/auth?${params}`,
        "gcal_oauth",
        "width=500,height=620,left=200,top=100"
      );
      const timer = setInterval(() => {
        try {
          const url = popup?.location?.href || "";
          if (url.includes("access_token")) {
            clearInterval(timer);
            popup.close();
            const hash = new URLSearchParams(url.split("#")[1]);
            const token = hash.get("access_token");
            const expiry = Date.now() + Number(hash.get("expires_in") || 3600) * 1000;
            tokenRef.current = { token, expiry };
            resolve(token);
          }
          if (popup?.closed && !url.includes("access_token")) {
            clearInterval(timer);
            reject(new Error("Авторизация отменена"));
          }
        } catch (_) {}
      }, 300);
    });
  }

  async function exportEvents(events) {
    if (!events?.length) return;
    setStatus("loading");
    try {
      const token = await getToken();
      for (const ev of events) {
        if (!ev.date) continue;
        await fetch("https://www.googleapis.com/calendar/v3/calendars/primary/events", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            summary: ev.summary,
            description: ev.description || "",
            start: { date: ev.date },
            end:   { date: ev.date },
            colorId: ev.colorId || "1",
            reminders: { useDefault: false },
          }),
        });
      }
      setStatus("success");
      setTimeout(() => setStatus("idle"), 3500);
    } catch (e) {
      console.error("[gcal]", e);
      setStatus("error");
      setTimeout(() => setStatus("idle"), 4000);
    }
  }

  return { exportEvents, status };
}

// ── Стили ─────────────────────────────────────────────────────────────────────

const styles = `
  .planner-root {
    min-height: 100vh;
    background: transparent;
    color: var(--text-primary);
    font-family: 'Inter', system-ui, sans-serif;
  }
  .planner-inner {
    max-width: 680px;
    margin: 0 auto;
    padding: 32px 20px;
  }
  .planner-header { margin-bottom: 28px; }
  .planner-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 6px;
  }
  .planner-title {
    margin: 0;
    font-size: 26px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: -0.5px;
  }
  .planner-subtitle { font-size: 13px; color: var(--text-secondary); margin-top: 2px; }

  .month-nav { display: flex; align-items: center; gap: 6px; }
  .month-nav-btn {
    width: 34px; height: 34px; border-radius: 10px; border: none;
    background: var(--accent); color: #fff; font-size: 16px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: opacity 0.15s;
  }
  .month-nav-btn:hover { opacity: 0.85; }
  .month-nav-label {
    font-size: 12px; color: var(--text-secondary); background: var(--bg-deeper);
    border: 1px solid var(--border); border-radius: 10px;
    padding: 6px 14px; font-weight: 600; min-width: 100px; text-align: center;
  }

  .tab-bar {
    display: flex; gap: 4px;
    background: var(--bg-deeper);
    border-radius: 14px; padding: 4px; margin-bottom: 28px;
  }
  .tab-btn {
    flex: 1; padding: 9px 12px; border-radius: 10px; border: none;
    cursor: pointer; font-size: 13px; font-weight: 600;
    font-family: 'Inter', system-ui, sans-serif;
    transition: all 0.15s; background: transparent; color: var(--accent);
  }
  .tab-btn.active {
    background: var(--accent); color: #fff;
  }

  .section-header {
    display: flex; align-items: flex-start;
    gap: 10px; margin-bottom: 16px; padding: 4px 0;
  }
  .section-icon {
    width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 15px; flex-shrink: 0; margin-top: 2px;
    background: var(--accent-muted);
  }
  .section-header-text h3 {
    margin: 0 0 3px; font-size: 15px; font-weight: 700; color: var(--text-primary);
  }
  .section-header-text p { margin: 0; font-size: 12px; color: var(--text-secondary); }

  .period-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px; padding: 16px 18px; margin-bottom: 10px;
    border-left: 3px solid transparent;
    transition: border-color 0.2s ease;
  }
  .period-card-header {
    display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap;
  }
  .period-badge { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 20px; }
  .period-subtitle { font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; }

  .period-items { margin: 0; padding: 0; list-style: none; }
  .period-items li {
    display: flex; align-items: flex-start; gap: 8px;
    margin-bottom: 6px; font-size: 13px; color: var(--text-primary); line-height: 1.5;
  }
  .period-items li .dot {
    margin-top: 5px; width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
  }

  @media (prefers-reduced-motion: reduce) {
    .period-card { transition: none; }
  }
  .lt-warning { font-size: 11px; color: var(--color-warning); margin-bottom: 8px; }

  .locked-box {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 16px; padding: 40px 24px; text-align: center;
  }
  .locked-box .lock-icon { font-size: 38px; margin-bottom: 14px; }
  .locked-box h3 { margin: 0 0 8px; font-size: 16px; font-weight: 700; color: var(--text-primary); }
  .locked-box p { font-size: 13px; color: var(--text-secondary); margin: 0 0 20px; }
  .upgrade-btn {
    padding: 11px 28px; border-radius: 12px; border: none;
    background: var(--accent); color: #fff; font-size: 14px; font-weight: 700;
    cursor: pointer; font-family: 'Inter', system-ui, sans-serif;
    transition: background-color 0.15s;
  }
  .upgrade-btn:hover { background: var(--accent-glow); }

  .free-hint {
    background: var(--accent-muted);
    border: 1px solid var(--border);
    border-radius: 12px; padding: 10px 14px;
    font-size: 12.5px; color: var(--accent); margin-bottom: 16px; line-height: 1.5;
  }
  .locked-teaser { position: relative; margin-top: 4px; }
  .locked-teaser .decoy {
    filter: blur(6px); opacity: 0.5; user-select: none; pointer-events: none;
  }
  .locked-teaser .decoy li { color: var(--text-secondary); }
  .locked-trigger {
    margin-top: 8px; font-size: 12.5px; color: var(--accent); line-height: 1.5;
    display: flex; gap: 6px; align-items: flex-start;
  }
  .locked-trigger .lk { flex-shrink: 0; }

  .error-box {
    background: var(--bg-card); border: 1px solid var(--color-danger);
    border-radius: 10px; padding: 18px; color: var(--color-danger); font-size: 14px;
  }
  .retry-btn {
    margin-top: 10px; background: var(--color-danger); color: #fff; border: none;
    border-radius: 8px; padding: 7px 16px; font-size: 13px; cursor: pointer;
    font-family: 'Inter', system-ui, sans-serif; font-weight: 600;
  }

  .loading-box {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; min-height: 280px; gap: 14px;
  }
  .loading-spinner {
    width: 36px; height: 36px;
    border: 3px solid var(--border); border-top-color: var(--accent);
    border-radius: 50%; animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-text { font-size: 14px; color: var(--text-secondary); }

  .refresh-footer {
    margin-top: 28px; padding-top: 16px;
    border-top: 1px solid var(--border);
    display: flex; flex-direction: column; gap: 10px;
  }
  .refresh-btn {
    width: 100%; padding: 11px; background: var(--accent); border: none;
    border-radius: 12px; color: #fff; font-size: 14px; font-weight: 700;
    cursor: pointer; font-family: 'Inter', system-ui, sans-serif;
    transition: background-color 0.15s;
  }
  .refresh-btn:hover { background: var(--accent-glow); }

  .gcal-btn {
    width: 100%; padding: 11px; background: var(--bg-card);
    border: 1.5px solid var(--border); border-radius: 12px;
    color: var(--accent); font-size: 14px; font-weight: 700;
    cursor: pointer; font-family: 'Inter', system-ui, sans-serif;
    transition: border-color 0.15s, background-color 0.15s;
  }
  .gcal-btn:hover:not(:disabled) { background: var(--accent-muted); border-color: var(--accent-glow); }
  .gcal-btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .gcal-btn.success { background: rgba(5,150,105,0.08); border-color: var(--color-success); color: var(--color-success); }
  .gcal-btn.error   { background: rgba(220,38,38,0.08); border-color: var(--color-danger); color: var(--color-danger); }

  /* ── Таймлайн ── */
  .tl-section { margin-bottom: 24px; }
  .tl-card {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 20px; padding: 20px 20px 16px;
  }
  .tl-title { margin: 0 0 4px; font-size: 15px; font-weight: 700; color: var(--text-primary); }
  .tl-scroll { position: relative; overflow-x: auto; overflow-y: visible; padding: 8px 48px 44px; scrollbar-width: none; -ms-overflow-style: none; }
  .tl-scroll::-webkit-scrollbar { display: none; }
  .tl-rail { position: relative; height: 104px; min-width: 480px; }
  .tl-line {
    position: absolute; left: 0; right: 0; top: 50px; height: 2px;
    background: linear-gradient(90deg, transparent, var(--border), transparent);
  }
  .tl-node {
    position: absolute; top: 0; transform: translateX(-50%);
    display: flex; flex-direction: column; align-items: center; width: 60px;
    border-radius: 14px; padding-bottom: 6px; transition: background 0.15s ease;
  }
  .tl-node:hover, .tl-node:focus-within { background: var(--accent-muted); }
  .tl-dot {
    position: absolute; top: 47px; left: 50%; transform: translateX(-50%);
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--accent); opacity: 0.4; pointer-events: none;
  }
  .tl-date { height: 40px; display: flex; align-items: center; font-size: 14px; font-weight: 700; color: var(--text-primary); }
  .tl-icowrap { position: relative; margin-top: 22px; display: flex; justify-content: center; }
  .tl-ico {
    font-size: 22px; line-height: 1; background: none; border: none; padding: 4px;
    border-radius: 50%; transition: transform 0.15s; font-family: inherit;
    display: inline-block;
  }
  .tl-ico.link { cursor: pointer; }
  .tl-ico.link:hover { transform: scale(1.22); }
  .tl-tip {
    position: absolute; top: calc(100% + 12px);
    background: var(--bg-card); color: var(--text-primary); font-size: 11px; font-weight: 600; white-space: nowrap;
    padding: 7px 11px; border-radius: 10px; border: 1px solid var(--border); opacity: 0; pointer-events: none;
    transition: opacity 0.15s; z-index: 30;
  }
  .tl-tip--right { left: 50%; }
  .tl-tip--left  { right: 50%; }
  .tl-tip::after {
    content: ""; position: absolute; bottom: 100%;
    border: 5px solid transparent; border-bottom-color: var(--bg-card);
  }
  .tl-tip--right::after { left: 12px; }
  .tl-tip--left::after  { right: 12px; }
  .tl-node.phase .tl-icowrap { cursor: default; }
  .tl-node.phase:hover .tl-ico, .tl-node.phase:focus-within .tl-ico { transform: scale(1.22); }
  .tl-node:hover .tl-tip, .tl-node:focus-within .tl-tip { opacity: 1; }

  /* Стопка событий одного дня */
  .tl-stack { position: relative; display: inline-flex; }
  .tl-stack::before {
    content: ""; position: absolute; inset: 0; border-radius: 50%;
    background: var(--border); transform: translate(3px, 3px); z-index: 0;
  }
  .tl-stack > * { position: relative; z-index: 1; }
  .tl-count {
    position: absolute; top: -6px; right: -9px; z-index: 2;
    min-width: 15px; height: 15px; padding: 0 3px; box-sizing: border-box;
    border-radius: 8px; background: var(--accent); color: #fff;
    font-size: 9px; font-weight: 700; line-height: 1;
    display: flex; align-items: center; justify-content: center;
    border: 1.5px solid var(--bg-card);
  }
  .tl-pop {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 12px; padding: 6px; box-shadow: 0 8px 28px rgba(0,0,0,0.18);
    display: flex; flex-direction: column; gap: 2px;
  }
  .tl-pop-day {
    font-size: 10px; font-weight: 700; color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: 0.04em; padding: 4px 8px 2px;
  }
  .tl-pop-item {
    display: flex; align-items: center; gap: 8px; width: 100%;
    background: none; border: none; text-align: left; font-family: inherit;
    padding: 7px 8px; border-radius: 8px; cursor: pointer;
    font-size: 12px; font-weight: 600; color: var(--text-primary); line-height: 1.3;
  }
  .tl-pop-item:hover:not(:disabled), .tl-pop-item:focus-visible:not(:disabled) { background: var(--accent-muted); }
  .tl-pop-item:disabled { cursor: default; }
`;

// ── Вспомогательные компоненты ────────────────────────────────────────────────

// Пропсы кружка для события: фаза → тип фазы/планеты + флаг ретро; переход → планета.
function dotPropsFor(ev) {
  return ev.kind === "phase"
    ? { type: ev.planet || ev.phaseType, retro: !!ev.planet }
    : { type: ev.planet, retro: false };
}

// Подпись события для тултипа/поповера.
function eventLabel(ev) {
  return ev.kind === "phase" ? ev.tooltip : `${ev.name} — ${ev.house} дом`;
}

function Timeline({ events, onPlanet }) {
  const [openDay, setOpenDay] = useState(null);
  const [popPos, setPopPos] = useState(null); // { cx, top, bottom, place }
  const popRef = useRef(null);

  // Закрытие поповера: клик вне, Escape, скролл/ресайз окна.
  useEffect(() => {
    if (openDay == null) return;
    const onDoc = (e) => {
      if (popRef.current && popRef.current.contains(e.target)) return;
      // клик по самому узлу-стопке обрабатывает его onClick (toggle), не гасим тут
      if (e.target.closest && e.target.closest(".tl-node.stacked")) return;
      setOpenDay(null);
    };
    const onKey = (e) => { if (e.key === "Escape") setOpenDay(null); };
    const onMove = () => setOpenDay(null);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [openDay]);

  if (!events.length) return null;

  // ── Часть 1: группировка событий по дню (порядок внутри группы — как в данных) ──
  const groupsMap = new Map();
  for (const ev of events) {
    if (!groupsMap.has(ev.day)) groupsMap.set(ev.day, []);
    groupsMap.get(ev.day).push(ev);
  }
  const groups = [...groupsMap.entries()]
    .map(([day, evs]) => ({ day, evs }))
    .sort((a, b) => a.day - b.day);

  const min = groups[0].day;
  const max = groups[groups.length - 1].day;
  const span = max - min || 1;

  // ── Часть 2: базовая позиция по дате + защита от слипания соседей ──
  const LO = 5, HI = 95, MIN_GAP = 9; // % ширины рельса
  const pos = groups.map((g) => 6 + ((g.day - min) / span) * 88);
  // прямой проход — раздвигаем налезающие вправо
  for (let i = 1; i < pos.length; i++) {
    if (pos[i] < pos[i - 1] + MIN_GAP) pos[i] = pos[i - 1] + MIN_GAP;
  }
  // обратный проход — если упёрлись в правый край, поджимаем соседей внутрь
  if (pos.length && pos[pos.length - 1] > HI) pos[pos.length - 1] = HI;
  for (let i = pos.length - 2; i >= 0; i--) {
    if (pos[i] > pos[i + 1] - MIN_GAP) pos[i] = pos[i + 1] - MIN_GAP;
  }
  if (pos.length && pos[0] < LO) pos[0] = LO; // страховка от вылета за левый край

  const toggleGroup = (day, el) => {
    if (openDay === day) { setOpenDay(null); return; }
    const rect = el.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    setPopPos({
      cx: rect.left + rect.width / 2,
      top: rect.bottom,
      bottom: rect.top,
      place: spaceBelow > 220 ? "below" : "above",
    });
    setOpenDay(day);
  };

  const openGroup = openDay != null ? groups.find((g) => g.day === openDay) : null;
  const popStyle = (() => {
    if (!openGroup || !popPos) return null;
    const W = Math.min(230, window.innerWidth - 16);
    let left = popPos.cx - W / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - W - 8));
    const s = { position: "fixed", left, width: W, zIndex: 100 };
    if (popPos.place === "below") s.top = popPos.top + 8;
    else s.bottom = window.innerHeight - popPos.bottom + 8;
    return s;
  })();

  return (
    <>
      <div className="tl-scroll" onScroll={() => setOpenDay(null)}>
        <div className="tl-rail">
          <div className="tl-line" />
          {groups.map((g, gi) => {
            const left = pos[gi];
            const tipSide = left > 55 ? "left" : "right";

            // Несколько событий в один день — узел-стопка с поповером.
            if (g.evs.length > 1) {
              const first = g.evs[0];
              return (
                <div className="tl-node stacked" key={`grp-${g.day}`} style={{ left: `${left}%` }}>
                  <span className="tl-dot" />
                  <span className="tl-date">{g.day}</span>
                  <span className="tl-icowrap">
                    <button
                      className="tl-ico link"
                      onClick={(e) => toggleGroup(g.day, e.currentTarget.closest(".tl-node"))}
                      aria-expanded={openDay === g.day}
                      aria-label={`События ${g.day} числа: ${g.evs.length}`}
                    >
                      <span className="tl-stack">
                        <PlanetDot {...dotPropsFor(first)} />
                        <span className="tl-count">{g.evs.length}</span>
                      </span>
                    </button>
                  </span>
                </div>
              );
            }

            // Одно событие — как прежде.
            const ev = g.evs[0];
            if (ev.kind === "phase") {
              return (
                <div className="tl-node phase" key={ev.id} style={{ left: `${left}%` }} tabIndex={0}>
                  <span className="tl-dot" />
                  <span className="tl-date">{ev.day}</span>
                  <span className="tl-icowrap">
                    <span className="tl-ico">
                      <PlanetDot {...dotPropsFor(ev)} />
                    </span>
                    <span className={`tl-tip tl-tip--${tipSide}`}>{ev.tooltip}</span>
                  </span>
                </div>
              );
            }
            return (
              <div className="tl-node" key={ev.id} style={{ left: `${left}%` }} tabIndex={0}>
                <span className="tl-dot" />
                <span className="tl-date">{ev.day}</span>
                <span className="tl-icowrap">
                  <button className="tl-ico link" onClick={() => onPlanet(ev.planet)}>
                    <PlanetDot type={ev.planet} />
                  </button>
                  <span className={`tl-tip tl-tip--${tipSide}`}>{ev.name} — {ev.house} дом</span>
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {openGroup && popStyle && (
        <div className="tl-pop" ref={popRef} style={popStyle}>
          <div className="tl-pop-day">{openGroup.day} число · {openGroup.evs.length} события</div>
          {openGroup.evs.map((ev) => {
            const clickable = !!ev.planet; // переходы и ретро несут planet; лунные фазы — нет
            return (
              <button
                key={ev.id}
                className="tl-pop-item"
                disabled={!clickable}
                onClick={() => { if (clickable) { onPlanet(ev.planet); setOpenDay(null); } }}
              >
                <PlanetDot {...dotPropsFor(ev)} />
                <span>{eventLabel(ev)}</span>
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}

function TabBar({ tabs, active, onChange }) {
  return (
    <div className="tab-bar">
      {tabs.map((tab) => (
        <button key={tab.key} onClick={() => onChange(tab.key)}
          className={`tab-btn${active === tab.key ? " active" : ""}`}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function SectionHeader({ planet, emoji, title, subtitle }) {
  return (
    <div className="section-header">
      <div className="section-icon">
        {planet ? <PlanetDot type={planet} size={22} /> : emoji}
      </div>
      <div className="section-header-text">
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </div>
    </div>
  );
}

// #1 — сворачиваемая секция месяца (клик по заголовку раскрывает/скрывает карточки)
function CollapsibleMonthSection({ section }) {
  const [open, setOpen] = useState(section.planet === 'sun');
  return (
    <div id={`plan-sec-${section.planet}`} style={{ marginBottom: 28, scrollMarginTop: 80 }}>
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen(o => !o)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(o => !o); } }}
        style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}
        aria-expanded={open}
      >
        <span style={{ fontSize: 12, color: "var(--text-secondary)", transition: "transform 0.2s", transform: open ? "rotate(90deg)" : "none", flexShrink: 0 }}>▶</span>
        <div style={{ flex: 1 }}>
          <SectionHeader
            planet={section.planet}
            emoji={section.emoji}
            title={section.planet_name}
            subtitle={section.planet_subtitle}
          />
        </div>
      </div>
      {open && (() => {
        const periods = section.periods || [];
        let bannerShown = false;
        return periods.map((p, pi) => {
          const showBanner = p.locked && !bannerShown;
          if (showBanner) bannerShown = true;
          return (
            <Fragment key={pi}>
              {showBanner && (
                <LockedGroupHint>
                  🔒 Дальше по месяцу — периоды Марса, Венеры, Сатурна и других планет с их компенсациями. Открой их на Lite, чтобы увидеть даты и что делать в каждом окне.
                </LockedGroupHint>
              )}
              <PeriodBlock planet={section.planet}
                badgeText={`Период ${p.period}`} items={p.items || []}
                locked={p.locked} />
            </Fragment>
          );
        });
      })()}
    </div>
  );
}

// E1 — блюр-тизер для заблокированных блоков Free (текст не приходит с бэка)
function LockedTeaser({ trigger }) {
  return (
    <div className="locked-teaser">
      <ul className="period-items decoy" aria-hidden="true">
        <li><span className="dot" style={{ background: "var(--border)" }} />Тема этого периода</li>
        <li><span className="dot" style={{ background: "var(--border)" }} />Ключевые действия окна</li>
        <li><span className="dot" style={{ background: "var(--border)" }} />Рекомендации по сферам</li>
      </ul>
      {trigger && <div className="locked-trigger"><span className="lk">🔒</span><span>{trigger}</span></div>}
    </div>
  );
}

// Общая плашка над группой заблокированных периодов раздела (вместо повтора фразы в каждой карточке)
function LockedGroupHint({ children }) {
  return <div className="free-hint">{children}</div>;
}

// Единая карточка периода — используется в разделах "Месяц", "Неделя" и "Долгосрочно",
// чтобы визуально не отличались (заголовок-бейдж + список пунктов).
function PeriodBlock({ planet, badgeText, subtitle, warning, items, locked }) {
  const color = PLANET_COLORS[planet] || "var(--text-secondary)";
  return (
    <div className="period-card" style={{ borderLeftColor: color }}>
      {warning && <div className="lt-warning">⚠️ {warning}</div>}
      <div className="period-card-header">
        <PlanetDot type={planet} size={20} />
        <span className="period-badge" style={{ color, background: `${color}18` }}>
          {badgeText}
        </span>
      </div>
      {subtitle && <div className="period-subtitle">{subtitle}</div>}
      {locked ? (
        <LockedTeaser />
      ) : (
        <ul className="period-items">
          {items.map((item, i) => (
            <li key={i}>
              <span className="dot" style={{ background: color }} />
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="loading-box">
      <div className="loading-spinner" />
      <div className="loading-text">Составляем ваш план…</div>
    </div>
  );
}

// ── Главный компонент ─────────────────────────────────────────────────────────

export default function PlannerPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Слой 3: пуш привёл сюда с темой для разговора — переводим сразу в чат
  // на странице карты, где Astrea встретит пользователя первой репликой.
  useEffect(() => {
    const topic = searchParams.get('astrea');
    if (topic) {
      navigate(`/chart/${id}?astrea=${encodeURIComponent(topic)}`, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const userRaw = localStorage.getItem("astro_user");
  const userTier = (() => {
    try { return JSON.parse(userRaw)?.tier || "free"; } catch { return "free"; }
  })();
  const isFree = userTier === "free" || !userRaw;
  const isPro  = userTier === "pro" || userTier === "premium";

  const [tab, setTab]               = useState("month");
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [planData, setPlanData]     = useState(null);
  const [phases, setPhases]         = useState([]);
  const [monthOffset, setMonthOffset] = useState(0);

  const { exportEvents, status: gcalStatus } = useGcalExport();

  // E1: Free тоже грузит план — витрина с блюром (текущий период Солнца открыт)
  useEffect(() => { loadPlan(); loadPhases(); }, [id, monthOffset]);

  async function loadPhases() {
    try {
      const d = new Date(); d.setMonth(d.getMonth() + monthOffset);
      const y = d.getFullYear(), m = d.getMonth() + 1;
      const r = await fetch(`${API_BASE}/api/v1/calendar/lunar?year=${y}&month=${m}`);
      setPhases(r.ok ? ((await r.json()).phases || []) : []);
    } catch { setPhases([]); }
  }

  const timelineEvents = useMemo(() => buildTimeline(planData, phases), [planData, phases]);

  function goToPlanet(planet) {
    setTab("month");
    setTimeout(() => {
      document.getElementById(`plan-sec-${planet}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
  }

  async function loadPlan() {
    setLoading(true); setError(null); setPlanData(null);
    try {
      const url = isPro && monthOffset !== 0
        ? `${API_BASE}/api/v1/chart/${id}/planner/monthly?month_offset=${monthOffset}`
        : `${API_BASE}/api/v1/chart/${id}/planner/monthly`;
      const res = await authFetch(url);
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `Ошибка ${res.status}`); }
      const data = await res.json();
      setPlanData(data.planner);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  // Собираем события из planData для экспорта
  function buildExportEvents() {
    if (!planData) return [];
    const result = [];
    const d = new Date(); d.setMonth(d.getMonth() + monthOffset);
    const yr = d.getFullYear();

    (planData.month_sections || []).forEach(section => {
      (section.periods || []).forEach(p => {
        const match = p.period?.match(/(\d{2})\.(\d{2})/);
        if (match) {
          result.push({
            summary:     `${section.emoji} ${section.planet_name}: ${p.period}`,
            description: (p.items || []).join("\n"),
            date:        `${yr}-${match[2]}-${match[1]}`,
            colorId:     "1",
          });
        }
      });
    });

    (planData.week_days || []).forEach(day => {
      const match = day.date?.match(/(\d{2})\.(\d{2})/);
      if (match) {
        result.push({
          summary:     `🌙 Луна в ${day.house} доме`,
          description: (day.items || []).join("\n"),
          date:        `${yr}-${match[2]}-${match[1]}`,
          colorId:     "5",
        });
      }
    });

    return result;
  }

  const tabs = [
    { key: "month",    label: "📅 Месяц"       },
    { key: "week",     label: "🌙 Неделя"      },
    { key: "longterm", label: "🪐 Долгосрочно" },
  ];

  const monthLabel = (() => {
    const d = new Date(); d.setMonth(d.getMonth() + monthOffset);
    return monthOffset === 0 ? "Этот месяц" : d.toLocaleString("ru-RU", { month: "long", year: "numeric" });
  })();

  const gcalLabel = {
    idle:    "📅 Экспортировать в Google Calendar",
    loading: "⏳ Экспортируем…",
    success: "✅ Добавлено в Google Calendar",
    error:   "❌ Ошибка — попробуйте снова",
  }[gcalStatus];

  return (
    <>
      <style>{styles}</style>
      <div className="planner-root">
        <div className="planner-inner">

          <div className="planner-header">
            <div className="planner-title-row">
              <h1 className="planner-title">
                {planData?.month_title || `Планер на ${getMonthName(new Date())}`}
              </h1>
              {isPro && !isFree && (
                <div className="month-nav">
                  <MotionButton level="secondary" className="month-nav-btn" onClick={() => setMonthOffset(o => o - 1)}>‹</MotionButton>
                  <span className="month-nav-label">{monthLabel}</span>
                  {monthOffset < 11 && (
                    <MotionButton level="secondary" className="month-nav-btn" onClick={() => setMonthOffset(o => o + 1)}>›</MotionButton>
                  )}
                </div>
              )}
            </div>
            <div className="planner-subtitle">Персональный астрологический план</div>
          </div>

          {isFree && (
            <div className="free-hint">
              ✦ Сейчас открыт ваш период Солнца — главная тема этого времени. Марс, Венера, Сатурн уже движутся по вашей карте — их периоды и компенсации открываются на Lite.
            </div>
          )}

          {(loading ? (
            <LoadingState />
          ) : error ? (
            <div className="error-box">
              <div>⚠️ {error}</div>
              <MotionButton level="primary" className="retry-btn" onClick={loadPlan}>Повторить</MotionButton>
            </div>
          ) : (
            <>
              {timelineEvents.length > 0 && (
                <section className="tl-section">
                  <div className="tl-card">
                    <h2 className="tl-title">Транзитный таймлайн</h2>
                    <Timeline events={timelineEvents} onPlanet={goToPlanet} />
                  </div>
                </section>
              )}

              <TabBar tabs={tabs} active={tab} onChange={setTab} />

              {tab === "month" && (planData?.month_sections || []).map((section, si) => (
                <CollapsibleMonthSection key={si} section={section} />
              ))}

              {tab === "week" && (
                <div>
                  <SectionHeader planet="moon" emoji="🌙" title={planData?.week_title || "Транзитная Луна по домам"} subtitle="Лучшие дни недели для каждой темы" />
                  {(() => {
                    const days = planData?.week_days || [];
                    let bannerShown = false;
                    return days.map((day, i) => {
                      const showBanner = day.locked && !bannerShown;
                      if (showBanner) bannerShown = true;
                      return (
                        <Fragment key={i}>
                          {showBanner && (
                            <LockedGroupHint>
                              🔒 Дальше по неделе — Луна проходит по вашим домам и открывает короткие окна под конкретные дела: разговоры, покупки, отдых. Открой на Lite, чтобы увидеть точные дни.
                            </LockedGroupHint>
                          )}
                          <PeriodBlock planet="moon"
                            badgeText={day.time ? `${day.date} · ${day.time}` : day.date}
                            subtitle={`Луна в ${day.house} доме`}
                            items={day.items || []}
                            locked={day.locked} />
                        </Fragment>
                      );
                    });
                  })()}
                </div>
              )}

              {tab === "longterm" && (
                <div>
                  <SectionHeader emoji="🪐" title={planData?.longterm_title || "Долгосрочные транзиты"} subtitle="Социальные и высшие планеты — тренды на годы" />
                  {(() => {
                    const items = planData?.longterm || [];
                    let bannerShown = false;
                    return items.map((lt, i) => {
                      const showBanner = lt.locked && !bannerShown;
                      if (showBanner) bannerShown = true;
                      return (
                        <Fragment key={i}>
                          {showBanner && (
                            <LockedGroupHint>
                              🔒 Дальше — медленные планеты задают ваши большие темы на месяцы и годы вперёд. Разбор — на Pro.
                            </LockedGroupHint>
                          )}
                          <div style={{ marginBottom: 20 }}>
                            <SectionHeader planet={lt.planet}
                              title={`${lt.planet_name} в ${lt.house} Доме`}
                              subtitle={lt.planet_subtitle} />
                            <PeriodBlock planet={lt.planet}
                              badgeText={lt.period}
                              warning={lt.warning}
                              items={lt.items || []}
                              locked={lt.locked} />
                          </div>
                        </Fragment>
                      );
                    });
                  })()}
                </div>
              )}

              <div className="refresh-footer">
                <MotionButton
                  level="secondary"
                  className={`gcal-btn${!isFree && gcalStatus === "success" ? " success" : ""}${!isFree && gcalStatus === "error" ? " error" : ""}`}
                  disabled={isFree || gcalStatus === "loading"}
                  onClick={() => { if (!isFree) exportEvents(buildExportEvents()); }}
                  title={isFree ? "Экспорт в Google Calendar доступен на Lite и выше" : undefined}
                >
                  {isFree ? "🔒 Экспорт в Google Calendar — на Lite и выше" : gcalLabel}
                </MotionButton>
              </div>
            </>
          ))}

        </div>
      </div>
    </>
  );
}
