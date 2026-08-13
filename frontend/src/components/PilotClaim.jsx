import { useEffect, useState } from "react";
import { BACKEND_BASE as API_BASE } from "../config";
import { TIER_NAMES } from "../constants";
import useAuth from "../hooks/useAuth.jsx";

// Страница /pilot/claim?t=<token> — активация пилота по одноразовой ссылке из бота.
//
// Поток:
//   1) читаем ?t=<token>;
//   2) если не залогинен — сохраняем токен и открываем модалку входа
//      (App.jsx: onShowAuth) поверх этой же страницы;
//   3) как только accessToken из useAuth() появится — эффект перезапускается
//      сам (без навигации) и продолжает POST /pilot/claim.
//
// Раньше редиректило на "/login?next=..." — такого маршрута в App.jsx нет
// (вход — модалка, не страница), пользователь просто зависал на пустой
// странице, активация не происходила вовсе. Модалка открывается поверх
// /pilot/claim (тот же путь), поэтому AuthModal.navigate(returnTo) сюда же
// не перемонтирует компонент — реагируем на сам accessToken, а не на роут.

const LS_KEY = "pilot_claim_token";

export default function PilotClaim({ onShowAuth }) {
  const { accessToken, authFetch, updateUser } = useAuth();
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

    if (!accessToken) {
      // не залогинен — сохраняем токен и открываем модалку входа
      localStorage.setItem(LS_KEY, token);
      onShowAuth?.("/pilot/claim");
      return;
    }

    claim(token);
  }, [accessToken, onShowAuth]);

  async function claim(token) {
    setState("claiming");
    try {
      await authFetch(`${API_BASE}/api/v1/pilot/claim`, {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      localStorage.removeItem(LS_KEY);
      updateUser({ tier: "premium" });
      setState("ok");
      setTimeout(() => { window.location.href = "/planner"; }, 1800);
    } catch (e) {
      setState("error");
      setError(errorText(e?.message));
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
