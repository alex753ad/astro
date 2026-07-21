import { useEffect, useState } from "react";
import { BACKEND_BASE as API_BASE } from "../config";

// E9 — read-only слой CRM для экс-пилотного астролога.
//
// Экспортирует:
//   useCrmAccess()      — { mode, loading }  (full | readonly | none)
//   <CrmReadOnlyBanner> — плашка сверху витрины в режиме readonly
//   <CrmLock feature clientName onClose /> — модалка-замок при клике по
//                          заблокированному действию (тексты — согласованы)
//   guardWrite(res, show) — помощник: ловит 403 crm_readonly и открывает замок

// ── доступ ──
export function useCrmAccess() {
  const [mode, setMode] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const token = localStorage.getItem("astro_access_token");
    fetch(`${API_BASE}/api/v1/crm/access`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((d) => setMode(d.mode || "none"))
      .catch(() => setMode("none"))
      .finally(() => setLoading(false));
  }, []);
  return { mode, loading };
}

// ── помощник для fetch-ответов мутаций ──
// Вызов: const res = await fetch(...); if (guardWrite(res, setLock)) return;
export async function guardWrite(res, showLock, feature, clientName) {
  if (res.status === 403) {
    try {
      const body = await res.clone().json();
      const err = body?.detail?.error || body?.error;
      if (err === "crm_readonly") {
        showLock({ feature: feature || "generic", clientName });
        return true;
      }
    } catch { /* ignore */ }
  }
  return false;
}

// ── баннер режима read-only ──
export function CrmReadOnlyBanner() {
  return (
    <>
      <style>{roStyles}</style>
      <div className="ro-banner">
        <span className="ro-dot" />
        Ваш месяц закончился — CRM открыта в режиме просмотра. Данные и карты
        клиентов сохранены. Действия доступны на Premium.
      </div>
    </>
  );
}

// ── тексты-замки (согласованный тёплый регистр) ──
function lockText(feature, name) {
  const who = name || "клиента";
  switch (feature) {
    case "transits":
    case "broadcast":
      return {
        title: "Написать клиенту",
        body:
          `У ${who} сейчас идёт активный период — хороший момент напомнить о себе. ` +
          `Но кнопка здесь закрыта. На Premium вы бы уже написали ему — и, скорее ` +
          `всего, получили бы сессию.`,
      };
    case "consultations":
    case "brief":
      return {
        title: "Консультации и бриф",
        body:
          `История с ${who} — в ваших заметках где-то. Жаль, что не здесь: бриф ` +
          `и записи сессий на Premium собраны в одном месте, и перед следующей ` +
          `встречей вам не нужно было бы ничего искать.`,
      };
    case "portal":
      return {
        title: "Портал клиента",
        body:
          `Клиентский портал для ${who} на Premium: карта и домашние задания ` +
          `под вашим брендом, доступные по ссылке. Сейчас создание закрыто.`,
      };
    case "report":
      return {
        title: "PDF-отчёт",
        body:
          `Брендированный PDF-отчёт для ${who} доступен на Premium. ` +
          `Данные карты сохранены — вернуть генерацию можно в любой момент.`,
      };
    default:
      return {
        title: "Действие закрыто",
        body:
          `Это действие доступно на Premium. Ваши данные и карты клиентов ` +
          `сохранены — ничего не потеряно.`,
      };
  }
}

// ── модалка-замок ──
export function CrmLock({ feature, clientName, onClose, onUpgrade }) {
  const t = lockText(feature, clientName);
  return (
    <>
      <style>{roStyles}</style>
      <div className="ro-overlay" onClick={onClose}>
        <div className="ro-card" onClick={(e) => e.stopPropagation()}>
          <div className="ro-lock">🔒</div>
          <div className="ro-title">{t.title}</div>
          <div className="ro-body">{t.body}</div>
          <div className="ro-actions">
            <button className="ro-later" onClick={onClose}>Позже</button>
            <button
              className="ro-up"
              onClick={onUpgrade || (() => { window.location.href = "/profile?upgrade=premium"; })}
            >
              Вернуться на Premium
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

const roStyles = `
.ro-banner{
  display:flex; align-items:center; gap:10px; margin:0 0 14px;
  background:rgba(144,96,200,.12); border:1px solid var(--bg-deeper); border-radius:12px;
  padding:11px 15px; color:var(--accent-glow); font-size:13px; line-height:1.5;
}
.ro-dot{ width:8px; height:8px; border-radius:50%; background:var(--accent); flex:0 0 auto; }
.ro-overlay{
  position:fixed; inset:0; z-index:10000; background:rgba(8,5,18,.72);
  display:flex; align-items:center; justify-content:center; padding:20px;
  backdrop-filter:blur(4px);
}
.ro-card{
  width:100%; max-width:380px; background:var(--bg-card); border:1px solid var(--bg-deeper);
  border-radius:16px; padding:24px; box-shadow:0 12px 40px rgba(0,0,0,.5); text-align:center;
}
.ro-lock{ font-size:26px; margin-bottom:8px; }
.ro-title{ color:var(--accent-muted); font-size:17px; font-weight:700; margin-bottom:10px; }
.ro-body{ color:var(--accent-glow); font-size:14px; line-height:1.6; margin-bottom:18px; }
.ro-actions{ display:flex; gap:10px; justify-content:center; }
.ro-later{ background:transparent; color:var(--text-secondary); border:none; padding:9px 14px;
  font-size:13px; cursor:pointer; }
.ro-up{
  background:linear-gradient(135deg,var(--accent),var(--accent)); color:#fff; border:none;
  border-radius:10px; padding:9px 18px; font-size:14px; font-weight:700; cursor:pointer;
}
`;

export default { useCrmAccess, guardWrite, CrmReadOnlyBanner, CrmLock };
