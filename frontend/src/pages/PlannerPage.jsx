import { useState, useEffect, useRef, useMemo } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import MotionButton from "../components/MotionButton";
import { authFetch, createCheckoutSession, apiErrorText } from "../api/client";
import { useToast } from "../components/Toast";
import { BACKEND_BASE as API_BASE } from "../config";
import { TIER_NAMES } from "../constants";
import TierOfferModal from "../components/TierOfferModal";
import { lockBanner, lockShort, lockText, plannerMonthsAhead } from "../lib/tierCatalog";
import { offerFor } from "../lib/offerRule";
import { buildUpcoming, datesInWords, formatWeekRange, planetCardTarget, railPositions, shortDate } from "../lib/plannerDates";
import { deviceTimeZone } from "../lib/deviceTimezone";
const GCAL_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const GCAL_SCOPE = "https://www.googleapis.com/auth/calendar.events";

function getMonthName(date) {
  return date.toLocaleString("ru-RU", { month: "long", year: "numeric" });
}

// "11–17 августа" (или "29 июля – 4 августа", если неделя между месяцами)

/* zodiac data-color, intentional */
// Плоские акцентные цвета планет — для бордеров/бейджей (не для кружков, см. PlanetDot ниже).
/*
 * ⚠️ Луна — серебристо-голубая, а не серая (решение владельца 16.09.2026).
 * Прежний #8E8E96 был нейтральным серым: рядом с цветными планетами её период
 * читался как неактивный, и на приёмке ленты это назвали дефектом. Новый тон —
 * hue 203, насыщенность 26% (было 3%), светлота подобрана по контрасту 4.5:1 к
 * фону светлой темы. Мобильное приложение берёт тот же тон своими токенами
 * `--planet-moon` (mobile.css), где светлота отдельно подогнана под тёмную
 * тему; второго ИСТОЧНИКА при этом нет — есть одна палитра и её пересчёт под
 * фон, как у всех остальных планет.
 */
const PLANET_COLORS = {
  sun: "#FDD85D", moon: "#4F7287", mercury: "#3498DB", venus: "#EC4899",  /* zodiac data-color, intentional */
  mars: "#E74C3C", jupiter: "#9B59B6", saturn: "#1E3A6E", uranus: "#1ABC9C",  /* zodiac data-color, intentional */
  neptune: "#3F3D9E", pluto: "#7C3AED",  /* zodiac data-color, intentional */
};

/* zodiac data-color, intentional */
// Градиентные пары для кружков планет: radial-gradient(circle at 34% 30%, c1, c2).
const PLANET_DOT_GRADIENTS = {
  sun:     { c1: "#FFE896", c2: "#FDD85D" }, // рендерится особо — см. PlanetDot (плоское + свечение)
  moon:    { c1: "#9DB6C4", c2: "#4F7287" },
  mercury: { c1: "#8FD3F4", c2: "#3498DB" },
  venus:   { c1: "#FF9EC4", c2: "#EC4899" },
  mars:    { c1: "#FF6B5A", c2: "#E74C3C" },
  jupiter: { c1: "#C9A7F0", c2: "#9B59B6" },  /* zodiac data-color, intentional */
  saturn:  { c1: "#3F5C8A", c2: "#1E3A6E" },
  uranus:  { c1: "#7FE7D8", c2: "#1ABC9C" },
  neptune: { c1: "#7C86E0", c2: "#3F3D9E" },
  pluto:   { c1: "#B98BE0", c2: "#7C3AED" },  /* zodiac data-color, intentional */
};

/* zodiac data-color, intentional */
// Фазы Луны, затмения и узлы — не планеты, но рендерятся тем же PlanetDot.
const PHASE_DOT_STYLES = {
  new_moon:      { c1: "#5A5A64", c2: "#2E2E36" },
  full_moon:     { solid: "#FDC05D" },
  solar_eclipse: { solid: "#1a1230", ring: "#FFE000" },
  lunar_eclipse: { solid: "#1a1230", ring: "#FFE000" },
  north_node:    { c1: "#FFB86B", c2: "#E8842A", node: "☊" },
  south_node:    { c1: "#FFB86B", c2: "#E8842A", node: "☋" },
};

// Тип не распознан (неизвестная планета/фаза) — нейтральный серый кружок.
const FALLBACK_DOT_GRADIENT = { c1: "#A6A6B0", c2: "#6E6E78" };

// Кружок планеты/фазы: градиентная заливка + опциональные символ узла и ретро-метка.
function PlanetDot({ type, size = 18, retro = false, node }) {
  const style = PLANET_DOT_GRADIENTS[type] || PHASE_DOT_STYLES[type] || FALLBACK_DOT_GRADIENT;
  const symbol = node ?? style.node;

  let background, boxShadow, border;
  if (style.solid) {
    background = style.solid;
    if (style.ring) border = `${Math.max(1, size * 0.11)}px solid ${style.ring}`;
  } else if (type === "sun") {
    background = `radial-gradient(circle at 50% 42%, ${style.c1}, ${style.c2} 70%)`;
    boxShadow = "0 0 5px rgba(253,216,93,0.5)";
  } else {
    background = `radial-gradient(circle at 34% 30%, ${style.c1}, ${style.c2})`;
  }

  return (
    <span style={{
      position: "relative", display: "inline-block", flexShrink: 0,
      width: size, height: size, borderRadius: "50%",
      background, boxShadow, border,
    }}>
      {symbol && (
        <span style={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "#fff", fontSize: size * 0.55, lineHeight: 1,
        }}>{symbol}</span>
      )}
      {retro && (
        <span style={{
          position: "absolute", bottom: -3, right: -(size * 0.3),
          fontSize: size * 0.5, color: "#E11D0C", fontFamily: "Georgia, serif", fontWeight: 700,
          textShadow: "-1px 0 #fff, 1px 0 #fff, 0 -1px #fff, 0 1px #fff",
        }}>R</span>
      )}
    </span>
  );
}


// ── Google Calendar: авторизация через GIS + экспорт ──────────────────────────
//
// 02.09.2026: переписано с implicit flow на Google Identity Services.
//
// Раньше здесь был window.open на accounts.google.com и setInterval, который
// каждые 300 мс пытался прочитать popup.location.href в ожидании
// #access_token. Этот приём несовместим с заголовком
// `Cross-Origin-Opener-Policy: same-origin` (nginx/snippets/security-headers.conf):
// как только попап уходит на чужой origin, браузер помещает его в отдельную
// группу контекстов и ссылка на окно обрывается НАВСЕГДА — в том числе после
// возврата попапа на наш origin. Отсюда были два разных симптома одной
// причины: на десктопе чтение location бросало SecurityError, его глотал
// пустой catch, и опрос крутился вечно (вход прошёл, экспорт не начался); на
// мобильном оборванная ссылка сразу отдавала closed === true, и код отклонял
// промис с «Авторизация отменена» ещё до входа.
//
// ⚠️ Здесь до 03.09.2026 стояло: «COOP не снимаем — GIS сам управляет окном,
// opener ему не нужен». Половина этого неверна, и на ней потерян заход.
// Opener не нужен GIS для ПЕРЕДАЧИ токена — он приходит в колбэк. Но для
// определения ОТМЕНЫ он следит за окном, и same-origin эту связь рвал: окно
// выглядело закрытым, error_callback приходил с popup_closed через ~1.3 с
// после клика при видимо открытом экране выбора аккаунта.
//
// Поэтому COOP не снят, а ослаблен ровно на попапы, которые открываем мы
// сами: same-origin-allow-popups (nginx/snippets/security-headers.conf, там
// же разбор). Изоляция от того, кто открыл НАС, сохранена.
//
// ⚠️ Скрипту GIS нужен `script-src https://accounts.google.com` в CSP
// (nginx/snippets/csp.conf). connect-src и frame-src для Google там уже были.
// Пока CSP в режиме Report-Only, отсутствие источника НЕ проявится: скрипт
// загрузится, всё будет работать, и отвалится молча в день включения боевой
// политики — поэтому правка внесена сразу, тем же коммитом.

const GIS_SRC = "https://accounts.google.com/gsi/client";

// Загрузка скрипта GIS — один раз на вкладку. Промис держим на уровне модуля,
// а не в хуке: страница может смонтировать хук повторно, а тег <script> в
// документе всё равно один.
let gisLoading = null;
function loadGis() {
  if (window.google?.accounts?.oauth2) return Promise.resolve();
  if (gisLoading) return gisLoading;
  gisLoading = new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = GIS_SRC;
    el.async = true;
    el.defer = true;
    el.onload = () => resolve();
    el.onerror = () => {
      // Сбрасываем, иначе одна сетевая ошибка навсегда заблокирует повтор.
      gisLoading = null;
      reject(new Error("Не удалось загрузить Google Identity Services"));
    };
    document.head.appendChild(el);
  });
  return gisLoading;
}

function useGcalExport() {
  // Токен живёт в памяти вкладки и намеренно НЕ кладётся в localStorage:
  // access token действует час, хранить его между сессиями незачем.
  const tokenRef = useRef(null);
  const [status, setStatus] = useState("idle"); // idle | loading | success | error

  function getToken() {
    if (tokenRef.current && tokenRef.current.expiry > Date.now()) {
      return Promise.resolve(tokenRef.current.token);
    }
    if (!GCAL_CLIENT_ID) {
      return Promise.reject(new Error("VITE_GOOGLE_CLIENT_ID не задан в .env"));
    }
    return loadGis().then(
      () =>
        new Promise((resolve, reject) => {
          // Клиент создаём на каждый запрос: колбэки замыкают resolve/reject
          // конкретного промиса. Переиспользуемый клиент потребовал бы
          // хранить их отдельно и разбираться, чей ответ пришёл.
          const client = window.google.accounts.oauth2.initTokenClient({
            client_id: GCAL_CLIENT_ID,
            scope: GCAL_SCOPE,
            callback: (resp) => {
              if (resp.error) {
                reject(new Error(resp.error_description || resp.error));
                return;
              }
              tokenRef.current = {
                token: resp.access_token,
                expiry: Date.now() + Number(resp.expires_in || 3600) * 1000,
              };
              resolve(resp.access_token);
            },
            // error_callback обязателен, и это не перестраховка: закрытое
            // пользователем окно и заблокированный попап приходят ТОЛЬКО
            // сюда, в callback они не попадают. Без него промис остался бы
            // висеть навсегда — ровно тот отказ, ради которого всё и
            // переписывалось.
            error_callback: (err) => {
              const cancelled =
                err?.type === "popup_closed" || err?.type === "user_cancel";
              reject(
                new Error(
                  cancelled
                    ? "Авторизация отменена"
                    : err?.message || "Не удалось авторизоваться в Google"
                )
              );
            },
          });
          client.requestAccessToken();
        })
    );
  }

  // Журнал экспорта. Единственное место, где экспорт вообще виден серверу:
  // сами события уходят из браузера прямо в googleapis.com с токеном
  // пользователя, бэкенд этого запроса не видит. Поэтому без журнала на
  // вопрос «сколько карт реально экспортируют» ответить нечем — ни сейчас,
  // ни задним числом.
  //
  // Ручка, модель и тест написаны давно, но вызывающих не имели: логирование
  // жило в useGoogleCalendar.js, который удалён 02.09.2026 как мёртвый дубль.
  //
  // fire-and-forget: сбой журнала не должен ломать успешный экспорт, поэтому
  // без await и с проглоченной ошибкой. Неавторизованный сюда не дойдёт —
  // кнопка закрыта для free, а ручка требует JWT.
  function _logExport(events, status, errorMsg, chartId) {
    // 03.09.2026: здесь стоял monthOffset — state из PlannerPage, вне scope
    // этого хука (useGcalExport — функция верхнего уровня, не вложена в
    // PlannerPage). ReferenceError бросался ДО вызова authFetch, то есть до
    // .catch(() => {}) на промисе — .catch ловит отказ промиса, а не
    // синхронный throw при подготовке данных. Исключение уходило в try/catch
    // exportEvents и превращало успешный экспорт в «ошибку» на экране, хотя
    // события в Google Calendar уже были созданы.
    //
    // month берём из уже построенных events (buildExportEvents кладёт туда
    // date "YYYY-MM-DD") — то, что и так в scope, вместо пересчёта заново.
    //
    // Вся подготовка — внутри try: fire-and-forget обязан не бросать
    // синхронно, а .catch(() => {}) на authFetch эту гарантию не даёт.
    try {
      const month = events[0]?.date?.slice(0, 7) || "";
      authFetch(`${API_BASE}/api/v1/calendar/export-log`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          month,
          event_count: events.length,
          event_types: [...new Set(events.map((e) => e.type).filter(Boolean))],
          status,
          error_msg: errorMsg || null,
          chart_id: chartId || null,
        }),
      }).catch(() => {});
    } catch {
      // журнал — не более чем журнал; сбой его подготовки не должен мешать
      // пользователю увидеть результат реального экспорта
    }
  }

  // chartId — какую карту выгружаем. На Веге экспорт — для одной карты
  // (TIER_FLAGS gcal_charts); выгрузка идёт из браузера прямо в Google,
  // поэтому сервер спрашиваем ДО неё. Отказ — не ошибка: возвращаем причину,
  // страница открывает окно предложения Лиры.
  async function exportEvents(events, chartId) {
    if (!events?.length) return null;
    try {
      const r = await authFetch(`${API_BASE}/api/v1/calendar/export-allowed?chart_id=${encodeURIComponent(chartId || "")}`);
      const allowed = r.ok ? await r.json() : { allowed: true };
      if (!allowed.allowed) return { blocked: allowed.reason };
    } catch {
      // сеть или сервер недоступны — не мешаем выгрузке, журнал всё равно запишет
    }
    setStatus("loading");
    try {
      const token = await getToken();
      for (const ev of events) {
        if (!ev.date) continue;
        const res = await fetch(
          "https://www.googleapis.com/calendar/v3/calendars/primary/events",
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              summary: ev.summary,
              description: ev.description || "",
              start: { date: ev.date },
              end: { date: ev.date },
              colorId: ev.colorId || "1",
              reminders: { useDefault: false },
            }),
          }
        );
        // Раньше ответ не проверялся вовсе: при 401 или превышении квоты
        // цикл молча доходил до конца и кнопка показывала «Готово», хотя в
        // календаре не появлялось ничего. Отказ, неотличимый от успеха, —
        // худший вид отказа, поэтому проверка добавлена здесь же.
        if (!res.ok) {
          if (res.status === 401) tokenRef.current = null;
          const err = await res.json().catch(() => ({}));
          throw new Error(err?.error?.message || `Google ответил ${res.status}`);
        }
      }
      setStatus("success");
      setTimeout(() => setStatus("idle"), 3500);
      try { _logExport(events, "success", null, chartId); } catch { /* fire-and-forget */ }
    } catch (e) {
      console.error("[gcal]", e);
      setStatus("error");
      setTimeout(() => setStatus("idle"), 4000);
      // 255, а не круглое число: столько в колонке error_msg
      // (models.py, String(255)). Длиннее — падение вставки на Postgres
      // ровно в тот момент, когда журнал нужнее всего.
      try {
        _logExport(events, "error", String(e?.message || e).slice(0, 255), chartId);
      } catch { /* fire-and-forget */ }
    }
  }

  return { exportEvents, status };
}

// ── Стили ─────────────────────────────────────────────────────────────────────

const styles = `
  .planner-root {
    min-height: 100vh;
    background: transparent;
    color: var(--text-primary);
    font-family: var(--font-body);
  }
  .planner-inner {
    max-width: 680px;
    margin: 0 auto;
    padding: 32px 20px;
  }
  .planner-header { margin-bottom: 28px; }
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
    color: var(--accent);
    letter-spacing: -0.5px;
  }
  .planner-subtitle { font-size: 13px; color: var(--text-secondary); margin-top: 2px; }

  .month-nav { display: flex; align-items: center; gap: 6px; }
  .month-nav-btn {
    width: 34px; height: 34px; border-radius: var(--radius-md); border: none;
    background: var(--accent); color: #fff; font-size: 16px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: opacity 0.15s;
  }
  .month-nav-btn.month-nav-locked { background: var(--accent-muted); }
  .month-nav-btn:hover { opacity: 0.85; }
  .month-nav-btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .month-nav-label {
    font-size: 12px; color: var(--text-secondary); background: var(--bg-deeper);
    border: 1px solid var(--border); border-radius: var(--radius-md);
    padding: 6px 14px; font-weight: 600; min-width: 100px; text-align: center;
  }
  .week-header-row {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap;
  }

  .tab-bar {
    display: flex; gap: 4px;
    background: var(--bg-deeper);
    border-radius: var(--radius-lg); padding: 4px; margin-bottom: 28px;
  }
  .tab-btn {
    flex: 1; padding: 9px 12px; border-radius: var(--radius-md); border: none;
    cursor: pointer; font-size: 13px; font-weight: 600;
    font-family: var(--font-body);
    transition: all 0.15s; background: transparent; color: var(--accent);
  }
  .tab-btn.active {
    background: var(--accent); color: #fff;
  }

  .section-header {
    display: flex; align-items: flex-start;
    gap: 10px; margin-bottom: 16px; padding: 4px 0;
  }
  .section-icon {
    width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 15px; flex-shrink: 0; margin-top: 2px;
    background: var(--accent-muted);
  }
  .section-header-text h3 {
    margin: 0 0 3px; font-size: 15px; font-weight: 700; color: var(--text-primary);
  }
  .section-header-text p { margin: 0; font-size: 12px; color: var(--text-secondary); }

  .period-card {
    position: relative;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md); padding: 16px 18px; margin-bottom: 10px;
    border-left: 3px solid transparent;
    transition: border-color 0.2s ease;
  }
  .period-card-header {
    display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap;
    padding-right: 90px; /* место под period-badge в углу */
  }
  .period-badge {
    position: absolute; top: 14px; right: 16px;
    font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 20px;
  }
  .period-subtitle { font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; }
  .period-planet-subtitle { font-size: 12.5px; font-weight: 600; line-height: 1.5; margin-bottom: 10px; }

  .period-notes { margin: 0 0 10px; padding: 0; list-style: none; }
  .period-notes li { font-size: 11.5px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 2px; }

  .period-group { margin-bottom: 10px; }
  .period-group:last-child { margin-bottom: 0; }
  .period-group-heading { font-size: 12.5px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px; }

  .period-items { margin: 0; padding: 0; list-style: none; }
  .period-items li {
    display: flex; align-items: flex-start; gap: 8px;
    margin-bottom: 6px; font-size: 13px; color: var(--text-primary); line-height: 1.5;
  }
  .period-items li .dot {
    margin-top: 5px; width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
  }

  @media (prefers-reduced-motion: reduce) {
    .period-card { transition: none; }
  }
  .lt-warning { font-size: 11px; color: var(--color-warning); margin-bottom: 8px; }

  .locked-box {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: 40px 24px; text-align: center;
  }
  .locked-box .lock-icon { font-size: 38px; margin-bottom: 14px; }
  .locked-box h3 { margin: 0 0 8px; font-size: 16px; font-weight: 700; color: var(--text-primary); }
  .locked-box p { font-size: 13px; color: var(--text-secondary); margin: 0 0 20px; }
  .upgrade-btn {
    padding: 11px 28px; border-radius: var(--radius-md); border: none;
    background: var(--accent); color: #fff; font-size: 14px; font-weight: 700;
    cursor: pointer; font-family: var(--font-body);
    transition: background-color 0.15s;
  }
  .upgrade-btn:hover { background: var(--accent-glow); }

  .free-hint {
    display: flex; align-items: center; gap: 16px;
    background: var(--accent-muted);
    border: 1px solid var(--border);
    border-radius: var(--radius-md); padding: 12px 14px;
    font-size: 13.5px; margin-bottom: 16px; line-height: 1.5;
  }
  .free-hint-lines { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
  .free-hint-open, .free-hint-locked { display: flex; align-items: center; gap: 8px; }
  .free-hint-open { color: var(--text-primary); }
  .free-hint-open svg { width: 20px; flex-shrink: 0; }
  .free-hint-locked { color: var(--accent); }
  .free-hint-locked .lk { flex-shrink: 0; }
  .free-hint .free-hint-btn {
    flex-shrink: 0; padding: 7px 16px; font-size: 13px; font-weight: 600; cursor: pointer;
    color: var(--accent); background: var(--bg-card);
    border: 1px solid var(--accent); border-radius: var(--radius-sm);
  }
  @media (max-width: 640px) {
    .free-hint { flex-direction: column; align-items: flex-start; gap: 10px; }
  }
  .locked-teaser { position: relative; margin-top: 4px; }
  .locked-teaser .decoy {
    filter: blur(6px); opacity: 0.5; user-select: none; pointer-events: none;
  }
  .locked-teaser .decoy li { color: var(--text-secondary); }
  .locked-trigger {
    margin-top: 8px; font-size: 12.5px; color: var(--accent); line-height: 1.5;
    display: flex; gap: 6px; align-items: center;
  }
  .locked-trigger .lk { flex-shrink: 0; }
  .locked-open {
    background: none; border: none; padding: 0; font: inherit; font-weight: 600;
    color: var(--accent); text-decoration: underline; cursor: pointer;
  }

  .error-box {
    background: var(--bg-card); border: 1px solid var(--color-danger);
    border-radius: var(--radius-md); padding: 18px; color: var(--color-danger); font-size: 14px;
  }
  .retry-btn {
    margin-top: 10px; background: var(--color-danger); color: #fff; border: none;
    border-radius: var(--radius-sm); padding: 7px 16px; font-size: 13px; cursor: pointer;
    font-family: var(--font-body); font-weight: 600;
  }

  .loading-box {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; min-height: 280px; gap: 14px;
  }
  .loading-spinner {
    width: 36px; height: 36px;
    border: 3px solid var(--border); border-top-color: var(--accent);
    border-radius: 50%; animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-text { font-size: 14px; color: var(--text-secondary); }

  .refresh-footer {
    margin-top: 28px; padding-top: 16px;
    border-top: 1px solid var(--border);
    display: flex; flex-direction: column; gap: 10px;
  }
  .refresh-btn {
    width: 100%; padding: 11px; background: var(--accent); border: none;
    border-radius: var(--radius-md); color: #fff; font-size: 14px; font-weight: 700;
    cursor: pointer; font-family: var(--font-body);
    transition: background-color 0.15s;
  }
  .refresh-btn:hover { background: var(--accent-glow); }

  .gcal-btn {
    width: 100%; padding: 11px; background: var(--bg-card);
    border: 1.5px solid var(--border); border-radius: var(--radius-md);
    color: var(--accent); font-size: 14px; font-weight: 700;
    cursor: pointer; font-family: var(--font-body);
    transition: border-color 0.15s, background-color 0.15s;
  }
  .gcal-btn:hover:not(:disabled) { background: var(--accent-muted); border-color: var(--accent-glow); }
  .gcal-btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .gcal-btn.success { background: rgba(5,150,105,0.08); border-color: var(--color-success); color: var(--color-success); }
  .gcal-btn.error   { background: rgba(220,38,38,0.08); border-color: var(--color-danger); color: var(--color-danger); }

  /* ── Ближайшие 30 дней: рельс ── */
  .tl-section { margin-bottom: 24px; }
  .tl-card {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: var(--radius-xl); padding: 20px 20px 12px;
  }
  .tl-title { margin: 0 0 4px; font-size: 15px; font-weight: 700; color: var(--text-primary); }
  /* Прокрутка внутри блока, полоса видна — на телефоне рельс шире экрана.
     Отступы по краям — внутри самого рельса (left: calc(30px + …)), а не
     padding контейнера прокрутки: правый padding в ширину прокрутки не
     входит, и крайний узел обрезался (приёмка 29.09.2026). */
  .tl-scroll { position: relative; overflow-x: auto; overflow-y: hidden; padding: 8px 0 10px; scrollbar-width: thin; }
  .tl-rail { position: relative; height: 96px; }
  .tl-scroll-wrap { position: relative; }
  .tl-scroll-wrap::after {
    content: ""; position: absolute; top: 0; right: 0; bottom: 0; width: 40px; pointer-events: none;
    background: linear-gradient(90deg, transparent, var(--bg-card)); opacity: 0; transition: opacity 0.2s;
  }
  .tl-scroll-wrap.more::after { opacity: 1; }
  .tl-line {
    position: absolute; left: 0; right: 0; top: 50px; height: 2px;
    background: linear-gradient(90deg, transparent, var(--border), transparent);
  }
  .tl-node {
    position: absolute; top: 0; transform: translateX(-50%);
    display: flex; flex-direction: column; align-items: center; width: 56px;
    background: none; border: none; padding: 0 0 6px; font: inherit; cursor: pointer;
    border-radius: var(--radius-lg); transition: background 0.15s ease;
  }
  .tl-node:hover, .tl-node:focus-visible, .tl-node[aria-expanded="true"] { background: var(--accent-muted); }
  .tl-dot {
    position: absolute; top: 47px; left: 50%; transform: translateX(-50%);
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--accent); opacity: 0.4; pointer-events: none;
  }
  .tl-date { height: 40px; display: flex; align-items: center; font-size: 13px; font-weight: 700; color: var(--text-primary); white-space: nowrap; }
  .tl-ico { position: relative; margin-top: 22px; display: inline-flex; padding: 4px; }
  .tl-count {
    position: absolute; top: -2px; right: -8px;
    min-width: 15px; height: 15px; padding: 0 3px; box-sizing: border-box;
    border-radius: var(--radius-sm); background: var(--accent); color: #fff;
    font-size: 9px; font-weight: 700; line-height: 1;
    display: flex; align-items: center; justify-content: center;
    border: 1.5px solid var(--bg-card);
  }
  .tl-pop {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: var(--radius-md); padding: 10px 12px; box-shadow: var(--shadow-raised);
    display: flex; flex-direction: column; gap: 10px;
  }
  .tl-pop-item { display: flex; gap: 8px; align-items: flex-start; }
  button.tl-pop-item {
    background: none; border: none; padding: 0; font: inherit; color: inherit;
    text-align: left; cursor: pointer;
  }
  button.tl-pop-item:hover .tl-pop-short, button.tl-pop-item:focus-visible .tl-pop-short { color: var(--accent); }
  .tl-pop-short { font-size: 12.5px; font-weight: 700; color: var(--text-primary); line-height: 1.35; }
  .tl-pop-detail { font-size: 12px; color: var(--text-secondary); line-height: 1.45; margin-top: 2px; }
`;

// ── Вспомогательные компоненты ────────────────────────────────────────────────

// Рельс «Ближайших 30 дней»: цифры дат сверху, точки на линии, значки
// снизу. По нажатию — подпись «26 окт · Полнолуние» и пояснение; несколько
// событий в один день — все в одной подписи. Подпись — fixed и прижата к
// краям окна: внутри блока с прокруткой она бы обрезалась.
// Событие с планетой в подписи — кнопка: ведёт к карточке планеты ниже
// (onPlanet, выбор вкладки — planetCardTarget).
const RAIL_NODE_PX = 56;   // физический зазор между соседними узлами
function Upcoming({ events, onPlanet }) {
  const [open, setOpen] = useState(null);   // { date, cx, top, bottom }
  const popRef = useRef(null);
  const scrollRef = useRef(null);
  // Затухание у правого края, пока рельс прокручивается дальше.
  const [more, setMore] = useState(false);
  const checkMore = () => {
    const el = scrollRef.current;
    setMore(!!el && el.scrollLeft + el.clientWidth < el.scrollWidth - 2);
  };
  useEffect(() => {
    checkMore();
    window.addEventListener("resize", checkMore);
    return () => window.removeEventListener("resize", checkMore);
  }, [events]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (popRef.current?.contains(e.target) || e.target.closest?.(".tl-node")) return;
      setOpen(null);
    };
    const onKey = (e) => { if (e.key === "Escape") setOpen(null); };
    const close = () => setOpen(null);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  const groups = [];
  for (const ev of events) {
    const last = groups[groups.length - 1];
    if (last && last.date === ev.date) last.evs.push(ev);
    else groups.push({ date: ev.date, evs: [ev] });
  }
  const { pos, gap } = railPositions(groups.map((g) => g.date));
  // Ширина под зазор RAIL_NODE_PX: уже экрана — прокрутка, а не слипание.
  const minWidth = Math.ceil(RAIL_NODE_PX / gap) + 60;

  const toggle = (g, el) => {
    if (open?.date === g.date) { setOpen(null); return; }
    const r = el.getBoundingClientRect();
    // Границы подписи — край блока (решение владельца 29.09.2026), а не окна.
    const card = el.closest(".tl-card")?.getBoundingClientRect();
    setOpen({ date: g.date, cx: r.left + r.width / 2, top: r.bottom, bottom: r.top,
      minX: Math.max(8, card ? card.left : 8),
      maxX: Math.min(window.innerWidth - 8, card ? card.right : window.innerWidth - 8),
      below: window.innerHeight - r.bottom > 200 });
  };
  const openGroup = open && groups.find((g) => g.date === open.date);
  let popStyle = null;
  if (openGroup) {
    const W = Math.min(260, open.maxX - open.minX);
    const left = Math.max(open.minX, Math.min(open.cx - W / 2, open.maxX - W));
    popStyle = { position: "fixed", left, width: W, zIndex: 100,
      ...(open.below ? { top: open.top + 6 } : { bottom: window.innerHeight - open.bottom + 6 }) };
  }

  return (
    <>
      <div className={`tl-scroll-wrap${more ? " more" : ""}`}>
      <div className="tl-scroll" ref={scrollRef} onScroll={() => { checkMore(); setOpen(null); }}>
        <div className="tl-rail" style={{ minWidth }}>
          <div className="tl-line" />
          {groups.map((g, gi) => (
            <button type="button" key={g.date} className="tl-node"
              style={{ left: `calc(30px + (100% - 60px) * ${pos[gi]})` }}
              aria-expanded={open?.date === g.date}
              aria-label={g.evs.map((e) => `${shortDate(e.date)} · ${e.short}`).join("; ")}
              onClick={(e) => toggle(g, e.currentTarget)}>
              <span className="tl-dot" />
              {/* У первой даты каждого месяца — месяц: «30 сен», «3 окт». */}
              <span className="tl-date">
                {gi === 0 || groups[gi - 1].date.slice(5, 7) !== g.date.slice(5, 7)
                  ? shortDate(g.date) : Number(g.date.slice(8, 10))}
              </span>
              <span className="tl-ico">
                <PlanetDot {...g.evs[0].dot} />
                {g.evs.length > 1 && <span className="tl-count">{g.evs.length}</span>}
              </span>
            </button>
          ))}
        </div>
      </div>
      </div>
      {openGroup && (
        <div className="tl-pop" ref={popRef} style={popStyle}>
          {openGroup.evs.map((ev) => {
            const body = (
              <>
                <PlanetDot {...ev.dot} size={16} />
                <div>
                  <div className="tl-pop-short">{shortDate(ev.date)} · {ev.short}</div>
                  <div className="tl-pop-detail">{ev.detail}</div>
                </div>
              </>
            );
            // Фазы и затмения планеты не несут — вести некуда, остаются текстом.
            return ev.planet ? (
              <button type="button" key={ev.id} className="tl-pop-item"
                onClick={() => { setOpen(null); onPlanet(ev.planet); }}>
                {body}
              </button>
            ) : (
              <div key={ev.id} className="tl-pop-item">{body}</div>
            );
          })}
        </div>
      )}
    </>
  );
}

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

function SectionHeader({ planet, emoji, title, subtitle }) {
  return (
    <div className="section-header">
      <div className="section-icon">
        {planet ? <PlanetDot type={planet} size={22} /> : emoji}
      </div>
      <div className="section-header-text">
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </div>
    </div>
  );
}

// #1 — секция месяца, всегда развёрнута (единообразно с "Неделя"/"Долгосрочно")
function MonthSection({ section, onUpgrade }) {
  return (
    <div id={`plan-sec-${section.planet}`} style={{ marginBottom: 28, scrollMarginTop: 80 }}>
      <SectionHeader
        planet={section.planet}
        emoji={section.emoji}
        title={section.planet_name}
        subtitle={section.planet_subtitle}
      />
      {(section.periods || []).map((p, pi) => (
        <PeriodBlock key={pi} planet={section.planet}
          badgeText={`Период ${p.period}`}
          house={p.house}
          theme={p.theme} subtitle={p.subtitle} notes={p.notes} groups={p.groups || []}
          locked={p.locked}
          lock={PLANET_GEN[section.planet] && lockShort("planner_period", "free", `Период ${PLANET_GEN[section.planet]}`)}
          onUpgrade={onUpgrade} />
      ))}
    </div>
  );
}

// E1 — блюр-тизер для заблокированных блоков Free (текст не приходит с бэка)
// Родительный падеж для «Период Меркурия — на Веге». Ключи — planet_key
// сервера (house_passages.py).
const PLANET_GEN = {
  sun: "Солнца", mercury: "Меркурия", venus: "Венеры", mars: "Марса", jupiter: "Юпитера",
  saturn: "Сатурна", uranus: "Урана", neptune: "Нептуна", pluto: "Плутона",
};

// Замок — как у закрытой планеты в полосе приложения (FeedPlanetStrip):
// пунктирное кольцо в цвете планеты и контурный замок внутри, не эмодзи
// (решение владельца 29.09.2026).
function LockMark({ color }) {
  return (
    <span className="lk" aria-hidden="true" style={{
      width: 20, height: 20, borderRadius: "50%", border: `1.5px dashed ${color}`,
      display: "inline-flex", alignItems: "center", justifyContent: "center",
    }}>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)"
        strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
        <rect x="5" y="11" width="14" height="10" rx="2" />
        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      </svg>
    </span>
  );
}

function LockedTeaser({ trigger, onUpgrade, color }) {
  return (
    <div className="locked-teaser">
      <ul className="period-items decoy" aria-hidden="true">
        <li><span className="dot" style={{ background: "var(--border)" }} />Тема этого периода</li>
        <li><span className="dot" style={{ background: "var(--border)" }} />Ключевые действия окна</li>
        <li><span className="dot" style={{ background: "var(--border)" }} />Рекомендации по сферам</li>
      </ul>
      {trigger && (
        <div className="locked-trigger">
          <LockMark color={color} />
          <span>{trigger}{onUpgrade && <> · <button type="button" className="locked-open" onClick={onUpgrade}>Открыть доступ</button></>}</span>
        </div>
      )}
    </div>
  );
}

// Плашка над страницей: строка «Открыто: …» обычным текстом со значком,
// под ней закрытое — цветом акцента с тем же пунктирным замком, что у
// карточек. Кнопка справа на десктопе, под строками на телефоне
// (.free-hint в styles). Тексты — lockBanner из каталога.
function LockedGroupHint({ banner, onUpgrade }) {
  if (!banner) return null;
  return (
    <div className="free-hint">
      <div className="free-hint-lines">
        <div className="free-hint-open">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)"
            strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M20 6 9 17l-5-5" />
          </svg>
          <span>{banner.open}</span>
        </div>
        <div className="free-hint-locked">
          <LockMark color="var(--accent)" />
          <span>{banner.locked}</span>
        </div>
      </div>
      <MotionButton level="secondary" className="free-hint-btn" onClick={onUpgrade}>
        Открыть доступ
      </MotionButton>
    </div>
  );
}

// Единая карточка периода — используется в разделах "Месяц", "Неделя" и "Долгосрочно",
// чтобы визуально не отличались (заголовок-бейдж + theme → subtitle → notes → группы).

// «5 дом: творчество, любовь, радость, дети» (решение владельца 29.09.2026).
// Тема в данных начинается с заглавной — после двоеточия её опускаем здесь,
// а не в methodology.json: там же её берут лента и промпт планера.
function themeWithHouse(house, theme) {
  if (!theme || !house || theme.includes(`${house} доме`)) return theme;
  return `${house} дом: ${theme.charAt(0).toLowerCase()}${theme.slice(1)}`;
}

function PeriodBlock({ planet, badgeText, house, theme, subtitle, notes, groups, warning, locked, lock, onUpgrade }) {
  const color = PLANET_COLORS[planet] || "var(--text-secondary)";
  return (
    <div className="period-card" style={{ borderLeftColor: color }}>
      {warning && <div className="lt-warning">⚠️ {warning}</div>}
      <div className="period-card-header">
        <PlanetDot type={planet} size={20} />
        {/* Текст плашки — --text-primary, цвет планеты — только фон и рамка.
            Цветной текст на своей же подложке не проходил WCAG AA у 7 планет
            из 10 (Солнце на белом — 1,3:1); так ≥ 9,6:1 в обеих темах. */}
        <span className="period-badge" style={{ color: "var(--text-primary)", background: `${color}26`, boxShadow: `inset 0 0 0 1px ${color}66` }}>
          {datesInWords(badgeText)}
        </span>
      </div>
      {theme && <div className="period-subtitle">{themeWithHouse(house, theme)}</div>}
      {subtitle && <div className="period-planet-subtitle" style={{ color }}>{subtitle}</div>}
      {locked ? (
        <LockedTeaser trigger={lock} onUpgrade={onUpgrade} color={color} />
      ) : (
        <>
          {notes && notes.length > 0 && (
            <ul className="period-notes">
              {notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          )}
          {(groups || []).map((g, gi) => (
            <div className="period-group" key={gi}>
              {g.heading && <div className="period-group-heading">{g.heading}</div>}
              <ul className="period-items">
                {g.items.map((item, i) => {
                  const colonIdx = item.indexOf(':');
                  return (
                    <li key={i}>
                      <span className="dot" style={{ background: color }} />
                      <span>
                        {colonIdx === -1 ? item : (
                          <>
                            <strong>{item.slice(0, colonIdx + 1)}</strong>
                            {item.slice(colonIdx + 1)}
                          </>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="loading-box">
      <div className="loading-spinner" />
      <div className="loading-text">Составляем твой план…</div>
    </div>
  );
}

// ── Главный компонент ─────────────────────────────────────────────────────────

export default function PlannerPage() {
  const toast = useToast();
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Слой 3: пуш привёл сюда с темой для разговора — переводим сразу в чат
  // на странице карты, где Aristea встретит пользователя первой репликой.
  useEffect(() => {
    const topic = searchParams.get('astrea');
    if (topic) {
      navigate(`/chart/${id}?astrea=${encodeURIComponent(topic)}`, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const userRaw = localStorage.getItem("astro_user");
  const userTier = (() => {
    try { return JSON.parse(userRaw)?.tier || "free"; } catch { return "free"; }
  })();
  const isFree = userTier === "free" || !userRaw;

  const [tab, setTab]               = useState("month");
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [planData, setPlanData]     = useState(null);
  const [lunar, setLunar]           = useState([]);
  const [monthOffset, setMonthOffset] = useState(0);
  // null = «неделя с сегодняшним днём» — бэкенд сам её находит (только имеет
  // смысл на текущем месяце). При явном клике по стрелке храним индекс недели
  // от начала отображаемого месяца (см. week_nav в ответе бэкенда).
  const [weekOffset, setWeekOffset]           = useState(null);
  // Что человек пытался открыть — пункт каталога витрины (planner_period,
  // planner_moon, planner_longterm, gcal_all): с него начинается окно
  // предложения; offerState — что случилось (отказ сервера по экспорту).
  const [offerFeature, setOfferFeature]       = useState(null);
  const [offerState, setOfferState]           = useState(null);
  const [checkoutLoading, setCheckoutLoading] = useState(false);

  function openPaywall(feature, state = null) {
    setOfferFeature(feature);
    setOfferState(state);
  }

  // Смена месяца — сбрасываем неделю в одном рендере, а не отдельным эффектом,
  // иначе loadPlan успел бы дёрнуться дважды (сначала со старым weekOffset).
  function changeMonth(newOffset) {
    setMonthOffset(newOffset);
    setWeekOffset(newOffset === 0 ? null : 0);
  }

  const weekNav = planData?.week_nav || null;
  const currentWeekOffset = weekOffset ?? weekNav?.week_offset ?? 0;

  // ⚠️ Строка `if (isFree) { openPaywall(); return; }` снята 16.09.2026.
  // Она запрещала бесплатному пользователю листать недели ВООБЩЕ — а по новому
  // правилу (is_moon_week_locked, backend) завершившиеся проходы Луны открыты
  // всем тарифам, и без листания free до них не добраться: то, что ему уже
  // отдаёт сервер, было бы недостижимо с экрана.
  //
  // Тариф решает не «листать или нет», а что внутри недели ЗАКРЫТО, и решает
  // это сервер. Клиентский запрет был вторым гейтом поверх серверного — ровно
  // та конструкция, которая в этом проекте расходится молча.
  function changeWeek(delta) {
    if (!weekNav) return;
    const next = currentWeekOffset + delta;
    if (next < 0 || next > weekNav.total_weeks - 1) return;
    setWeekOffset(next);
  }

  // Апселл на тариф — цель (Вега/Лира) не зависит от того, какой конкретно
  // гейт вызвал модалку: какую модалку показать решает ТЕКУЩИЙ тариф юзера
  // (Free → сравнение Вега/Лира, Вега → апселл на Лиру), см. рендер модалок ниже.
  async function handleCheckout(tier, promoCode = null) {
    if (checkoutLoading) return;
    setCheckoutLoading(true);
    try {
      // checkout_url, не url — контракт держит api/checkoutContract.test.js.
      const { checkout_url: checkoutUrl } = await createCheckoutSession(tier, "monthly", id, promoCode);
      if (!checkoutUrl) {
        toast.error("Платёжный сервис не вернул ссылку на оплату. Попробуй чуть позже.");
        setCheckoutLoading(false);
        return;
      }
      window.location.href = checkoutUrl;
    } catch (e) {
      toast.error(apiErrorText(e, "Не удалось открыть страницу оплаты. Попробуй чуть позже."));
      setCheckoutLoading(false);
    }
  }


  const { exportEvents, status: gcalStatus } = useGcalExport();

  // E1: Free тоже грузит план — витрина с блюром (текущий период Солнца открыт)
  useEffect(() => { loadLunar(); }, []);
  useEffect(() => { loadPlan(); }, [id, monthOffset, weekOffset]);

  // Фазы и затмения для «Ближайших 30 дней» — этот и следующий месяц от
  // сегодня, от листания месяцев не зависят.
  async function loadLunar() {
    const d = new Date();
    const months = [0, 1].map((k) => new Date(d.getFullYear(), d.getMonth() + k, 1));
    const res = await Promise.all(months.map(async (m) => {
      try {
        const r = await fetch(`${API_BASE}/api/v1/calendar/lunar?year=${m.getFullYear()}&month=${m.getMonth() + 1}`);
        return r.ok ? await r.json() : null;
      } catch { return null; }
    }));
    setLunar(res.filter(Boolean));
  }

  const upcoming = useMemo(() => buildUpcoming(planData, lunar), [planData, lunar]);

  // Из подписи «Ближайших 30 дней» — к карточке планеты. Вкладку переключаем,
  // только если карточки нет на текущей. Таймаут — дождаться рендера новой
  // вкладки: до него элемента с этим id в DOM ещё нет.
  function goToPlanet(planet) {
    const target = planetCardTarget(planData, planet, tab);
    if (!target) return;
    setTab(target.tab);
    setTimeout(() => {
      document.getElementById(target.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
  }

  async function loadPlan() {
    setLoading(true); setError(null); setPlanData(null);
    try {
      const params = new URLSearchParams();
      if (monthOffset !== 0) params.set('month_offset', monthOffset);
      if (weekOffset !== null) params.set('week_offset', weekOffset);
      // Пояс браузера: «сегодня» и время проходов — по нему, не по месту рождения.
      if (deviceTimeZone()) params.set('tz', deviceTimeZone());
      const qs = params.toString();
      const url = `${API_BASE}/api/v1/chart/${id}/planner/monthly${qs ? `?${qs}` : ''}`;
      const res = await authFetch(url);
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `Ошибка ${res.status}`); }
      const data = await res.json();
      setPlanData(data.planner);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  // Собираем события из planData для экспорта — короткие: планета + тема + период,
  // без вывала всего списка пунктов в описание.
  function buildExportEvents() {
    if (!planData) return [];
    const result = [];
    const d = new Date(); d.setMonth(d.getMonth() + monthOffset);
    const yr = d.getFullYear();

    (planData.month_sections || []).forEach(section => {
      (section.periods || []).forEach(p => {
        const match = p.period?.match(/(\d{2})\.(\d{2})/);
        if (match) {
          const title = p.theme ? `${section.planet_name} — ${p.theme}` : section.planet_name;
          result.push({
            summary:     `${section.emoji} ${title} (${p.period})`,
            description: "",
            date:        `${yr}-${match[2]}-${match[1]}`,
            colorId:     "1",
            // type в Google Calendar не уходит — он только для журнала
            // экспорта (см. _logExport ниже).
            type:        "planet_period",
          });
        }
      });
    });

    (planData.week_days || []).forEach(day => {
      const match = day.date?.match(/(\d{2})\.(\d{2})/);
      if (match) {
        result.push({
          summary:     `🌙 ${day.theme || `Луна в ${day.house} доме`}`,
          description: "",
          date:        `${yr}-${match[2]}-${match[1]}`,
          colorId:     "5",
          type:        "moon_day",
        });
      }
    });

    return result;
  }

  const tabs = [
    { key: "month",    label: "Месяц"       },
    { key: "week",     label: "Неделя"      },
    { key: "longterm", label: "Долгосрочно" },
  ];

  const monthLabel = (() => {
    const d = new Date(); d.setMonth(d.getMonth() + monthOffset);
    // «Март 2027»: без «г.», который добавляет toLocaleString с year, и с
    // заглавной (решение владельца 29.09.2026).
    if (monthOffset === 0) return "Этот месяц";
    const m = d.toLocaleString("ru-RU", { month: "long" });
    return `${m.charAt(0).toUpperCase()}${m.slice(1)} ${d.getFullYear()}`;
  })();

  const gcalLabel = {
    idle:    "📅 Экспортировать события в Google Календарь",
    loading: "⏳ Экспортируем…",
    success: "✅ Добавлено в Google Календарь",
    error:   "❌ Ошибка — попробуй снова",
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
              {/* Листать — в пределах горизонта тарифа (plannerMonthsAhead, на
                  сервере — planner_offset_window). За горизонтом — стрелка с
                  замком и окно предложения; у Лиры и Ориона стрелки нет — Орион
                  на вебе не продаётся, дальше предложить нечего. Назад — как раньше, только платным. */}
              <div className="month-nav">
                {!isFree && (
                  <MotionButton level="secondary" className="month-nav-btn" onClick={() => changeMonth(monthOffset - 1)}>‹</MotionButton>
                )}
                <span className="month-nav-label">{monthLabel}</span>
                {monthOffset < plannerMonthsAhead(isFree ? "free" : userTier) ? (
                  <MotionButton level="secondary" className="month-nav-btn" onClick={() => changeMonth(monthOffset + 1)}>›</MotionButton>
                ) : offerFor("planner_horizon", isFree ? "free" : userTier, { sellable: ["lite", "pro"] }) && (
                  <MotionButton level="secondary" className="month-nav-btn month-nav-locked"
                    aria-label={lockText("planner_horizon", isFree ? "free" : userTier)}
                    onClick={() => openPaywall("planner_horizon")}>
                    <LockMark color="var(--text-secondary)" />
                  </MotionButton>
                )}
              </div>
            </div>
            <div className="planner-subtitle">Персональный астрологический план</div>
          </div>

          {(isFree || userTier === "lite") && (
            <LockedGroupHint
              banner={lockBanner(isFree ? "planner_period" : "planner_longterm", isFree ? "free" : "lite")}
              onUpgrade={() => openPaywall(isFree ? "planner_period" : "planner_longterm")} />
          )}

          {(loading ? (
            <LoadingState />
          ) : error ? (
            <div className="error-box">
              <div>⚠️ {error}</div>
              <MotionButton level="primary" className="retry-btn" onClick={loadPlan}>Повторить</MotionButton>
            </div>
          ) : (
            <>
              {monthOffset === 0 && upcoming.length >= 2 && (
                <section className="tl-section">
                  <div className="tl-card">
                    <h2 className="tl-title">Ближайшие 30 дней</h2>
                    <Upcoming events={upcoming} onPlanet={goToPlanet} />
                  </div>
                </section>
              )}

              <TabBar tabs={tabs} active={tab} onChange={setTab} />

              {tab === "month" && (planData?.month_sections || []).map((section, si) => (
                <MonthSection key={si} section={section} onUpgrade={() => openPaywall("planner_period")} />
              ))}

              {tab === "week" && (
                <div>
                  <div className="week-header-row">
                    <SectionHeader planet="moon" emoji="🌙" title={planData?.week_title || "Транзитная Луна по домам"} subtitle="Лучшие дни недели для каждой темы" />
                    {weekNav && (
                      <div className="month-nav">
                        <MotionButton
                          level="secondary" className="month-nav-btn"
                          disabled={currentWeekOffset <= 0}
                          onClick={() => changeWeek(-1)}
                        >‹</MotionButton>
                        <span className="month-nav-label">{formatWeekRange(weekNav.week_start, weekNav.week_end)}</span>
                        <MotionButton
                          level="secondary" className="month-nav-btn"
                          disabled={currentWeekOffset >= weekNav.total_weeks - 1}
                          onClick={() => changeWeek(1)}
                        >›</MotionButton>
                      </div>
                    )}
                  </div>
                  {(planData?.week_days || []).map((day, i) => (
                    // Замок — у каждой закрытой карточки, как у периодов
                    // (решение владельца 29.09.2026), и только на free: у
                    // платных закрытые недели тоже приходят, но Вега им
                    // ничего не откроет — продавать её значило бы продавать
                    // то, что уже есть.
                    <PeriodBlock key={i} planet="moon"
                      badgeText={day.time ? `${day.date} – ${day.time}` : day.date}
                      house={day.house}
                      theme={day.locked ? "" : (day.theme || `Луна в ${day.house} доме`)}
                      groups={day.groups || []}
                      locked={day.locked}
                      lock={isFree && lockShort("planner_moon", "free", `Луна в ${day.house} доме`)}
                      onUpgrade={() => openPaywall("planner_moon")} />
                  ))}
                </div>
              )}

              {tab === "longterm" && (
                <div>
                  <SectionHeader emoji="🪐" title={planData?.longterm_title || "Долгосрочные транзиты"} subtitle="Социальные и высшие планеты — тренды на годы" />
                  {(planData?.longterm || []).map((lt, i) => (
                    <div key={i} id={`plan-lt-${lt.planet}`} style={{ marginBottom: 20, scrollMarginTop: 80 }}>
                      <SectionHeader planet={lt.planet}
                        title={`${lt.planet_name} в ${lt.house} Доме`}
                        subtitle={lt.planet_subtitle} />
                      <PeriodBlock planet={lt.planet}
                        badgeText={lt.period}
                        house={lt.house}
                        theme={lt.theme} subtitle={lt.subtitle} notes={lt.notes} groups={lt.groups || []}
                        warning={lt.warning}
                        locked={lt.locked}
                        lock={PLANET_GEN[lt.planet] && lockShort("planner_longterm", userTier, `Период ${PLANET_GEN[lt.planet]}`)}
                        onUpgrade={() => openPaywall("planner_longterm")} />
                    </div>
                  ))}
                </div>
              )}

              <div className="refresh-footer">
                <MotionButton
                  level="secondary"
                  className={`gcal-btn${!isFree && gcalStatus === "success" ? " success" : ""}${!isFree && gcalStatus === "error" ? " error" : ""}`}
                  disabled={isFree || gcalStatus === "loading"}
                  onClick={async () => {
                    if (isFree) return;
                    const res = await exportEvents(buildExportEvents(), id);
                    if (res?.blocked) openPaywall("gcal_all", res.blocked);
                  }}
                  title={isFree ? `Экспорт событий в Google Календарь — на тарифе ${TIER_NAMES.lite} и выше` : undefined}
                >
                  {isFree ? `Экспорт событий в Google Календарь — на тарифе ${TIER_NAMES.lite} и выше` : gcalLabel}
                </MotionButton>
              </div>
            </>
          ))}

        </div>
      </div>

      <TierOfferModal
        open={!!offerFeature}
        onClose={() => setOfferFeature(null)}
        feature={offerFeature}
        tier={userTier || "free"}
        state={offerState}
        onChoose={(t) => handleCheckout(t)}
        busy={checkoutLoading}
      />
    </>
  );
}
