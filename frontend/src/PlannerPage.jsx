import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";

const API_BASE = "https://astro-production-abcc.up.railway.app";

function getMonthName(date) {
  return date.toLocaleString("ru-RU", { month: "long", year: "numeric" });
}

const PLANET_COLORS = {
  sun: "#f59e0b", mercury: "#6ee7b7", venus: "#f472b6",
  mars: "#f87171", jupiter: "#a78bfa", saturn: "#94a3b8",
  uranus: "#38bdf8", neptune: "#818cf8", pluto: "#e879f9", moon: "#c4b5fd",
};

function TabBar({ tabs, active, onChange }) {
  return (
    <div style={{ display: "flex", gap: 2, background: "#0f172a", borderRadius: 10, padding: 4, marginBottom: 24 }}>
      {tabs.map((tab) => (
        <button key={tab.key} onClick={() => onChange(tab.key)} style={{
          flex: 1, padding: "8px 12px", borderRadius: 8, border: "none", cursor: "pointer",
          fontSize: 13, fontWeight: 500, transition: "all 0.15s",
          background: active === tab.key ? "#1e293b" : "transparent",
          color: active === tab.key ? "#e2e8f0" : "#64748b",
        }}>{tab.label}</button>
      ))}
    </div>
  );
}

function SectionHeader({ emoji, title, subtitle, planetSubtitle }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 18 }}>{emoji}</span>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "#e2e8f0" }}>{title}</h3>
      </div>
      {planetSubtitle && <div style={{ fontSize: 12, color: "#94a3b8", marginLeft: 26, fontStyle: "italic", marginBottom: 2 }}>{planetSubtitle}</div>}
      {subtitle && <div style={{ fontSize: 12, color: "#64748b", marginLeft: 26 }}>{subtitle}</div>}
    </div>
  );
}

function PeriodBlock({ planet, emoji, period, items, subtitle }) {
  const color = PLANET_COLORS[planet] || "#64748b";
  return (
    <div style={{ background: "#1e293b", border: `1px solid ${color}30`, borderLeft: `3px solid ${color}`, borderRadius: 8, padding: "14px 16px", marginBottom: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 16 }}>{emoji}</span>
        <span style={{ fontSize: 12, color, fontWeight: 500 }}>Период {period}</span>
      </div>
      {subtitle && <div style={{ fontSize: 13, color: "#94a3b8", marginBottom: 8 }}>{subtitle}</div>}
      <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
        {items.map((item, i) => (
          <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 5, fontSize: 13, color: "#cbd5e1", lineHeight: 1.5 }}>
            <span style={{ color, marginTop: 2, flexShrink: 0 }}>•</span>{item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function WeekDayBlock({ date, time, house, items }) {
  const color = PLANET_COLORS.moon;
  return (
    <div style={{ background: "#1e293b", border: `1px solid ${color}30`, borderLeft: `3px solid ${color}`, borderRadius: 8, padding: "14px 16px", marginBottom: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color, fontWeight: 600 }}>{date}</span>
        {time && <span style={{ fontSize: 12, color: "#64748b" }}>{time}</span>}
        <span style={{ marginLeft: "auto", fontSize: 11, background: `${color}20`, color, padding: "2px 8px", borderRadius: 12 }}>
          🌙 Луна в {house} доме
        </span>
      </div>
      <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
        {items.map((item, i) => (
          <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 4, fontSize: 13, color: "#cbd5e1", lineHeight: 1.5 }}>
            <span style={{ color, marginTop: 2, flexShrink: 0 }}>•</span>{item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function LongTermBlock({ planet, emoji, period, items, warning, subtitle }) {
  const color = PLANET_COLORS[planet] || "#64748b";
  return (
    <div style={{ background: "#1e293b", border: `1px solid ${color}30`, borderLeft: `3px solid ${color}`, borderRadius: 8, padding: "14px 16px", marginBottom: 10 }}>
      {warning && <div style={{ fontSize: 11, color: "#f59e0b", marginBottom: 8 }}>⚠️ {warning}</div>}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 16 }}>{emoji}</span>
        <span style={{ fontSize: 13, color, fontWeight: 600 }}>{period}</span>
      </div>
      {subtitle && <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 8, fontStyle: "italic" }}>{subtitle}</div>}
      <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
        {items.map((item, i) => (
          <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 5, fontSize: 13, color: "#cbd5e1", lineHeight: 1.5 }}>
            <span style={{ color, marginTop: 2, flexShrink: 0 }}>•</span>{item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function LoadingState() {
  const [dots, setDots] = useState(".");
  useEffect(() => {
    const t = setInterval(() => setDots((d) => (d.length >= 3 ? "." : d + ".")), 500);
    return () => clearInterval(t);
  }, []);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 300, gap: 16 }}>
      <div style={{ fontSize: 32 }}>✨</div>
      <div style={{ fontSize: 14, color: "var(--text-secondary)" }}>Составляем ваш план{dots}</div>
    </div>
  );
}

export default function PlannerPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  // Читаем тир из localStorage
  const userRaw = localStorage.getItem('astro_user');
  const userTier = (() => {
    try { return JSON.parse(userRaw)?.tier || 'free'; } catch { return 'free'; }
  })();
  const isFree    = userTier === 'free' || !userRaw;
  const isLite    = userTier === 'lite';
  const isPro     = userTier === 'pro' || userTier === 'premium';

  const [tab, setTab] = useState("month");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [planData, setPlanData] = useState(null);
  const [monthOffset, setMonthOffset] = useState(0); // только для pro+

  useEffect(() => { if (!isFree) loadPlan(); else setLoading(false); }, [id, monthOffset]);

  async function loadPlan() {
    setLoading(true);
    setError(null);
    setPlanData(null);
    try {
      const token = localStorage.getItem('astro_access_token');
      const url = isPro && monthOffset !== 0
        ? `${API_BASE}/api/v1/chart/${id}/planner/monthly?month_offset=${monthOffset}`
        : `${API_BASE}/api/v1/chart/${id}/planner/monthly`;
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Ошибка ${res.status}`);
      }
      const data = await res.json();
      setPlanData(data.planner);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const tabs = [
    { key: "month",    label: "📅 Месяц"       },
    { key: "week",     label: "🌙 Неделя"      },
    { key: "longterm", label: "🪐 Долгосрочно"  },
  ];

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text-primary)", fontFamily: "'Inter', system-ui, sans-serif" }}>
      <div style={{ maxWidth: 640, margin: "0 auto", padding: "24px 16px" }}>

        <div style={{ marginBottom: 24 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "var(--text-primary)" }}>
            {planData?.month_title || `Планер на ${getMonthName(new Date())}`}
          </h1>
          <div style={{ fontSize: 13, color: "#475569", marginTop: 4 }}>Персональный астрологический план</div>
        </div>

        {/* Free — заблокировано */}
        {isFree && (
          <div style={{ background: "#1e293b", border: "1px solid rgba(124,108,255,0.3)", borderRadius: 14, padding: "32px 24px", textAlign: "center" }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🔒</div>
            <p style={{ fontSize: 15, color: "#e2e8f0", fontWeight: 600, margin: "0 0 8px" }}>Планировщик недоступен на бесплатном тарифе</p>
            <p style={{ fontSize: 13, color: "#64748b", margin: "0 0 20px" }}>Подключите Lite или Pro, чтобы получить персональный астро-план</p>
            <button onClick={() => navigate(-1)} style={{ padding: "10px 24px", borderRadius: 10, border: "none", background: "linear-gradient(135deg,#7C6CFF,#C060A0)", color: "#fff", fontSize: 14, fontWeight: 700, cursor: "pointer" }}>
              Выбрать тариф
            </button>
          </div>
        )}

        {/* Lite и Pro — контент */}
        {!isFree && (loading ? (
          <LoadingState />
        ) : error ? (
          <div style={{ background: "#1e293b", border: "1px solid #ef444430", borderRadius: 8, padding: 20, color: "#f87171", fontSize: 14 }}>
            <div style={{ marginBottom: 8 }}>⚠️ {error}</div>
            <button onClick={loadPlan} style={{ background: "#ef4444", color: "white", border: "none", borderRadius: 6, padding: "6px 14px", fontSize: 12, cursor: "pointer" }}>
              Повторить
            </button>
          </div>
        ) : (
          <>
            <TabBar tabs={tabs} active={tab} onChange={setTab} />

            {tab === "month" && (planData?.month_sections || []).map((section, si) => (
              <div key={si} style={{ marginBottom: 28 }}>
                <SectionHeader
                  emoji={section.emoji}
                  title={`${section.planet_name} — приоритеты месяца`}
                  planetSubtitle={section.planet_subtitle}
                />
                {(section.periods || []).map((p, pi) => (
                  <PeriodBlock key={pi} planet={section.planet} emoji={section.emoji} period={p.period} items={p.items || []} subtitle={section.planet_subtitle} />
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
                  <LongTermBlock
                    key={i} planet={lt.planet} emoji={lt.emoji}
                    period={`${lt.planet_name} в ${lt.house} Доме — ${lt.period}`}
                    items={lt.items || []} warning={lt.warning} subtitle={lt.planet_subtitle}
                  />
                ))}
              </div>
            )}

            <div style={{ marginTop: 32, paddingTop: 16, borderTop: "1px solid #1e293b", display: "flex", flexDirection: "column", gap: 10 }}>
              {/* Навигация по месяцам — только Pro/Premium */}
              {isPro && (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12 }}>
                  <button onClick={() => setMonthOffset(o => o - 1)} style={{ padding: "6px 14px", background: "#1e293b", border: "1px solid #334155", borderRadius: 8, color: "#e2e8f0", fontSize: 13, cursor: "pointer" }}>
                    ← Пред. месяц
                  </button>
                  <span style={{ fontSize: 13, color: "#64748b", minWidth: 120, textAlign: "center" }}>
                    {monthOffset === 0 ? "Текущий месяц" : monthOffset > 0 ? `+${monthOffset} мес.` : `${monthOffset} мес.`}
                  </span>
                  {monthOffset < 11 && (
                    <button onClick={() => setMonthOffset(o => o + 1)} style={{ padding: "6px 14px", background: "#1e293b", border: "1px solid #334155", borderRadius: 8, color: "#e2e8f0", fontSize: 13, cursor: "pointer" }}>
                      След. месяц →
                    </button>
                  )}
                </div>
              )}
              <button onClick={loadPlan} style={{ width: "100%", padding: "10px", background: "transparent", border: "1px solid #334155", borderRadius: 8, color: "#64748b", fontSize: 13, cursor: "pointer" }}>
                🔄 Пересчитать план
              </button>
            </div>
          </>
        ))}
      </div>
    </div>
  );
}
