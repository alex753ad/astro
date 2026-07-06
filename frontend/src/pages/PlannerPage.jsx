import { useState, useEffect, useRef, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";

const API_BASE = "https://astro-production-abcc.up.railway.app";
const GCAL_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const GCAL_SCOPE = "https://www.googleapis.com/auth/calendar.events";

function getMonthName(date) {
  return date.toLocaleString("ru-RU", { month: "long", year: "numeric" });
}

const PLANET_COLORS = {
  sun: "#EAB308", mercury: "#8B5CF6", venus: "#EC4899",
  mars: "#EF4444", jupiter: "#8B5CF6", saturn: "#64748B",
  uranus: "#06B6D4", neptune: "#4F46E5", pluto: "#7C3AED", moon: "#EAB308",
};

// Знак в предложный падеж («в Раке», «в Водолее»)
const SIGN_PREP = {
  "Овен": "Овне", "Телец": "Тельце", "Близнецы": "Близнецах", "Рак": "Раке",
  "Лев": "Льве", "Дева": "Деве", "Весы": "Весах", "Скорпион": "Скорпионе",
  "Стрелец": "Стрельце", "Козерог": "Козероге", "Водолей": "Водолее", "Рыбы": "Рыбах",
};
const signPrep = (s) => SIGN_PREP[s] || s || "";

const PHASE_EMOJI = {
  new_moon: "🌑", full_moon: "🌕", solar_eclipse: "🌚", lunar_eclipse: "🌘", retro: "℞",
};

function phaseTooltip(type, sign, fallback) {
  const inSign = sign ? ` в ${signPrep(sign)}` : "";
  switch (type) {
    case "new_moon":     return `Новолуние${inSign}`;
    case "full_moon":    return `Полнолуние${inSign}`;
    case "solar_eclipse":return `Солнечное затмение${inSign}`;
    case "lunar_eclipse":return `Лунное затмение${inSign}`;
    default:             return fallback || "";
  }
}

// Строим события таймлайна: переходы планет по домам (тип A) + фазы/затмения/ретро (тип B)
function buildTimeline(planData, phases) {
  const events = [];

  (planData?.month_sections || []).forEach((sec) => {
    (sec.periods || []).forEach((p, i) => {
      if (i === 0) return; // старт месяца — не переход внутри месяца
      const start = (p.period || "").split("—")[0].trim(); // "23.07"
      const [dd, mm] = start.split(".").map(Number);
      if (!dd) return;
      events.push({
        id: `${sec.planet}-${i}`, kind: "passage",
        date: start, day: dd, mon: mm,
        emoji: sec.emoji, name: sec.planet_name, subtitle: sec.planet_subtitle,
        house: p.house, items: p.items || [],
        color: PLANET_COLORS[sec.planet] || "#9333EA",
      });
    });
  });

  (phases || []).forEach((ph, i) => {
    const [, mm, dd] = (ph.date || "").split("-").map(Number);
    if (!dd) return;
    events.push({
      id: `phase-${i}`, kind: "phase", ptype: ph.type,
      date: `${String(dd).padStart(2, "0")}.${String(mm).padStart(2, "0")}`,
      day: dd, mon: mm,
      emoji: ph.emoji || PHASE_EMOJI[ph.type] || "🌙",
      tooltip: phaseTooltip(ph.type, ph.sign, ph.description),
    });
  });

  // Готовый маркер: ретроградность (включится, когда бэкенд начнёт отдавать planData.retrogrades)
  (planData?.retrogrades || []).forEach((r, i) => {
    const [dd, mm] = (r.date || "").split(".").map(Number);
    if (!dd) return;
    events.push({
      id: `retro-${i}`, kind: "phase", ptype: "retro",
      date: r.date, day: dd, mon: mm, emoji: "℞",
      tooltip: r.label || `${r.status === "end" ? "Окончание" : "Начало"} ретро ${r.planet_name || ""}`.trim(),
    });
  });

  return events.sort((a, b) => (a.mon - b.mon) || (a.day - b.day));
}

// ── Встроенный Google Calendar OAuth + export ─────────────────────────────────

function useGcalExport() {
  const tokenRef = useRef(null);
  const [status, setStatus] = useState("idle");

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

// ── Стили (светлая тема + тёмная «Celestial Logic» через html.dark) ────────────

const styles = `
  .planner-root {
    --pl-page-bg: linear-gradient(135deg, #F4EFFF 0%, #FFFDF0 100%);
    --pl-text: #1E293B; --pl-dim: #64748B; --pl-title: #9333EA;
    --pl-card-bg: #ffffff; --pl-card-border: rgba(147,51,234,0.10);
    --pl-card-blur: blur(0px); --pl-card-shadow: 0 2px 10px rgba(147,51,234,0.07);
    --pl-inner-bg: #FAF7FF; --pl-inner-border: #ECE4FB;
    --pl-accent: #9333EA; --pl-on-accent: #ffffff; --pl-accent-soft: rgba(147,51,234,0.10);
    --pl-tabbar-bg: rgba(226,232,240,0.7); --pl-tab-dim: #7C3AED;
    --pl-line: linear-gradient(90deg, rgba(147,51,234,0.10), rgba(147,51,234,0.40), rgba(147,51,234,0.10));
    --pl-dotbg: #E9D5FF; --pl-dotborder: #C4B5FD;
    --pl-glow: none; --pl-border: #E2E8F0;
    --pl-tooltip-bg: #1E293B; --pl-tooltip-text: #ffffff;

    min-height: 100vh;
    background: var(--pl-page-bg);
    color: var(--pl-text);
    font-family: 'Space Grotesk', 'Inter', system-ui, sans-serif;
    transition: background 0.3s, color 0.3s;
  }
  html.dark .planner-root {
    --pl-page-bg: #0F0A1A;
    --pl-text: #e7e0ed; --pl-dim: #cbc3d7; --pl-title: #d0bcff;
    --pl-card-bg: rgba(33,30,39,0.42); --pl-card-border: rgba(208,188,255,0.12);
    --pl-card-blur: blur(12px); --pl-card-shadow: 0 0 30px rgba(208,188,255,0.10);
    --pl-inner-bg: rgba(35,28,56,0.55); --pl-inner-border: #2A2245;
    --pl-accent: #d0bcff; --pl-on-accent: #3c0091; --pl-accent-soft: rgba(208,188,255,0.14);
    --pl-tabbar-bg: #1d1a23; --pl-tab-dim: #cbc3d7;
    --pl-line: linear-gradient(90deg, rgba(208,188,255,0.10), rgba(208,188,255,0.40), rgba(208,188,255,0.10));
    --pl-dotbg: #2A2245; --pl-dotborder: #494454;
    --pl-glow: 0 0 20px rgba(208,188,255,0.30); --pl-border: #2A2245;
    --pl-tooltip-bg: #231C38; --pl-tooltip-text: #e7e0ed;
  }

  .planner-inner { max-width: 760px; margin: 0 auto; padding: 32px 20px; }

  .planner-header { margin-bottom: 24px; }
  .planner-title-row {
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 8px; margin-bottom: 6px;
  }
  .planner-title { margin: 0; font-size: 26px; font-weight: 700; color: var(--pl-title); letter-spacing: -0.5px; }
  .planner-subtitle { font-size: 13px; color: var(--pl-dim); margin-top: 2px; }

  .month-nav { display: flex; align-items: center; gap: 6px; }
  .month-nav-btn {
    width: 34px; height: 34px; border-radius: 10px; border: none;
    background: var(--pl-accent); color: var(--pl-on-accent); font-size: 16px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    box-shadow: var(--pl-glow); transition: opacity 0.15s;
  }
  .month-nav-btn:hover { opacity: 0.85; }
  .month-nav-label {
    font-size: 12px; color: var(--pl-text); background: var(--pl-inner-bg);
    border: 1px solid var(--pl-inner-border); border-radius: 10px;
    padding: 6px 14px; font-weight: 600; min-width: 100px; text-align: center;
  }

  /* Card */
  .glass-card {
    background: var(--pl-card-bg);
    backdrop-filter: var(--pl-card-blur); -webkit-backdrop-filter: var(--pl-card-blur);
    border: 1px solid var(--pl-card-border);
    box-shadow: var(--pl-card-shadow);
  }

  /* ── Timeline ── */
  .tl-section { margin-bottom: 28px; }
  .tl-card { border-radius: 20px; padding: 20px 18px 16px; }
  .tl-head {
    display: flex; align-items: center; gap: 12px;
    flex-wrap: wrap; margin-bottom: 14px;
  }
  .tl-head h2 { margin: 0; font-size: 15px; font-weight: 600; color: var(--pl-text); flex: 1; }
  .tl-openall {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 7px 14px; border: none; border-radius: 10px; cursor: pointer;
    background: var(--pl-accent); color: var(--pl-on-accent);
    font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
    font-family: inherit; box-shadow: var(--pl-glow); transition: opacity 0.15s;
  }
  .tl-openall:hover { opacity: 0.88; }
  .tl-legend { display: flex; gap: 12px; align-items: center; }
  .tl-legend span { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; text-transform: uppercase; color: var(--pl-dim); }
  .tl-legend .d { width: 8px; height: 8px; border-radius: 50%; }

  .tl-scroll { position: relative; overflow-x: auto; padding: 8px 4px 4px; }
  .tl-scroll::-webkit-scrollbar { height: 0; }
  .tl-line {
    position: absolute; top: 62px; left: 0; right: 0; height: 2px;
    background: var(--pl-line);
  }
  .tl-track { display: flex; gap: 8px; min-width: max-content; position: relative; }
  .tl-node {
    flex: 0 0 auto; min-width: 78px; display: flex; flex-direction: column;
    align-items: center; gap: 8px; position: relative; z-index: 1;
  }

  .tl-top {
    display: flex; flex-direction: column; align-items: center; gap: 1px;
    padding: 6px 10px; border-radius: 12px; border: 1px solid transparent;
    background: transparent; cursor: pointer; font-family: inherit;
    transition: all 0.15s; min-height: 52px; justify-content: center;
  }
  .tl-top .tl-emoji { font-size: 18px; line-height: 1; }
  .tl-top .tl-name  { font-size: 10px; color: var(--pl-dim); margin-top: 2px; text-align: center; }
  .tl-top .tl-date  { font-size: 15px; font-weight: 700; color: var(--pl-text); }
  .tl-top.passage:hover { background: var(--pl-accent-soft); }
  .tl-top.open {
    background: var(--pl-accent-soft); border-color: var(--pl-accent);
    box-shadow: var(--pl-glow);
  }
  .tl-top.open .tl-name, .tl-top.open .tl-date { color: var(--pl-accent); }

  .tl-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--pl-dotbg); border: 2px solid var(--pl-dotborder); }
  .tl-dot.today { box-shadow: 0 0 0 4px var(--pl-accent-soft); }

  .tl-chev {
    border: none; background: transparent; cursor: pointer; padding: 2px;
    color: var(--pl-accent); font-size: 14px; line-height: 1; border-radius: 50%;
    transition: transform 0.2s, background 0.15s;
  }
  .tl-chev:hover { background: var(--pl-accent-soft); }
  .tl-chev.open { transform: rotate(180deg); }
  .tl-chev-spacer { height: 22px; }

  /* фаза — tooltip */
  .tl-phase { position: relative; }
  .tl-tip {
    position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%);
    background: var(--pl-tooltip-bg); color: var(--pl-tooltip-text);
    font-size: 11px; font-weight: 500; white-space: nowrap;
    padding: 6px 10px; border-radius: 8px; pointer-events: none;
    opacity: 0; transition: opacity 0.15s; z-index: 20;
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
  }
  .tl-tip::after {
    content: ""; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
    border: 5px solid transparent; border-top-color: var(--pl-tooltip-bg);
  }
  .tl-phase:hover .tl-tip, .tl-phase:focus-within .tl-tip { opacity: 1; }

  /* раскрытые детали переходов */
  .tl-details { margin-top: 14px; display: flex; flex-direction: column; gap: 10px; }
  .tl-detail {
    background: var(--pl-inner-bg); border: 1px solid var(--pl-inner-border);
    border-left: 3px solid var(--_c); border-radius: 12px; padding: 12px 14px;
  }
  .tl-detail-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
  .tl-detail-title { font-size: 13px; font-weight: 700; color: var(--pl-text); }
  .tl-detail-title b { color: var(--_c); }
  .tl-detail-date { font-size: 12px; color: var(--pl-dim); }

  /* ── Tabs ── */
  .tab-bar {
    display: flex; gap: 4px; background: var(--pl-tabbar-bg);
    border-radius: 14px; padding: 4px; margin-bottom: 24px;
  }
  .tab-btn {
    flex: 1; padding: 9px 12px; border-radius: 10px; border: none;
    cursor: pointer; font-size: 13px; font-weight: 600; font-family: inherit;
    transition: all 0.15s; background: transparent; color: var(--pl-tab-dim);
  }
  .tab-btn.active { background: var(--pl-accent); color: var(--pl-on-accent); box-shadow: var(--pl-glow); }

  .section-header { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 14px; padding: 4px 0; }
  .section-icon {
    width: 40px; height: 40px; border-radius: 50%; background: var(--pl-accent-soft);
    display: flex; align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0;
  }
  .section-header-text h3 { margin: 0 0 3px; font-size: 16px; font-weight: 700; color: var(--pl-text); }
  .section-header-text p { margin: 0; font-size: 12px; color: var(--pl-dim); }

  .period-card {
    background: var(--pl-inner-bg); border: 1px solid var(--pl-inner-border);
    border-left: 3px solid transparent; border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;
  }
  .period-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
  .period-badge { font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 8px; }
  .period-house { font-size: 11px; color: var(--pl-dim); }
  .period-subtitle { font-size: 12px; color: var(--pl-dim); margin-bottom: 8px; font-style: italic; }

  .period-items { margin: 0; padding: 0; list-style: none; }
  .period-items li {
    display: flex; align-items: flex-start; gap: 8px;
    margin-bottom: 6px; font-size: 13px; color: var(--pl-text); line-height: 1.5;
  }
  .period-items li .dot { margin-top: 6px; width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }

  .week-card {
    background: var(--pl-inner-bg); border: 1px solid var(--pl-inner-border);
    border-left: 3px solid #EAB308; border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;
  }
  .week-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
  .week-date { font-size: 13px; color: #CA8A04; font-weight: 700; }
  html.dark .week-date { color: #ffb869; }
  .week-time { font-size: 12px; color: var(--pl-dim); }
  .week-house-badge {
    margin-left: auto; font-size: 11px; background: rgba(234,179,8,0.12); color: #CA8A04;
    padding: 3px 10px; border-radius: 12px; font-weight: 600; white-space: nowrap;
  }
  html.dark .week-house-badge { color: #ffb869; }

  .lt-card {
    background: var(--pl-inner-bg); border: 1px solid var(--pl-inner-border);
    border-left: 3px solid transparent; border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;
  }
  .lt-title { font-size: 13px; font-weight: 700; color: var(--pl-text); margin-bottom: 6px; }
  .lt-subtitle { font-size: 12px; color: var(--pl-dim); font-style: italic; margin-bottom: 8px; }

  .locked-box {
    background: var(--pl-card-bg); border: 1px solid var(--pl-card-border);
    border-radius: 16px; padding: 40px 24px; text-align: center;
  }
  .locked-box .lock-icon { font-size: 38px; margin-bottom: 14px; }
  .locked-box h3 { margin: 0 0 8px; font-size: 16px; font-weight: 700; color: var(--pl-text); }
  .locked-box p { font-size: 13px; color: var(--pl-dim); margin: 0 0 20px; }
  .upgrade-btn {
    padding: 11px 28px; border-radius: 12px; border: none; background: var(--pl-accent);
    color: var(--pl-on-accent); font-size: 14px; font-weight: 700; cursor: pointer;
    font-family: inherit; box-shadow: var(--pl-glow); transition: opacity 0.15s;
  }
  .upgrade-btn:hover { opacity: 0.88; }

  .error-box { background: var(--pl-card-bg); border: 1px solid #FCA5A5; border-radius: 12px; padding: 18px; color: #DC2626; font-size: 14px; }
  html.dark .error-box { color: #ffb4ab; border-color: #93000a; }
  .retry-btn {
    margin-top: 10px; background: #EF4444; color: #fff; border: none;
    border-radius: 8px; padding: 7px 16px; font-size: 13px; cursor: pointer; font-family: inherit; font-weight: 600;
  }

  .loading-box { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 280px; gap: 14px; }
  .loading-spinner { width: 36px; height: 36px; border: 3px solid var(--pl-inner-border); border-top-color: var(--pl-accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-text { font-size: 14px; color: var(--pl-dim); }

  .refresh-footer { margin-top: 28px; padding-top: 16px; border-top: 1px solid var(--pl-border); display: flex; flex-direction: column; gap: 10px; }
  .refresh-btn {
    width: 100%; padding: 11px; background: var(--pl-accent); border: none; border-radius: 12px;
    color: var(--pl-on-accent); font-size: 14px; font-weight: 700; cursor: pointer; font-family: inherit;
    box-shadow: var(--pl-glow); transition: opacity 0.15s;
  }
  .refresh-btn:hover { opacity: 0.88; }
  .gcal-btn {
    width: 100%; padding: 11px; background: var(--pl-card-bg); border: 1.5px solid var(--pl-accent);
    border-radius: 12px; color: var(--pl-accent); font-size: 14px; font-weight: 700; cursor: pointer; font-family: inherit; transition: all 0.15s;
  }
  .gcal-btn:hover:not(:disabled) { background: var(--pl-accent-soft); }
  .gcal-btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .gcal-btn.success { border-color: #86EFAC; color: #16A34A; }
  .gcal-btn.error   { border-color: #FCA5A5; color: #DC2626; }

  @media (max-width: 767px) { .planner-title { font-size: 22px; } }
`;

// ── Вспомогательные компоненты ────────────────────────────────────────────────

function Timeline({ events, openAll, todayKey }) {
  const [open, setOpen] = useState(() => new Set());

  // синхронизация с кнопкой «открыть все»
  useEffect(() => {
    if (openAll === null) return;
    setOpen(openAll ? new Set(events.filter(e => e.kind === "passage").map(e => e.id)) : new Set());
  }, [openAll]); // eslint-disable-line

  if (!events.length) return null;

  const toggle = (id) =>
    setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const details = events.filter((e) => e.kind === "passage" && open.has(e.id));

  return (
    <div className="tl-scroll">
      <div className="tl-line" />
      <div className="tl-track">
        {events.map((ev) => {
          const isToday = `${ev.day}.${ev.mon}` === todayKey;
          if (ev.kind === "phase") {
            return (
              <div className="tl-node tl-phase" key={ev.id} tabIndex={0}>
                <div className="tl-top">
                  <span className="tl-emoji">{ev.emoji}</span>
                  <span className="tl-date">{ev.date}</span>
                </div>
                <div className={`tl-dot${isToday ? " today" : ""}`} />
                <div className="tl-chev-spacer" />
                <div className="tl-tip">{ev.tooltip}</div>
              </div>
            );
          }
          const isOpen = open.has(ev.id);
          return (
            <div className="tl-node" key={ev.id}>
              <button
                className={`tl-top passage${isOpen ? " open" : ""}`}
                onClick={() => toggle(ev.id)}
                aria-expanded={isOpen}
              >
                <span className="tl-emoji">{ev.emoji}</span>
                <span className="tl-name">{ev.name}</span>
                <span className="tl-date">{ev.date}</span>
              </button>
              <div className={`tl-dot${isToday ? " today" : ""}`} style={{ background: ev.color, borderColor: ev.color }} />
              <button className={`tl-chev${isOpen ? " open" : ""}`} onClick={() => toggle(ev.id)} aria-label="Детали">
                ⌄
              </button>
            </div>
          );
        })}
      </div>

      {details.length > 0 && (
        <div className="tl-details">
          {details.map((ev) => (
            <div className="tl-detail" key={ev.id} style={{ "--_c": ev.color }}>
              <div className="tl-detail-head">
                <span className="tl-detail-title">
                  {ev.emoji} {ev.name} → <b>{ev.house} дом</b>
                </span>
                <span className="tl-detail-date">с {ev.date}</span>
              </div>
              <ul className="period-items">
                {ev.items.map((it, i) => (
                  <li key={i}><span className="dot" style={{ background: ev.color }} />{it}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TabBar({ tabs, active, onChange }) {
  return (
    <div className="tab-bar">
      {tabs.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)} className={`tab-btn${active === t.key ? " active" : ""}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

function SectionHeader({ emoji, title, subtitle }) {
  return (
    <div className="section-header">
      <div className="section-icon">{emoji}</div>
      <div className="section-header-text">
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </div>
    </div>
  );
}

function PeriodBlock({ planet, emoji, period, house, items }) {
  const color = PLANET_COLORS[planet] || "#9333EA";
  return (
    <div className="period-card" style={{ borderLeftColor: color }}>
      <div className="period-card-header">
        <span style={{ fontSize: 15 }}>{emoji}</span>
        <span className="period-badge" style={{ color, background: `${color}22` }}>Период {period}</span>
        {house != null && <span className="period-house">{house} дом</span>}
      </div>
      <ul className="period-items">
        {items.map((item, i) => (
          <li key={i}><span className="dot" style={{ background: color }} />{item}</li>
        ))}
      </ul>
    </div>
  );
}

function WeekDayBlock({ date, time, house, items }) {
  return (
    <div className="week-card">
      <div className="week-card-header">
        <span className="week-date">{date}</span>
        {time && <span className="week-time">{time}</span>}
        <span className="week-house-badge">🌙 Луна в {house} доме</span>
      </div>
      <ul className="period-items">
        {items.map((item, i) => (
          <li key={i}><span className="dot" style={{ background: "#EAB308" }} />{item}</li>
        ))}
      </ul>
    </div>
  );
}

function LongTermBlock({ planet, emoji, period, items, subtitle }) {
  const color = PLANET_COLORS[planet] || "#64748B";
  return (
    <div className="lt-card" style={{ borderLeftColor: color }}>
      <div className="lt-title"><span style={{ marginRight: 6 }}>{emoji}</span><span style={{ color }}>{period}</span></div>
      {subtitle && <div className="lt-subtitle">{subtitle}</div>}
      <ul className="period-items">
        {items.map((item, i) => (
          <li key={i}><span className="dot" style={{ background: color }} />{item}</li>
        ))}
      </ul>
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

  const userRaw = localStorage.getItem("astro_user");
  const userTier = (() => {
    try { return JSON.parse(userRaw)?.tier || "free"; } catch { return "free"; }
  })();
  const isFree = userTier === "free" || !userRaw;
  const isPro  = userTier === "pro" || userTier === "premium";

  const [tab, setTab]                 = useState("month");
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);
  const [planData, setPlanData]       = useState(null);
  const [phases, setPhases]           = useState([]);
  const [monthOffset, setMonthOffset] = useState(0);
  const [openAll, setOpenAll]         = useState(null); // null | true | false

  const { exportEvents, status: gcalStatus } = useGcalExport();

  useEffect(() => {
    if (!isFree) { loadPlan(); loadPhases(); } else setLoading(false);
  }, [id, monthOffset]); // eslint-disable-line

  async function loadPlan() {
    setLoading(true); setError(null); setPlanData(null);
    try {
      const token = localStorage.getItem("astro_access_token");
      const url = isPro && monthOffset !== 0
        ? `${API_BASE}/api/v1/chart/${id}/planner/monthly?month_offset=${monthOffset}`
        : `${API_BASE}/api/v1/chart/${id}/planner/monthly`;
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `Ошибка ${res.status}`); }
      const data = await res.json();
      setPlanData(data.planner);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  async function loadPhases() {
    try {
      const d = new Date(); d.setMonth(d.getMonth() + monthOffset);
      const y = d.getFullYear(), m = d.getMonth() + 1;
      const r = await fetch(`${API_BASE}/api/v1/calendar/lunar?year=${y}&month=${m}`);
      setPhases(r.ok ? ((await r.json()).phases || []) : []);
    } catch { setPhases([]); }
  }

  const timelineEvents = useMemo(() => buildTimeline(planData, phases), [planData, phases]);

  const todayKey = (() => {
    const d = new Date();
    if (monthOffset !== 0) return "";
    return `${d.getDate()}.${d.getMonth() + 1}`;
  })();

  function buildExportEvents() {
    if (!planData) return [];
    const result = [];
    const d = new Date(); d.setMonth(d.getMonth() + monthOffset);
    const yr = d.getFullYear();
    (planData.month_sections || []).forEach((section) => {
      (section.periods || []).forEach((p) => {
        const match = p.period?.match(/(\d{2})\.(\d{2})/);
        if (match) result.push({
          summary: `${section.emoji} ${section.planet_name}: ${p.period}`,
          description: (p.items || []).join("\n"),
          date: `${yr}-${match[2]}-${match[1]}`, colorId: "1",
        });
      });
    });
    (planData.week_days || []).forEach((day) => {
      const match = day.date?.match(/(\d{2})\.(\d{2})/);
      if (match) result.push({
        summary: `🌙 Луна в ${day.house} доме`,
        description: (day.items || []).join("\n"),
        date: `${yr}-${match[2]}-${match[1]}`, colorId: "5",
      });
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
    idle: "📅 Экспортировать в Google Calendar",
    loading: "⏳ Экспортируем…",
    success: "✅ Добавлено в Google Calendar",
    error: "❌ Ошибка — попробуйте снова",
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
                  <button className="month-nav-btn" onClick={() => setMonthOffset((o) => o - 1)}>‹</button>
                  <span className="month-nav-label">{monthLabel}</span>
                  {monthOffset < 11 && (
                    <button className="month-nav-btn" onClick={() => setMonthOffset((o) => o + 1)}>›</button>
                  )}
                </div>
              )}
            </div>
            <div className="planner-subtitle">Персональный астрологический план</div>
          </div>

          {isFree && (
            <div className="locked-box">
              <div className="lock-icon">🔒</div>
              <h3>Планировщик недоступен на бесплатном тарифе</h3>
              <p>Подключите Lite или Pro, чтобы получить персональный астро-план</p>
              <button className="upgrade-btn" onClick={() => navigate(-1)}>Выбрать тариф</button>
            </div>
          )}

          {!isFree && (loading ? (
            <LoadingState />
          ) : error ? (
            <div className="error-box">
              <div>⚠️ {error}</div>
              <button className="retry-btn" onClick={loadPlan}>Повторить</button>
            </div>
          ) : (
            <>
              {/* Таймлайн событий месяца */}
              {timelineEvents.length > 0 && (
                <section className="tl-section">
                  <div className="glass-card tl-card">
                    <div className="tl-head">
                      <button
                        className="tl-openall"
                        onClick={() => setOpenAll((v) => (v === true ? false : true))}
                      >
                        ⇕ Открыть все детали
                      </button>
                      <h2>Транзитный таймлайн</h2>
                      <div className="tl-legend">
                        <span><i className="d" style={{ background: "var(--pl-accent)" }} /> Сегодня</span>
                        <span><i className="d" style={{ background: "var(--pl-dotbg)", border: "1px solid var(--pl-dotborder)" }} /> Фаза Луны</span>
                      </div>
                    </div>
                    <Timeline events={timelineEvents} openAll={openAll} todayKey={todayKey} />
                  </div>
                </section>
              )}

              <TabBar tabs={tabs} active={tab} onChange={setTab} />

              {tab === "month" && (planData?.month_sections || []).map((section, si) => (
                <div key={si} style={{ marginBottom: 24 }}>
                  <SectionHeader emoji={section.emoji} title={`${section.planet_name} — приоритеты месяца`} subtitle={section.planet_subtitle} />
                  {(section.periods || []).map((p, pi) => (
                    <PeriodBlock key={pi} planet={section.planet} emoji={section.emoji} period={p.period} house={p.house} items={p.items || []} />
                  ))}
                </div>
              ))}

              {tab === "week" && (
                <div>
                  <SectionHeader emoji="🌙" title={planData?.week_title || "Транзитная Луна по домам"} subtitle="Лучшие дни недели для каждой темы" />
                  {(planData?.week_days || []).map((day, i) => (
                    <WeekDayBlock key={i} date={day.date} time={day.time} house={day.house} items={day.items || []} />
                  ))}
                </div>
              )}

              {tab === "longterm" && (
                <div>
                  <SectionHeader emoji="🪐" title={planData?.longterm_title || "Долгосрочные транзиты"} subtitle="Социальные и высшие планеты — тренды на годы" />
                  {(planData?.longterm || []).map((lt, i) => (
                    <LongTermBlock key={i} planet={lt.planet} emoji={lt.emoji}
                      period={`${lt.planet_name} в ${lt.house} Доме — ${lt.period}`}
                      items={lt.items || []} subtitle={lt.planet_subtitle} />
                  ))}
                </div>
              )}

              <div className="refresh-footer">
                <button className="refresh-btn" onClick={() => { loadPlan(); loadPhases(); }}>🔄 Пересчитать план</button>
                <button
                  className={`gcal-btn${gcalStatus === "success" ? " success" : gcalStatus === "error" ? " error" : ""}`}
                  disabled={gcalStatus === "loading"}
                  onClick={() => exportEvents(buildExportEvents())}
                >
                  {gcalLabel}
                </button>
              </div>
            </>
          ))}

        </div>
      </div>
    </>
  );
}
