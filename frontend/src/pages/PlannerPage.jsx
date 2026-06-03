import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";

const API_BASE = "https://astro-production-abcc.up.railway.app";

function getMonthName(date) {
  return date.toLocaleString("ru-RU", { month: "long", year: "numeric" });
}

const PLANET_COLORS = {
  sun: "#EAB308", mercury: "#8B5CF6", venus: "#EC4899",
  mars: "#EF4444", jupiter: "#8B5CF6", saturn: "#64748B",
  uranus: "#06B6D4", neptune: "#4F46E5", pluto: "#7C3AED", moon: "#EAB308",
};

const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

  .planner-root {
    min-height: 100vh;
    background: linear-gradient(135deg, #F4EFFF 0%, #FFFDF0 100%);
    color: #1E293B;
    font-family: 'Manrope', system-ui, sans-serif;
  }
  .planner-inner {
    max-width: 680px;
    margin: 0 auto;
    padding: 32px 20px;
  }
  .planner-header {
    margin-bottom: 28px;
  }
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
    color: #9333EA;
    letter-spacing: -0.5px;
  }
  .planner-subtitle {
    font-size: 13px;
    color: #64748B;
    margin-top: 2px;
  }

  /* Month nav */
  .month-nav {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .month-nav-btn {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    border: none;
    background: #9333EA;
    color: #fff;
    font-size: 16px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 8px rgba(147,51,234,0.25);
    transition: opacity 0.15s;
  }
  .month-nav-btn:hover { opacity: 0.85; }
  .month-nav-label {
    font-size: 12px;
    color: #475569;
    background: #F1F5F9;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 6px 14px;
    font-weight: 600;
    min-width: 100px;
    text-align: center;
  }

  /* Tabs */
  .tab-bar {
    display: flex;
    gap: 4px;
    background: rgba(226,232,240,0.7);
    border-radius: 14px;
    padding: 4px;
    margin-bottom: 28px;
  }
  .tab-btn {
    flex: 1;
    padding: 9px 12px;
    border-radius: 10px;
    border: none;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    font-family: 'Manrope', system-ui, sans-serif;
    transition: all 0.15s;
    background: transparent;
    color: #7C3AED;
  }
  .tab-btn.active {
    background: #9333EA;
    color: #fff;
    box-shadow: 0 2px 8px rgba(147,51,234,0.25);
  }

  /* Section header */
  .section-header {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 16px;
    padding: 4px 0;
  }
  .section-icon {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    flex-shrink: 0;
    margin-top: 2px;
  }
  .section-header-text h3 {
    margin: 0 0 3px;
    font-size: 15px;
    font-weight: 700;
    color: #94A3B8;
  }
  .section-header-text p {
    margin: 0;
    font-size: 12px;
    color: #94A3B8;
  }

  /* Cards */
  .period-card {
    background: #1E293B;
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 10px;
    border-left: 3px solid transparent;
    transition: box-shadow 0.15s;
  }
  .period-card:hover {
    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
  }
  .period-card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }
  .period-badge {
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 20px;
    background: rgba(255,255,255,0.08);
  }
  .period-subtitle {
    font-size: 12px;
    color: #94A3B8;
    margin-bottom: 10px;
  }
  .period-items {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .period-items li {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin-bottom: 6px;
    font-size: 13px;
    color: #CBD5E1;
    line-height: 1.5;
  }
  .period-items li .dot {
    margin-top: 5px;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* Week cards */
  .week-card {
    background: #1E293B;
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 10px;
    border-left: 3px solid #EAB308;
  }
  .week-card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }
  .week-date {
    font-size: 13px;
    color: #EAB308;
    font-weight: 700;
  }
  .week-time {
    font-size: 12px;
    color: #64748B;
  }
  .week-house-badge {
    margin-left: auto;
    font-size: 11px;
    background: rgba(234,179,8,0.12);
    color: #EAB308;
    padding: 3px 10px;
    border-radius: 12px;
    font-weight: 600;
    white-space: nowrap;
  }

  /* Long-term cards */
  .lt-card {
    background: #1E293B;
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 10px;
    border-left: 3px solid transparent;
  }
  .lt-warning {
    font-size: 11px;
    color: #F59E0B;
    margin-bottom: 8px;
  }
  .lt-title {
    font-size: 13px;
    font-weight: 700;
    color: #E2E8F0;
    margin-bottom: 6px;
  }
  .lt-subtitle {
    font-size: 12px;
    color: #94A3B8;
    font-style: italic;
    margin-bottom: 10px;
  }

  /* Locked */
  .locked-box {
    background: #fff;
    border: 1px solid rgba(147,51,234,0.15);
    border-radius: 16px;
    padding: 40px 24px;
    text-align: center;
    box-shadow: 0 4px 24px rgba(147,51,234,0.06);
  }
  .locked-box .lock-icon { font-size: 38px; margin-bottom: 14px; }
  .locked-box h3 { margin: 0 0 8px; font-size: 16px; font-weight: 700; color: #1E293B; }
  .locked-box p { font-size: 13px; color: #64748B; margin: 0 0 20px; }
  .upgrade-btn {
    padding: 11px 28px;
    border-radius: 12px;
    border: none;
    background: #9333EA;
    color: #fff;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    font-family: 'Manrope', system-ui, sans-serif;
    box-shadow: 0 4px 14px rgba(147,51,234,0.3);
    transition: opacity 0.15s;
  }
  .upgrade-btn:hover { opacity: 0.88; }

  /* Error */
  .error-box {
    background: #fff;
    border: 1px solid #FCA5A5;
    border-radius: 10px;
    padding: 18px;
    color: #DC2626;
    font-size: 14px;
  }
  .retry-btn {
    margin-top: 10px;
    background: #EF4444;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    font-size: 13px;
    cursor: pointer;
    font-family: 'Manrope', system-ui, sans-serif;
    font-weight: 600;
  }

  /* Loading */
  .loading-box {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 280px;
    gap: 14px;
  }
  .loading-spinner {
    width: 36px;
    height: 36px;
    border: 3px solid #E9D5FF;
    border-top-color: #9333EA;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-text { font-size: 14px; color: #94A3B8; }

  /* Refresh footer */
  .refresh-footer {
    margin-top: 28px;
    padding-top: 16px;
    border-top: 1px solid #E2E8F0;
  }
  .refresh-btn {
    width: 100%;
    padding: 11px;
    background: #9333EA;
    border: none;
    border-radius: 12px;
    color: #fff;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    font-family: 'Manrope', system-ui, sans-serif;
    box-shadow: 0 4px 14px rgba(147,51,234,0.25);
    transition: opacity 0.15s;
  }
  .refresh-btn:hover { opacity: 0.88; }
`;

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

function SectionHeader({ emoji, title, subtitle }) {
  return (
    <div className="section-header">
      <div className="section-icon" style={{ background: "rgba(147,51,234,0.1)" }}>
        {emoji}
      </div>
      <div className="section-header-text">
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </div>
    </div>
  );
}

function PeriodBlock({ planet, emoji, period, items, subtitle }) {
  const color = PLANET_COLORS[planet] || "#64748B";
  return (
    <div className="period-card" style={{ borderLeftColor: color }}>
      <div className="period-card-header">
        <span style={{ fontSize: 15 }}>{emoji}</span>
        <span className="period-badge" style={{ color, background: `${color}18` }}>
          Период {period}
        </span>
      </div>
      {subtitle && <div className="period-subtitle">{subtitle}</div>}
      <ul className="period-items">
        {items.map((item, i) => (
          <li key={i}>
            <span className="dot" style={{ background: color }} />
            {item}
          </li>
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
          <li key={i}>
            <span className="dot" style={{ background: "#EAB308" }} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function LongTermBlock({ planet, emoji, period, items, warning, subtitle }) {
  const color = PLANET_COLORS[planet] || "#64748B";
  return (
    <div className="lt-card" style={{ borderLeftColor: color }}>
      {warning && <div className="lt-warning">⚠️ {warning}</div>}
      <div className="lt-title">
        <span style={{ marginRight: 6 }}>{emoji}</span>
        <span style={{ color }}>{period}</span>
      </div>
      {subtitle && <div className="lt-subtitle">{subtitle}</div>}
      <ul className="period-items">
        {items.map((item, i) => (
          <li key={i}>
            <span className="dot" style={{ background: color }} />
            {item}
          </li>
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

export default function PlannerPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const userRaw = localStorage.getItem("astro_user");
  const userTier = (() => {
    try { return JSON.parse(userRaw)?.tier || "free"; } catch { return "free"; }
  })();
  const isFree = userTier === "free" || !userRaw;
  const isPro  = userTier === "pro" || userTier === "premium";

  const [tab, setTab] = useState("month");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [planData, setPlanData] = useState(null);
  const [monthOffset, setMonthOffset] = useState(0);

  useEffect(() => { if (!isFree) loadPlan(); else setLoading(false); }, [id, monthOffset]);

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

  const tabs = [
    { key: "month",    label: "📅 Месяц"      },
    { key: "week",     label: "🌙 Неделя"     },
    { key: "longterm", label: "🪐 Долгосрочно" },
  ];

  const monthLabel = (() => {
    const d = new Date(); d.setMonth(d.getMonth() + monthOffset);
    return monthOffset === 0 ? "Этот месяц" : d.toLocaleString("ru-RU", { month: "long", year: "numeric" });
  })();

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
                  <button className="month-nav-btn" onClick={() => setMonthOffset(o => o - 1)}>‹</button>
                  <span className="month-nav-label">{monthLabel}</span>
                  {monthOffset < 11 && (
                    <button className="month-nav-btn" onClick={() => setMonthOffset(o => o + 1)}>›</button>
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
              <TabBar tabs={tabs} active={tab} onChange={setTab} />

              {tab === "month" && (planData?.month_sections || []).map((section, si) => (
                <div key={si} style={{ marginBottom: 28 }}>
                  <SectionHeader
                    emoji={section.emoji}
                    title={`${section.planet_name} — приоритеты месяца`}
                    subtitle={section.planet_subtitle}
                  />
                  {(section.periods || []).map((p, pi) => (
                    <PeriodBlock key={pi} planet={section.planet} emoji={section.emoji}
                      period={p.period} items={p.items || []} subtitle={section.planet_subtitle} />
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
                      items={lt.items || []} warning={lt.warning} subtitle={lt.planet_subtitle} />
                  ))}
                </div>
              )}

              <div className="refresh-footer">
                <button className="refresh-btn" onClick={loadPlan}>🔄 Пересчитать план</button>
              </div>
            </>
          ))}

        </div>
      </div>
    </>
  );
}
