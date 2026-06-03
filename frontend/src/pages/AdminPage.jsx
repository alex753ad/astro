// frontend/src/pages/AdminPage.jsx
// Добавить в App.jsx:
//   import AdminPage from "./pages/AdminPage";
//   <Route path="/admin" element={<AdminPage />} />

import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const PLAN_LABELS = { free: "Free", lite: "Lite", pro: "Pro", premium: "Premium" };
const PLAN_COLORS = {
  free:    { bar: "#B4B2A9", text: "#888780", badge: "bg-[#F1EFE8] text-[#5F5E5A]" },
  lite:    { bar: "#378ADD", text: "#185FA5", badge: "bg-[#E6F1FB] text-[#185FA5]" },
  pro:     { bar: "#639922", text: "#3B6D11", badge: "bg-[#EAF3DE] text-[#3B6D11]" },
  premium: { bar: "#7F77DD", text: "#3C3489", badge: "bg-[#EEEDFE] text-[#3C3489]" },
};
const PLAN_PRICES = { lite: 790, pro: 1990, premium: 7990 };
const TABS = ["Обзор", "Пользователи", "Выручка", "AI & расходы", "Email-цепочки", "Промокоды"];

// Мок-данные пока нет реального API
const MOCK = {
  users: { total: 2847, new_month: 143, new_week: 47, google_pct: 61, by_plan: { free: 1906, lite: 541, pro: 284, premium: 116 } },
  activity_30d: { charts: 1842, interpretations: 1203, pdf_reports: 187, rag_sessions: 432, crm_cards: 94, lunar_calendar_views: 3218, planner_views: 1547 },
  revenue: { mrr: 341000, mrr_growth_pct: 18, arr: 4092000, arpu: 365 },
  funnel: { registered: 2847, made_chart: 2220, lite: 541, pro: 284, premium: 116 },
  payment_errors: { total: 14, items: [{ code: "card_declined", plan: "lite", count: 6 }, { code: "insufficient_funds", plan: "pro", count: 4 }, { code: "expired_card", plan: "premium", count: 3 }, { code: "authentication_required", plan: "pro", count: 1 }] },
  churn: { count: 29, rate_pct: 3.2 },
  gift_codes: { total: 48, activated: 31, activation_pct: 65 },
  avg_per_plan: {
    free:    { charts: 1.4, interpretations: 0 },
    lite:    { charts: 4.2, interpretations: 2.1 },
    pro:     { charts: 11.7, interpretations: 9.8 },
    premium: { charts: 23.1, interpretations: 41.2 },
  },
  recent_users: [
    { id: 1, email: "a.smirnova@mail.ru",  plan: "premium", charts: 23, interpretations: 84, created_at: new Date(Date.now() - 2*86400000).toISOString() },
    { id: 2, email: "kozlov.d@yandex.ru",  plan: "pro",     charts: 11, interpretations: 15, created_at: new Date(Date.now() - 5*86400000).toISOString() },
    { id: 3, email: "marina.v@gmail.com",  plan: "lite",    charts: 8,  interpretations: 3,  created_at: new Date(Date.now() - 7*86400000).toISOString() },
    { id: 4, email: "user4821@gmail.com",  plan: "free",    charts: 2,  interpretations: 0,  created_at: new Date(Date.now() - 8*86400000).toISOString() },
    { id: 5, email: "p.novikova@bk.ru",   plan: "pro",     charts: 17, interpretations: 14, created_at: new Date(Date.now() - 14*86400000).toISOString() },
  ],
  ai_costs: { gpt4o: 38400, deepseek: 6200, total: 44600, fallback_rate_pct: 8.3 },
  rate_limits_24h: { lite: 89, pro: 31, premium: 0 },
  email_chains: [
    { name: "Welcome (регистрация)",   open_pct: 67, click_pct: 23 },
    { name: "Day 2 — транзит",         open_pct: 48, click_pct: 18 },
    { name: "Day 7 — апгрейд-нудж",   open_pct: 34, click_pct: 14 },
    { name: "Day 14 — купон 30%",      open_pct: 41, click_pct: 22 },
    { name: "Welcome Lite",            open_pct: 58, click_pct: 16 },
    { name: "Lite Day 14 → Pro тизер", open_pct: 29, click_pct: 9  },
    { name: "Pro Day 30 → Premium",    open_pct: 36, click_pct: 11 },
    { name: "Еженедельный дайджест",   open_pct: 52, click_pct: 19 },
    { name: "Ошибка оплаты → Portal",  open_pct: 71, click_pct: 54 },
  ],
  promos: {
    list: [
      { code: "LITE30",    active: true,  times_redeemed: 48, discount: "30%", duration: "once",       expires_at: "2026-08-01" },
      { code: "PRO20",     active: true,  times_redeemed: 21, discount: "20%", duration: "repeating",  expires_at: "2026-07-01" },
      { code: "WELCOME10", active: true,  times_redeemed: 134,discount: "10%", duration: "forever",    expires_at: null },
      { code: "ASTRO500",  active: false, times_redeemed: 12, discount: "₽500",duration: "once",       expires_at: "2026-03-01" },
    ],
    promo_by_plan: { free: 0, lite: 48, pro: 21, premium: 7 },
    gift_by_plan:  { lite: 18, pro: 9, premium: 4 },
  },
};

function fmt(n) { return n?.toLocaleString("ru-RU") ?? "—"; }
function fmtMoney(n) { return "₽ " + fmt(n); }
function fmtDate(iso) {
  const d = new Date(iso);
  const diff = Math.floor((Date.now() - d) / 86400000);
  if (diff === 0) return "сегодня";
  if (diff === 1) return "вчера";
  if (diff < 7) return diff + " дн. назад";
  if (diff < 14) return "1 нед. назад";
  return Math.floor(diff / 7) + " нед. назад";
}

function Badge({ plan }) {
  const c = PLAN_COLORS[plan]?.badge ?? "";
  return <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium ${c}`}>{PLAN_LABELS[plan] ?? plan}</span>;
}

function MetricCard({ label, value, sub, subColor }) {
  return (
    <div className="bg-[var(--color-background-secondary,#F7F5F0)] rounded-xl p-4">
      <div className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">{label}</div>
      <div className="text-[22px] font-medium text-gray-900 leading-none">{value}</div>
      {sub && <div className={`text-[11px] mt-1 ${subColor ?? "text-gray-400"}`}>{sub}</div>}
    </div>
  );
}

function Row({ left, right, sub }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-gray-100 last:border-0 text-[13px]">
      <span className="text-gray-600">{left}</span>
      <div className="text-right">
        <strong className="text-gray-900">{right}</strong>
        {sub && <span className="text-[11px] text-gray-400 ml-2">{sub}</span>}
      </div>
    </div>
  );
}

function PlanBar({ plan, count, total, mrr }) {
  const pct = total ? Math.round(count / total * 100) : 0;
  const c = PLAN_COLORS[plan];
  return (
    <div className="flex items-center gap-3 mb-3">
      <span className="w-16 text-[12px] font-medium" style={{ color: c.text }}>{PLAN_LABELS[plan]}</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: pct + "%", background: c.bar }} />
      </div>
      <span className="w-10 text-right text-[12px] text-gray-600">{fmt(count)}</span>
      <span className="w-20 text-right text-[11px] text-gray-400">{mrr ? fmtMoney(mrr) : "—"}</span>
    </div>
  );
}

// ─── Вкладки ──────────────────────────────────────────────────────────────────

function TabOverview({ d }) {
  const plans = d.users.by_plan;
  const total = d.users.total;
  const mrr_by_plan = { lite: plans.lite * 790, pro: plans.pro * 1990, premium: plans.premium * 7990 };
  const funnel = d.funnel;
  const funnelSteps = [
    { label: "Регистрация", val: funnel.registered, pct: 100,  color: "#B4B2A9" },
    { label: "1-я карта",   val: funnel.made_chart, pct: Math.round(funnel.made_chart/funnel.registered*100), color: "#85B7EB" },
    { label: "→ Lite",      val: funnel.lite,        pct: Math.round(funnel.lite/funnel.registered*100),       color: "#97C459" },
    { label: "→ Pro",       val: funnel.pro,         pct: Math.round(funnel.pro/funnel.registered*100),        color: "#AFA9EC" },
    { label: "→ Premium",   val: funnel.premium,     pct: Math.round(funnel.premium/funnel.registered*100),    color: "#7F77DD" },
  ];

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
        <MetricCard label="Пользователи" value={fmt(total)} sub={`+${d.users.new_month} за месяц`} subColor="text-green-600" />
        <MetricCard label="MRR" value={fmtMoney(d.revenue.mrr)} sub={`+${d.revenue.mrr_growth_pct}% м/м`} subColor="text-green-600" />
        <MetricCard label="Карт (всё время)" value={fmt(d.activity_30d.charts)} sub="за 30 дней" />
        <MetricCard label="AI-интерпретаций" value={fmt(d.activity_30d.interpretations)} sub={fmtMoney(d.ai_costs.total) + " расходы"} subColor="text-red-500" />
        <MetricCard label="Churn (мес)" value={d.churn.rate_pct + "%"} sub={`−0.8% к пр.`} subColor="text-green-600" />
        <MetricCard label="Ошибки оплат" value={d.payment_errors.total} sub="₽ 22K под угрозой" subColor="text-red-500" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-3">
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Распределение по тарифам</div>
          {Object.entries(plans).map(([plan, count]) => (
            <PlanBar key={plan} plan={plan} count={count} total={total} mrr={mrr_by_plan[plan]} />
          ))}
        </div>
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Воронка конверсии</div>
          {funnelSteps.map(s => (
            <div key={s.label} className="flex items-center gap-3 mb-2">
              <span className="w-24 text-[12px] text-gray-500">{s.label}</span>
              <div className="flex-1 h-6 bg-gray-100 rounded overflow-hidden">
                <div className="h-full flex items-center pl-2 rounded text-[11px] font-medium text-white" style={{ width: s.pct + "%", background: s.color, color: s.pct < 15 ? "#fff" : undefined }}>
                  {fmt(s.val)}
                </div>
              </div>
              <span className="w-10 text-right text-[11px] text-gray-400">{s.pct}%</span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Активность за 30 дней</div>
          <Row left="Карт рассчитано"    right={fmt(d.activity_30d.charts)} />
          <Row left="Интерпретаций"      right={fmt(d.activity_30d.interpretations)} />
          <Row left="PDF-отчётов"        right={fmt(d.activity_30d.pdf_reports)} />
          <Row left="RAG-чат сессий"     right={fmt(d.activity_30d.rag_sessions)} />
          <Row left="CRM-карт"           right={fmt(d.activity_30d.crm_cards)} />
          <div className="my-2 border-t border-gray-100" />
          <Row left="🌙 Лунный календарь" right={fmt(d.activity_30d.lunar_calendar_views)} />
          <Row left="📅 Планировщик"      right={fmt(d.activity_30d.planner_views)} />
        </div>
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Ошибки оплат</div>
          {d.payment_errors.items.map((e, i) => (
            <div key={i} className="flex justify-between items-center py-2 border-b border-gray-100 last:border-0 text-[12px]">
              <span className="text-gray-600"><Badge plan={e.plan} /> · {e.code}</span>
              <span className="text-red-500 font-medium bg-red-50 px-2 py-0.5 rounded text-[10px]">{e.count}</span>
            </div>
          ))}
          <div className="mt-3 text-[11px] text-gray-400">Stripe Portal отправлен: 11 / {d.payment_errors.total}</div>
        </div>
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">AI-расходы (месяц)</div>
          <Row left="GPT-4o"         right={fmtMoney(d.ai_costs.gpt4o)} />
          <Row left="DeepSeek V3"    right={fmtMoney(d.ai_costs.deepseek)} />
          <Row left="Template"       right={<span className="text-green-600">₽ 0</span>} />
          <div className="my-2 border-t border-gray-100" />
          <Row left={<strong>Итого</strong>} right={<strong>{fmtMoney(d.ai_costs.total)}</strong>} />
          <div className="mt-2 text-[11px] text-gray-400">Fallback rate: {d.ai_costs.fallback_rate_pct}% → DeepSeek</div>
        </div>
      </div>
    </div>
  );
}

function TabUsers({ d }) {
  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <MetricCard label="Новых за 7 дней" value={d.users.new_week} />
        <MetricCard label="Активных (30д)" value={fmt(d.activity_30d.charts)} />
        <MetricCard label="Среднее карт/user" value={d.avg_per_plan.pro.charts} />
        <MetricCard label="Google OAuth" value={d.users.google_pct + "%"} />
      </div>
      <div className="border border-gray-100 rounded-xl p-4 mb-3">
        <div className="text-[13px] font-medium text-gray-500 mb-4">Последние пользователи</div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-gray-100">
                {["Email", "Тариф", "Карт", "Интерп.", "Регистрация"].map(h => (
                  <th key={h} className="text-left pb-2 pr-4 text-[11px] uppercase tracking-wide text-gray-400 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.recent_users.map(u => (
                <tr key={u.id} className="border-b border-gray-100 last:border-0">
                  <td className="py-2 pr-4 text-gray-700">{u.email}</td>
                  <td className="py-2 pr-4"><Badge plan={u.plan} /></td>
                  <td className="py-2 pr-4">{u.charts}</td>
                  <td className="py-2 pr-4">{u.interpretations}</td>
                  <td className="py-2 text-gray-400">{fmtDate(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Карт на пользователя</div>
          {Object.entries(d.avg_per_plan).map(([plan, v]) => (
            <Row key={plan} left={<Badge plan={plan} />} right={v.charts} />
          ))}
        </div>
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Интерпретаций на пользователя</div>
          {Object.entries(d.avg_per_plan).map(([plan, v]) => (
            <Row key={plan} left={<Badge plan={plan} />} right={v.interpretations} />
          ))}
        </div>
      </div>
    </div>
  );
}

function TabRevenue({ d }) {
  const plans = d.users.by_plan;
  const mrr_by_plan = { lite: plans.lite * 790, pro: plans.pro * 1990, premium: plans.premium * 7990 };
  const total_mrr = Object.values(mrr_by_plan).reduce((a, b) => a + b, 0);
  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <MetricCard label="MRR" value={fmtMoney(d.revenue.mrr)} sub={`+${d.revenue.mrr_growth_pct}% м/м`} subColor="text-green-600" />
        <MetricCard label="ARR (прогноз)" value={fmtMoney(d.revenue.arr)} />
        <MetricCard label="ARPU (платящие)" value={fmtMoney(d.revenue.arpu)} />
        <MetricCard label="LTV (est)" value="₽ 11 400" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">MRR по тарифам</div>
          {Object.entries(mrr_by_plan).map(([plan, mrr]) => (
            <Row key={plan} left={<span style={{ color: PLAN_COLORS[plan]?.text, fontWeight: 500 }}>{PLAN_LABELS[plan]}</span>}
              right={fmtMoney(mrr)} sub={Math.round(mrr / total_mrr * 100) + "%"} />
          ))}
          <div className="my-2 border-t border-gray-100" />
          <Row left={<strong>Итого MRR</strong>} right={<strong>{fmtMoney(total_mrr)}</strong>} />
          <div className="mt-2 text-[11px] text-gray-400">{plans.premium} Premium-клиентов генерируют {Math.round(mrr_by_plan.premium / total_mrr * 100)}% выручки</div>
        </div>
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Подарочные коды</div>
          <Row left="Создано" right={d.gift_codes.total} />
          <Row left="Активировано" right={`${d.gift_codes.activated} (${d.gift_codes.activation_pct}%)`} />
        </div>
      </div>
    </div>
  );
}

function TabAI({ d }) {
  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <MetricCard label="Токены (мес)" value="48M" />
        <MetricCard label="Расходы AI" value={fmtMoney(d.ai_costs.total)} />
        <MetricCard label="Стоимость / интерп" value="₽ 51" />
        <MetricCard label="Маржа на AI" value="87%" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Разбивка по движку</div>
          <Row left="GPT-4o" right={fmtMoney(d.ai_costs.gpt4o)} sub="86%" />
          <Row left="DeepSeek V3 (fallback)" right={fmtMoney(d.ai_costs.deepseek)} sub="14%" />
          <Row left="Template engine" right={<span className="text-green-600">₽ 0</span>} sub="0%" />
        </div>
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Rate limits (за 24ч)</div>
          <Row left={<><Badge plan="lite" /> достигли лимита</>}    right={<span className="text-yellow-600">{d.rate_limits_24h.lite} польз.</span>} />
          <Row left={<><Badge plan="pro" /> достигли лимита</>}     right={<span className="text-yellow-600">{d.rate_limits_24h.pro} польз.</span>} />
          <Row left={<><Badge plan="premium" /> достигли лимита</>} right={d.rate_limits_24h.premium} />
          <div className="mt-2 text-[11px] text-gray-400">Fallback rate: {d.ai_costs.fallback_rate_pct}%</div>
        </div>
      </div>
    </div>
  );
}

function TabEmails({ d }) {
  const total_sent = 18402;
  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <MetricCard label="Отправлено (мес)" value={fmt(total_sent)} />
        <MetricCard label="Открытий" value="41%" />
        <MetricCard label="Кликов" value="12%" />
        <MetricCard label="Конверсий с email" value="8.4%" />
      </div>
      <div className="border border-gray-100 rounded-xl p-4">
        <div className="text-[13px] font-medium text-gray-500 mb-4">Эффективность цепочек</div>
        <div className="grid grid-cols-[1fr_70px_70px_90px] text-[11px] uppercase tracking-wide text-gray-400 pb-2 border-b border-gray-100 font-medium">
          <span>Цепочка</span><span className="text-right">Откр.</span><span className="text-right">Клики</span><span className="text-right">Прогресс</span>
        </div>
        {d.email_chains.map((c, i) => (
          <div key={i} className="grid grid-cols-[1fr_70px_70px_90px] items-center py-2 border-b border-gray-100 last:border-0 text-[12px]">
            <span className="text-gray-600 pr-2">{c.name}</span>
            <span className="text-right font-medium">{c.open_pct}%</span>
            <span className="text-right font-medium">{c.click_pct}%</span>
            <div className="flex justify-end">
              <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full rounded-full bg-violet-400" style={{ width: c.open_pct + "%" }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Вкладка Промокоды ────────────────────────────────────────────────────────

const DURATION_LABELS = { once: "Один раз", repeating: "Несколько мес.", forever: "Навсегда" };

function TabPromos({ d, authFetch, onReload }) {
  const promos = d.promos ?? { list: [], promo_by_plan: {}, gift_by_plan: {} };

  const [form, setForm] = useState({
    code: "", discount_type: "percent", discount_value: 10,
    duration: "once", duration_months: 3,
    expires_at: "", max_redemptions: "",
  });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  async function handleCreate(e) {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    try {
      const body = {
        code: form.code,
        discount_type: form.discount_type,
        discount_value: Number(form.discount_value),
        duration: form.duration,
        duration_months: form.duration === "repeating" ? Number(form.duration_months) : null,
        expires_at: form.expires_at || null,
        max_redemptions: form.max_redemptions ? Number(form.max_redemptions) : null,
      };
      const res = await authFetch("/api/v1/admin/coupons", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      setMsg({ ok: true, text: "Промокод создан ✓" });
      setForm(f => ({ ...f, code: "" }));
      onReload();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setSaving(false);
    }
  }

  async function handleDeactivate(id) {
    await authFetch(`/api/v1/admin/coupons/${id}`, { method: "DELETE" });
    onReload();
  }

  return (
    <div>
      {/* Статистика по тарифам */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {Object.entries(PLAN_LABELS).map(([plan, label]) => (
          <div key={plan} className="border border-gray-100 rounded-xl p-4">
            <div className="text-[11px] text-gray-400 uppercase tracking-wide mb-2">{label}</div>
            <div className="text-[13px] text-gray-600 flex justify-between mb-1">
              <span>Промокод</span>
              <strong>{promos.promo_by_plan[plan] ?? 0}</strong>
            </div>
            <div className="text-[13px] text-gray-600 flex justify-between">
              <span>Gift-карта</span>
              <strong>{promos.gift_by_plan[plan] ?? 0}</strong>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-4">
        {/* Список промокодов */}
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Активные промокоды</div>
          {promos.list.length === 0 && <div className="text-[13px] text-gray-400">Промокодов нет</div>}
          {promos.list.map(p => (
            <div key={p.code} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0 gap-2">
              <div>
                <span className="font-mono text-[13px] font-medium text-gray-900">{p.code}</span>
                <span className="ml-2 text-[11px] text-gray-400">{p.discount} · {DURATION_LABELS[p.duration] ?? p.duration}</span>
                {p.expires_at && <span className="ml-2 text-[11px] text-gray-400">до {p.expires_at}</span>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-[11px] text-gray-400">{p.times_redeemed}×</span>
                {p.active
                  ? <span className="text-[10px] bg-green-50 text-green-700 px-2 py-0.5 rounded">активен</span>
                  : <span className="text-[10px] bg-gray-100 text-gray-400 px-2 py-0.5 rounded">выключен</span>}
                {p.active && (
                  <button onClick={() => handleDeactivate(p.id)}
                    className="text-[11px] text-red-400 hover:text-red-600 px-1">✕</button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Форма создания */}
        <div className="border border-gray-100 rounded-xl p-4">
          <div className="text-[13px] font-medium text-gray-500 mb-4">Создать промокод</div>
          <form onSubmit={handleCreate} className="space-y-3">

            <div>
              <label className="text-[11px] text-gray-400 uppercase tracking-wide block mb-1">Код</label>
              <input required value={form.code} onChange={e => set("code", e.target.value.toUpperCase())}
                placeholder="ASTRO30" maxLength={20}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-violet-400" />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[11px] text-gray-400 uppercase tracking-wide block mb-1">Тип скидки</label>
                <select value={form.discount_type} onChange={e => set("discount_type", e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-violet-400">
                  <option value="percent">Процент (%)</option>
                  <option value="amount">Сумма (₽)</option>
                </select>
              </div>
              <div>
                <label className="text-[11px] text-gray-400 uppercase tracking-wide block mb-1">
                  Размер {form.discount_type === "percent" ? "%" : "₽"}
                </label>
                <input type="number" required min={1} max={form.discount_type === "percent" ? 100 : 10000}
                  value={form.discount_value} onChange={e => set("discount_value", e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-violet-400" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[11px] text-gray-400 uppercase tracking-wide block mb-1">Длительность</label>
                <select value={form.duration} onChange={e => set("duration", e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-violet-400">
                  <option value="once">Один раз</option>
                  <option value="repeating">Несколько мес.</option>
                  <option value="forever">Навсегда</option>
                </select>
              </div>
              {form.duration === "repeating" && (
                <div>
                  <label className="text-[11px] text-gray-400 uppercase tracking-wide block mb-1">Кол-во мес.</label>
                  <input type="number" min={1} max={24} value={form.duration_months}
                    onChange={e => set("duration_months", e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-violet-400" />
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[11px] text-gray-400 uppercase tracking-wide block mb-1">Срок действия</label>
                <input type="date" value={form.expires_at} onChange={e => set("expires_at", e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-violet-400" />
              </div>
              <div>
                <label className="text-[11px] text-gray-400 uppercase tracking-wide block mb-1">Макс. применений</label>
                <input type="number" min={1} placeholder="∞" value={form.max_redemptions}
                  onChange={e => set("max_redemptions", e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-violet-400" />
              </div>
            </div>

            {msg && (
              <div className={`text-[12px] px-3 py-2 rounded-lg ${msg.ok ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
                {msg.text}
              </div>
            )}

            <button type="submit" disabled={saving}
              className="w-full bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white text-[13px] font-medium py-2 rounded-lg transition-colors">
              {saving ? "Создаём в Stripe..." : "Создать промокод"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

// ─── Основной компонент ────────────────────────────────────────────────────────

export default function AdminPage() {
  const { user, authFetch } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsRes, promosRes] = await Promise.all([
        authFetch("/api/v1/admin/stats"),
        authFetch("/api/v1/admin/coupons/stats"),
      ]);
      const stats = statsRes.ok ? await statsRes.json() : {};
      const promos = promosRes.ok ? await promosRes.json() : MOCK.promos;
      setData({ ...MOCK, ...stats, promos });
    } catch {
      setData({ ...MOCK });
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  async function handleExport() {
    setExporting(true);
    try {
      const res = await authFetch("/api/v1/admin/export");
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `astrea_stats_${new Date().toISOString().slice(0,10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // fallback: скачать моки
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `astrea_stats_${new Date().toISOString().slice(0,10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  useEffect(() => {
    if (!user) { navigate("/"); return; }
    if (!user.is_admin) { navigate("/"); return; }
    load();
  }, [user, navigate, load]);

  if (!user || !user.is_admin) return null;

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-100">
        <h1 className="text-[18px] font-medium text-gray-900">Кабинет управляющего · Astrea Timeline</h1>
        <div className="flex gap-2">
          <button onClick={handleExport} disabled={exporting}
            className="text-[11px] px-3 py-1.5 border border-gray-200 rounded-lg text-gray-500 hover:bg-gray-50 transition-colors disabled:opacity-50">
            {exporting ? "Экспорт..." : "↓ Экспорт JSON"}
          </button>
          <button onClick={load}
            className="text-[11px] px-3 py-1.5 border border-gray-200 rounded-lg text-gray-500 hover:bg-gray-50 transition-colors">
            {loading ? "Загрузка..." : "⟳ Обновить"}
          </button>
        </div>
      </div>

      <div className="flex gap-1 mb-6 overflow-x-auto">
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)}
            className={`px-3 py-1.5 text-[13px] rounded-lg border transition-colors whitespace-nowrap
              ${tab === i ? "bg-gray-100 text-gray-900 border-gray-200 font-medium" : "border-transparent text-gray-500 hover:bg-gray-50"}`}>
            {t}
          </button>
        ))}
      </div>

      {loading && <div className="text-center py-20 text-gray-400">Загрузка...</div>}
      {error && <div className="text-center py-20 text-red-400">{error}</div>}
      {data && !loading && (
        <>
          {tab === 0 && <TabOverview d={data} />}
          {tab === 1 && <TabUsers d={data} />}
          {tab === 2 && <TabRevenue d={data} />}
          {tab === 3 && <TabAI d={data} />}
          {tab === 4 && <TabEmails d={data} />}
          {tab === 5 && <TabPromos d={data} authFetch={authFetch} onReload={load} />}
        </>
      )}
    </div>
  );
}
