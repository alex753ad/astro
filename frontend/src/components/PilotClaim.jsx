import { useEffect, useState } from "react";
import { BACKEND_BASE as API_BASE } from "../config";
import { TIER_NAMES } from "../constants";

// Страница /pilot/claim?t=<token> — активация пилота по одноразовой ссылке из бота.
//
// Поток:
//   1) читаем ?t=<token>;
//   2) если не залогинен — сохраняем токен и ведём на вход по почте (/login);
//      после входа возвращаемся сюда (см. LoginPage-заметку в wiring);
//   3) если залогинен — POST /pilot/claim {token}, показываем результат.

const LS_KEY = "pilot_claim_token";

export default function PilotClaim() {
  const [state, setState] = useState("init"); // init | claiming | ok | error
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("t") || localStorage.getItem(LS_KEY);
    if (!token) {
      setState("error");
      setError("Ссылка недействительна. Откройте бота @astreyatimelinebot заново.");
      return;
    }

    const access = localStorage.getItem("astro_access_token");
    if (!access) {
      // не залогинен — сохраняем токен и идём на вход
      localStorage.setItem(LS_KEY, token);
      const next = encodeURIComponent("/pilot/claim");
      window.location.href = `/login?next=${next}`;
      return;
    }

    claim(token, access);
  }, []);

  async function claim(token, access) {
    setState("claiming");
    try {
      const res = await fetch(`${API_BASE}/api/v1/pilot/claim`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${access}`,
        },
        body: JSON.stringify({ token }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setState("error");
        setError(errorText(body?.detail));
        return;
      }
      localStorage.removeItem(LS_KEY);
      // обновим tier в локальном профиле
      try {
        const u = JSON.parse(localStorage.getItem("astro_user") || "{}");
        u.tier = "premium";
        localStorage.setItem("astro_user", JSON.stringify(u));
      } catch { /* ignore */ }
      setState("ok");
      setTimeout(() => { window.location.href = "/planner"; }, 1800);
    } catch {
      setState("error");
      setError("Не удалось связаться с сервером. Попробуйте ещё раз.");
    }
  }

  function errorText(detail) {
    switch (detail) {
      case "already_pilot":  return "На этом аккаунте пилот уже активирован.";
      case "tg_already_used": return "Этот Telegram уже активировал пилот на другом аккаунте.";
      case "token_used":     return "Ссылка уже использована. Запросите новую в боте.";
      case "token_expired":  return "Ссылка истекла. Откройте бота и получите новую.";
      case "invalid_token":  return "Ссылка недействительна. Откройте бота заново.";
      default:               return "Не удалось активировать пилот. Попробуйте позже.";
    }
  }

  return (
    <>
      <style>{pcStyles}</style>
      <div className="pc-wrap">
        <div className="pc-card">
          {(state === "init" || state === "claiming") && (
            <>
              <div className="pc-spin" />
              <div className="pc-title">Активируем ваш месяц…</div>
            </>
          )}
          {state === "ok" && (
            <>
              <div className="pc-badge">✦</div>
              <div className="pc-title">{TIER_NAMES.premium} на 30 дней открыт</div>
              <div className="pc-sub">Открываем ваш планер…</div>
            </>
          )}
          {state === "error" && (
            <>
              <div className="pc-err-ico">·</div>
              <div className="pc-title">Не получилось</div>
              <div className="pc-sub">{error}</div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

const pcStyles = `
.pc-wrap{ min-height:70vh; display:flex; align-items:center; justify-content:center; padding:24px; }
.pc-card{
  width:100%; max-width:360px; background:var(--bg-card); border:1px solid var(--bg-deeper);
  border-radius:16px; padding:32px 24px; text-align:center;
  box-shadow:0 12px 40px rgba(0,0,0,.4);
}
.pc-title{ color:var(--accent-muted); font-size:18px; font-weight:700; margin-top:14px; }
.pc-sub{ color:var(--accent-glow); font-size:14px; line-height:1.6; margin-top:10px; }
.pc-badge{ font-size:34px; color:var(--accent); }
.pc-err-ico{ font-size:34px; color:var(--color-danger); line-height:1; }
.pc-spin{
  width:34px; height:34px; margin:0 auto; border-radius:50%;
  border:3px solid var(--bg-deeper); border-top-color:var(--accent); animation:pcspin .8s linear infinite;
}
@keyframes pcspin{ to{ transform:rotate(360deg); } }
`;
