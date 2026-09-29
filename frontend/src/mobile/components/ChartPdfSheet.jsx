/**
 * ChartPdfSheet.jsx — лист «PDF-отчёты» на экране «Карта» (29.09.2026).
 *
 * Как на вебе (components/PdfReports.jsx): «Собрать PDF» ставит сборку на
 * сервере, пока она идёт — «Готовим PDF, это займёт пару минут» с прогрессом;
 * готовые — списком с датой, тарифом, «Открыть» (системная читалка) и значком
 * «Поделиться»; «Файл хранится 30 дней». Готовая сборка только встаёт в
 * список — лист «Поделиться» сам не открывается (решение владельца 29.09.2026).
 * Закрыл лист — сборка не прерывается: отчёт будет в списке с отметкой
 * «Новый» (и пуш «PDF готов», если уведомления включены).
 *
 * Тарифного гейта здесь нет: лимит и его текст — check_pdf_limit на сервере.
 */

import React, { useCallback, useEffect, useState } from 'react';
import SupportLink from './SupportLink';
import { ACTIVE, FAIL_TEXT, OPEN_FAIL, errorText, listPdf, openPdf, pdfStatus, sharePdf, startPdf } from '../lib/pdfApi';

const POLL_MS = 2000;

const BTN = {
  width: '100%', height: 46, borderRadius: 'var(--radius-md)', border: 'none',
  background: 'var(--accent)', color: 'var(--accent-on)',
  fontFamily: 'var(--font-body)', fontSize: 15, fontWeight: 600,
};

function dayWords(iso) {
  if (!iso) return '';
  const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
}

export default function ChartPdfSheet({ chart, wheelPng, onClose }) {
  const [reports, setReports] = useState([]);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      const list = await listPdf(chart.id);
      setReports(list.filter((r) => r.status === 'ready'));
      setJob((j) => j || list.find((r) => ACTIVE.includes(r.status)) || null);
    } catch { /* список не главное — кнопка работает и без него */ }
  }, [chart.id]);

  useEffect(() => { refresh(); }, [refresh]);

  async function handOff(fn, r) {
    setError('');
    try {
      if (await fn(r.id, chart.name)) refresh();   // false — уже идёт, молчим
    } catch {
      setError(OPEN_FAIL);
    }
  }

  useEffect(() => {
    if (!job || !ACTIVE.includes(job.status)) return undefined;
    const t = setTimeout(async () => {
      try {
        const next = await pdfStatus(job.id);
        if (next.status === 'ready') {
          setJob(null);
          await refresh();
        } else if (next.status === 'failed') {
          setJob(null);
          setError(errorText({ message: next.error }, FAIL_TEXT));
        } else {
          setJob(next);
        }
      } catch {
        setJob({ ...job });   // сеть моргнула — спросим ещё раз
      }
    }, POLL_MS);
    return () => clearTimeout(t);
  }, [job, refresh]);

  async function start() {
    if (busy || job) return;
    setBusy(true);
    setError('');
    try {
      // Снимок не вышел (колесо не на экране) — PDF всё равно собирается,
      // с упрощённым колесом сервера.
      const png = wheelPng ? await wheelPng().catch(() => null) : null;
      const r = await startPdf(chart.id, png);
      if (r.status === 'ready') {
        await refresh();
      } else {
        setJob(r);
      }
    } catch (e) {
      setError(errorText(e, FAIL_TEXT));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="PDF-отчёты"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.45)',
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--bg-deeper)', borderTopLeftRadius: 20, borderTopRightRadius: 20,
          borderTop: '1px solid var(--border)', padding: '18px 16px calc(18px + env(safe-area-inset-bottom))',
          display: 'flex', flexDirection: 'column', gap: 12,
        }}
      >
        <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 600, color: 'var(--text-primary)' }}>
          PDF-отчёты
        </p>

        {job ? (
          <div aria-live="polite">
            <p style={{ margin: '0 0 8px', fontSize: 14, color: 'var(--text-primary)' }}>Готовим PDF, это займёт пару минут</p>
            <div role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100}
              style={{ height: 6, borderRadius: 3, background: 'var(--accent-muted)', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${Math.max(6, job.progress || 0)}%`, background: 'var(--accent)', transition: 'width 0.6s ease' }} />
            </div>
            {job.step && <p style={{ margin: '6px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>{job.step}</p>}
          </div>
        ) : (
          <button type="button" onClick={start} disabled={busy} style={{ ...BTN, opacity: busy ? 0.7 : 1 }}>
            {busy ? 'Отправляем…' : 'Собрать PDF'}
          </button>
        )}

        {error && (
          <>
            <p role="alert" style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--color-danger)' }}>{error}</p>
            <SupportLink screen="chart-pdf" error={error} style={{ alignSelf: 'flex-start' }} />
          </>
        )}

        {reports.length > 0 && (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {reports.map((r) => (
              <li key={r.id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
                padding: '10px 14px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
              }}>
                <span style={{ fontSize: 14, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  {dayWords(r.ready_at || r.created_at)} · {r.tier_name}
                  {r.new && (
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent)', background: 'var(--accent-muted)', borderRadius: 999, padding: '2px 8px' }}>
                      Новый
                    </span>
                  )}
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 }}>
                  <button type="button" className="mobile-link" onClick={() => handOff(openPdf, r)} style={{ fontSize: 14, fontWeight: 600, padding: 0 }}>
                    Открыть
                  </button>
                  <button type="button" className="mobile-link" aria-label="Поделиться" onClick={() => handOff(sharePdf, r)}
                    style={{ padding: 0, display: 'flex' }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
                      <path d="M16 6l-4-4-4 4" />
                      <path d="M12 2v13" />
                    </svg>
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}

        <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)' }}>Файл хранится 30 дней.</p>
      </div>
    </div>
  );
}
