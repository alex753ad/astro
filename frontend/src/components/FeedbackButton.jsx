import { useState } from "react";

// E8 — «Здесь что-то не так». Плавающая кнопка на каждом экране.
// Монтируется ОДИН раз в корне приложения (App.jsx), появляется поверх всего.
// Пишет в POST /api/v1/feedback с контекстом экрана (url + screen).

const API_BASE = "https://astro-production-abcc.up.railway.app";

// Логический экран из pathname (для группировки точек трения в метриках)
function screenFromPath(path) {
  if (path.startsWith("/planner")) return "planner";
  if (path.startsWith("/transits")) return "transits";
  if (path.startsWith("/lunar")) return "lunar";
  if (path.startsWith("/profile")) return "profile";
  if (path.startsWith("/crm") || path.startsWith("/clients")) return "crm";
  if (path === "/" || path.startsWith("/home")) return "home";
  return path.split("/")[1] || "unknown";
}

export default function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [state, setState] = useState("idle"); // idle | sending | done | error

  async function submit() {
    setState("sending");
    try {
      const token = localStorage.getItem("astro_access_token");
      const res = await fetch(`${API_BASE}/api/v1/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          screen: screenFromPath(window.location.pathname),
          url: window.location.href,
          message: message.trim() || null,
        }),
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
      setState("done");
      setMessage("");
      setTimeout(() => { setOpen(false); setState("idle"); }, 1600);
    } catch {
      setState("error");
    }
  }

  return (
    <>
      <style>{fbStyles}</style>

      {!open && (
        <button className="fb-fab" onClick={() => setOpen(true)}
                aria-label="Здесь что-то не так">
          ⚠️ Здесь что-то не так
        </button>
      )}

      {open && (
        <div className="fb-panel">
          {state === "done" ? (
            <div className="fb-done">Спасибо — записали. Это помогает нам чинить.</div>
          ) : (
            <>
              <div className="fb-title">Что не так на этом экране?</div>
              <textarea
                className="fb-input"
                placeholder="Опишите проблему (необязательно)"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={3}
              />
              {state === "error" && (
                <div className="fb-err">Не отправилось. Попробуйте ещё раз.</div>
              )}
              <div className="fb-actions">
                <button className="fb-cancel" onClick={() => { setOpen(false); setState("idle"); }}>
                  Отмена
                </button>
                <button className="fb-send" disabled={state === "sending"} onClick={submit}>
                  {state === "sending" ? "Отправляем…" : "Отправить"}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}

const fbStyles = `
.fb-fab{
  position:fixed; right:16px; bottom:16px; z-index:9999;
  background:rgba(30,22,50,.92); color:#fff; border:1px solid var(--bg-deeper);
  border-radius:22px; padding:9px 15px; font-size:13px; font-weight:600;
  cursor:pointer; backdrop-filter:blur(6px); box-shadow:0 4px 16px rgba(0,0,0,.3);
}
.fb-fab:hover{ background:rgba(45,33,74,.98); }
.fb-panel{
  position:fixed; right:16px; bottom:16px; z-index:9999; width:300px;
  background:var(--bg-card); border:1px solid var(--bg-deeper); border-radius:14px;
  padding:16px; box-shadow:0 8px 32px rgba(0,0,0,.45);
}
.fb-title{ color:var(--text-primary); font-size:14px; font-weight:700; margin-bottom:10px; }
.fb-input{
  width:100%; box-sizing:border-box; background:var(--bg); color:var(--text-primary);
  border:1px solid var(--bg-deeper); border-radius:10px; padding:10px; font-size:13px;
  resize:vertical; font-family:inherit;
}
.fb-actions{ display:flex; gap:8px; justify-content:flex-end; margin-top:12px; }
.fb-cancel{
  background:transparent; color:var(--text-secondary); border:none; padding:8px 12px;
  font-size:13px; cursor:pointer;
}
.fb-send{
  background:linear-gradient(135deg,var(--accent),var(--accent)); color:#fff; border:none;
  border-radius:10px; padding:8px 16px; font-size:13px; font-weight:700; cursor:pointer;
}
.fb-send:disabled{ opacity:.6; cursor:default; }
.fb-err{ color:var(--color-danger); font-size:12px; margin-top:8px; }
.fb-done{ color:var(--text-primary); font-size:13px; line-height:1.5; padding:4px 0; }
`;
