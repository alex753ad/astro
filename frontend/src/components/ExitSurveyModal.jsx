import { useEffect, useState } from "react";

// E10 — Exit-survey. Два режима одним компонентом:
//   1) Модалка перед активным уходом (удаление аккаунта / отключение):
//        <ExitSurveyModal moment="active" onDone={handleActualDelete} onClose={...} />
//      onDone вызывается ПОСЛЕ отправки причины — там и делайте DELETE /auth/me.
//   2) Страница по ссылке из письма /exit-survey?m=dormant&u=<id>:
//        смонтировать <ExitSurveyModal page /> на маршруте /exit-survey —
//        moment и user_id берутся из query.

const API_BASE = "https://astro-production-abcc.up.railway.app";

export default function ExitSurveyModal({
  moment: momentProp,
  page = false,
  onDone,
  onClose,
}) {
  const [reasons, setReasons] = useState([]);
  const [selected, setSelected] = useState(null);
  const [text, setText] = useState("");
  const [state, setState] = useState("idle"); // idle | sending | done

  // query-параметры для режима страницы
  const params = new URLSearchParams(window.location.search);
  const moment = momentProp || params.get("m") || "active";
  const urlUser = params.get("u") || null;

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/exit-survey/reasons`)
      .then((r) => r.json())
      .then((d) => setReasons(d.reasons || []))
      .catch(() => setReasons([]));
  }, []);

  async function submit() {
    setState("sending");
    const token = localStorage.getItem("astro_access_token");
    let userId = urlUser;
    if (!userId) {
      try { userId = JSON.parse(localStorage.getItem("astro_user") || "{}").id || null; }
      catch { userId = null; }
    }
    try {
      await fetch(`${API_BASE}/api/v1/exit-survey`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          moment,
          reason_code: selected,
          reason_text: text.trim() || null,
          user_id: userId,
        }),
      });
    } catch { /* причина — не критично, не блокируем уход */ }
    setState("done");
    if (onDone) setTimeout(onDone, 400); // затем — фактическое удаление/закрытие
  }

  const Wrap = ({ children }) =>
    page ? <div className="xs-page">{children}</div>
         : <div className="xs-overlay" onClick={onClose}>
             <div className="xs-card" onClick={(e) => e.stopPropagation()}>{children}</div>
           </div>;

  if (state === "done") {
    return (
      <>
        <style>{xsStyles}</style>
        <Wrap>
          <div className="xs-thanks">
            Спасибо. Ваш ответ помогает нам стать лучше.
            {page && <div className="xs-sub">Окно можно закрыть.</div>}
          </div>
        </Wrap>
      </>
    );
  }

  const title =
    moment === "end_of_month" ? "Почему вы не остались?"
    : moment === "dormant"    ? "Что-то пошло не так?"
    :                           "Почему вы уходите?";

  return (
    <>
      <style>{xsStyles}</style>
      <Wrap>
        <div className="xs-title">{title}</div>
        <div className="xs-list">
          {reasons.map((r) => (
            <button
              key={r.code}
              className={`xs-opt ${selected === r.code ? "xs-opt-on" : ""}`}
              onClick={() => setSelected(r.code)}
            >
              {r.label}
            </button>
          ))}
        </div>
        {selected === "other" && (
          <textarea
            className="xs-text"
            placeholder="Расскажите подробнее"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
          />
        )}
        <div className="xs-actions">
          {!page && (
            <button className="xs-skip" onClick={onDone || onClose}>
              Пропустить
            </button>
          )}
          <button
            className="xs-send"
            disabled={!selected || state === "sending"}
            onClick={submit}
          >
            {state === "sending" ? "Отправляем…" : "Отправить"}
          </button>
        </div>
      </Wrap>
    </>
  );
}

const xsStyles = `
.xs-overlay{
  position:fixed; inset:0; z-index:10000; background:rgba(8,5,18,.72);
  display:flex; align-items:center; justify-content:center; padding:20px;
  backdrop-filter:blur(4px);
}
.xs-card, .xs-page{
  width:100%; max-width:380px; background:#1b1430; border:1px solid #4a3a6e;
  border-radius:16px; padding:22px; box-shadow:0 12px 40px rgba(0,0,0,.5);
}
.xs-page{ margin:48px auto; }
.xs-title{ color:#e9ddff; font-size:17px; font-weight:700; margin-bottom:16px; }
.xs-list{ display:flex; flex-direction:column; gap:8px; }
.xs-opt{
  text-align:left; background:#120d24; color:#cfc2ea; border:1px solid #3a2e5c;
  border-radius:10px; padding:11px 13px; font-size:14px; cursor:pointer;
}
.xs-opt:hover{ border-color:#6a54a0; }
.xs-opt-on{ background:#2a1f4a; border-color:#9060C8; color:#fff; }
.xs-text{
  width:100%; box-sizing:border-box; margin-top:10px; background:#120d24;
  color:#e9ddff; border:1px solid #3a2e5c; border-radius:10px; padding:10px;
  font-size:13px; resize:vertical; font-family:inherit;
}
.xs-actions{ display:flex; gap:8px; justify-content:flex-end; margin-top:16px; }
.xs-skip{ background:transparent; color:#a898c8; border:none; padding:9px 12px;
  font-size:13px; cursor:pointer; }
.xs-send{
  background:linear-gradient(135deg,#9060C8,#C060A0); color:#fff; border:none;
  border-radius:10px; padding:9px 18px; font-size:14px; font-weight:700; cursor:pointer;
}
.xs-send:disabled{ opacity:.5; cursor:default; }
.xs-thanks{ color:#b9ffcf; font-size:15px; line-height:1.6; text-align:center; padding:12px; }
.xs-sub{ color:#8f7fb5; font-size:13px; margin-top:8px; }
`;
