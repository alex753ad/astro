import { useState } from "react";
import { BACKEND_BASE as API_BASE } from "../config";

// E8 — «Здесь что-то не так». Плавающая кнопка на каждом экране.
// Монтируется ОДИН раз в корне приложения (App.jsx), появляется поверх всего.
// Пишет в POST /api/v1/feedback с контекстом экрана (url + screen).

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

const MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024;
const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/webp"];

export default function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [screenshot, setScreenshot] = useState(null); // File
  const [screenshotPreview, setScreenshotPreview] = useState(null); // object URL
  const [fileError, setFileError] = useState("");
  const [state, setState] = useState("idle"); // idle | sending | done | error
  const [doneMessage, setDoneMessage] = useState("Спасибо — записали. Это помогает нам чинить.");

  function pickFile(file) {
    setFileError("");
    if (!file) return;
    if (!ALLOWED_TYPES.includes(file.type)) {
      setFileError("Нужен файл PNG, JPEG или WEBP");
      return;
    }
    if (file.size > MAX_SCREENSHOT_BYTES) {
      setFileError("Файл больше 5 МБ — приложите поменьше");
      return;
    }
    setScreenshot(file);
    setScreenshotPreview(URL.createObjectURL(file));
  }

  function clearFile() {
    if (screenshotPreview) URL.revokeObjectURL(screenshotPreview);
    setScreenshot(null);
    setScreenshotPreview(null);
    setFileError("");
  }

  async function submit() {
    setState("sending");
    try {
      const token = localStorage.getItem("astro_access_token");
      const form = new FormData();
      form.append("screen", screenFromPath(window.location.pathname));
      form.append("url", window.location.href);
      if (message.trim()) form.append("message", message.trim());
      form.append("user_agent", navigator.userAgent);
      if (screenshot) form.append("screenshot", screenshot);

      const res = await fetch(`${API_BASE}/api/v1/feedback`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
      const data = await res.json().catch(() => ({}));
      setDoneMessage(data.message || "Спасибо — записали. Это помогает нам чинить.");
      setState("done");
      setMessage("");
      clearFile();
      setTimeout(() => { setOpen(false); setState("idle"); }, 2200);
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
            <div className="fb-done">{doneMessage}</div>
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

              {screenshotPreview ? (
                <div className="fb-preview">
                  <img src={screenshotPreview} alt="Скриншот" />
                  <button className="fb-preview-remove" onClick={clearFile}>Убрать</button>
                </div>
              ) : (
                <label className="fb-file-label">
                  Приложить скриншот (необязательно)
                  <input
                    type="file"
                    accept="image/*"
                    className="fb-file-input"
                    onChange={(e) => pickFile(e.target.files?.[0])}
                  />
                </label>
              )}
              {fileError && <div className="fb-err">{fileError}</div>}

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
.fb-file-label{
  display:block; margin-top:10px; font-size:12px; color:var(--text-secondary);
  cursor:pointer;
}
.fb-file-input{ display:block; margin-top:6px; font-size:12px; color:var(--text-secondary); width:100%; }
.fb-preview{ margin-top:10px; position:relative; }
.fb-preview img{
  width:100%; max-height:120px; object-fit:cover; border-radius:8px;
  border:1px solid var(--bg-deeper);
}
.fb-preview-remove{
  position:absolute; top:6px; right:6px; background:rgba(20,16,32,.75); color:#fff;
  border:none; border-radius:8px; padding:4px 10px; font-size:11px; cursor:pointer;
}
`;
