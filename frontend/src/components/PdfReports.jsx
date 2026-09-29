import { useCallback, useEffect, useRef, useState } from "react";
import MotionButton from "./MotionButton";
import { listPdfReports, pdfReportFile, pdfReportStatus, startPdfReport } from "../api/client";

/*
  PDF-отчёты на вебе (решение владельца 29.09.2026): сборка идёт на сервере в
  фоне, здесь — «Готовим PDF, это займёт пару минут» с прогрессом и список
  «PDF-отчёты» в карточке карты: дата, тариф, «Скачать», «Файл хранится 30
  дней». Ушёл со страницы — отчёт соберётся всё равно: при следующем заходе
  он в списке с отметкой «Новый» (и пуш «PDF готов», если включены).
*/

const POLL_MS = 2000;
const ACTIVE = ["queued", "running"];

function dayWords(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

export async function savePdf(report, name) {
  const blob = await pdfReportFile(report.id);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name ? `Натальная карта — ${name}.pdf` : "Натальная карта.pdf";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Список и идущая сборка по карте. start(wheelPng) → отчёт или бросает
 * ApiError (429 — лимит, текст с сервера).
 */
export function usePdfReports(chartId, enabled, { onReady, onFail } = {}) {
  const [reports, setReports] = useState([]);
  const [job, setJob] = useState(null);
  const handlers = useRef({ onReady, onFail });
  handlers.current = { onReady, onFail };

  const refresh = useCallback(async () => {
    if (!enabled || !chartId) return;
    try {
      const list = await listPdfReports(chartId);
      setReports(list.filter((r) => r.status === "ready"));
      setJob((j) => j || list.find((r) => ACTIVE.includes(r.status)) || null);
    } catch { /* список — не главное на странице */ }
  }, [chartId, enabled]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (!job || !ACTIVE.includes(job.status)) return undefined;
    const t = setTimeout(async () => {
      try {
        const next = await pdfReportStatus(job.id);
        if (next.status === "ready") {
          setJob(null);
          await refresh();
          handlers.current.onReady?.(next);
        } else if (next.status === "failed") {
          setJob(null);
          handlers.current.onFail?.(next.error);
        } else {
          setJob(next);
        }
      } catch {
        setJob({ ...job });   // сеть моргнула — спросим ещё раз
      }
    }, POLL_MS);
    return () => clearTimeout(t);
  }, [job, refresh]);

  const start = useCallback(async (wheelPng) => {
    const r = await startPdfReport(chartId, wheelPng);
    if (r.status === "ready") {
      await refresh();
      handlers.current.onReady?.(r);
    } else {
      setJob(r);
    }
    return r;
  }, [chartId, refresh]);

  return { reports, job, start, refresh };
}

export function PdfReportsCard({ reports, job, onDownload }) {
  if (!job && !reports.length) return null;
  return (
    <section style={st.card} aria-live="polite">
      <h2 style={st.title}>PDF-отчёты</h2>
      {job && (
        <div style={st.job}>
          <div style={st.jobText}>Готовим PDF, это займёт пару минут</div>
          <div style={st.bar} role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100}>
            <div style={{ ...st.fill, width: `${Math.max(6, job.progress || 0)}%` }} />
          </div>
          {job.step && <div style={st.step}>{job.step}</div>}
        </div>
      )}
      {reports.length > 0 && (
        <ul style={st.list}>
          {reports.map((r) => (
            <li key={r.id} style={st.row}>
              <span style={st.rowText}>
                {dayWords(r.ready_at || r.created_at)} · {r.tier_name}
                {r.new && <span style={st.badge}>Новый</span>}
              </span>
              <MotionButton level="secondary" style={st.btn} onClick={() => onDownload(r)}>Скачать</MotionButton>
            </li>
          ))}
        </ul>
      )}
      <p style={st.note}>Файл хранится 30 дней.</p>
    </section>
  );
}

const st = {
  card: {
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)",
    padding: "16px 18px", margin: "0 0 20px",
  },
  title: { margin: "0 0 10px", fontFamily: "var(--font-display)", fontSize: 17, fontWeight: 600, color: "var(--text-primary)" },
  job: { marginBottom: 12 },
  jobText: { fontSize: 14, color: "var(--text-primary)", marginBottom: 8 },
  bar: { height: 6, borderRadius: 3, background: "var(--accent-muted)", overflow: "hidden" },
  fill: { height: "100%", background: "var(--accent)", borderRadius: 3, transition: "width 0.6s ease" },
  step: { fontSize: 12, color: "var(--text-secondary)", marginTop: 6 },
  list: { listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 },
  row: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 },
  rowText: { fontSize: 14, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  badge: {
    fontSize: 11, fontWeight: 600, color: "var(--accent-fg)", background: "var(--accent-muted)",
    borderRadius: 999, padding: "2px 8px",
  },
  btn: {
    padding: "6px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer", color: "var(--accent)",
    background: "var(--bg-card)", border: "1px solid var(--accent)", borderRadius: "var(--radius-sm)",
  },
  note: { margin: "10px 0 0", fontSize: 12, color: "var(--text-secondary)" },
};
