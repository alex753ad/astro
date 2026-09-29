/**
 * pdfApi.js — PDF-отчёты в приложении (решение владельца 29.09.2026).
 *
 * Сборка идёт на сервере в фоне (backend/pdf_reports): старт, опрос статуса,
 * список по карте. Файл отдаётся только с токеном, поэтому ни ссылкой, ни
 * `a.download` его не взять (в Capacitor WebView нет DownloadListener, см.
 * шапку ChartShareSheet.jsx): он читается fetch'ем, пишется в кеш
 * приложения (@capacitor/filesystem) и уходит в системный лист «Поделиться»
 * (@capacitor/share) или открывается в системной читалке
 * (@capawesome-team/capacitor-file-opener, решение владельца 29.09.2026).
 * FileProvider с cache-path в шаблоне Capacitor уже есть — оба плагина
 * отдают файл через него.
 *
 * ⚠️ Объекты плагинов не возвращаются и не await-ятся — только их методы
 * (frontend/src/mobile/CLAUDE.md, «Объект плагина Capacitor…»).
 */

import { API_BASE } from '../../config';
import { responseErrorText } from '../../api/client';
import { authFetchWithTimeout, getWithRetry } from './authFetchTimeout';

export const FAIL_TEXT = 'Не получилось собрать PDF, попробуй ещё раз';
export const OPEN_FAIL = 'Не получилось открыть файл, попробуй ещё раз';
export const ACTIVE = ['queued', 'running'];

/** Текст ошибки для экрана. Плагины и WebView отвечают по-английски
 * («Can't share while sharing is in progress») — человеку такое не
 * показывается никогда; русский текст сервера проходит как есть. */
export function errorText(e, fallback) {
  const msg = String(e?.message || '');
  return /[а-яё]/i.test(msg) ? msg : fallback;
}

async function json(resp, fallback) {
  if (!resp.ok) throw new Error(await responseErrorText(resp, fallback));
  return resp.json();
}

export async function startPdf(chartId) {
  const resp = await authFetchWithTimeout(`${API_BASE}/chart/${chartId}/pdf-reports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
  return json(resp, FAIL_TEXT);
}

export async function listPdf(chartId) {
  const data = await json(await getWithRetry(`${API_BASE}/chart/${chartId}/pdf-reports`), 'Не удалось загрузить список');
  return data.reports || [];
}

export async function pdfStatus(reportId) {
  return json(await getWithRetry(`${API_BASE}/pdf-reports/${reportId}`), FAIL_TEXT);
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(',')[1] || '');
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

export function pdfFileName(chartName) {
  const name = (chartName || '').replace(/[\\/:*?"<>|]/g, '').trim();
  return name ? `Натальная карта — ${name}.pdf` : 'Натальная карта.pdf';
}

async function cacheFile(reportId, chartName) {
  // 60 с: файл в сотни килобайт на медленной сети — не признак зависания.
  const resp = await authFetchWithTimeout(`${API_BASE}/pdf-reports/${reportId}/file`, undefined, 60000);
  if (!resp.ok) throw new Error(await responseErrorText(resp, 'Файл не найден — собери PDF заново'));
  const data = await blobToBase64(await resp.blob());
  const { Filesystem, Directory } = await import('@capacitor/filesystem');
  const { uri } = await Filesystem.writeFile({
    path: `pdf/${pdfFileName(chartName)}`, data, directory: Directory.Cache, recursive: true,
  });
  return uri;
}

// ⚠️ Один вызов за раз на всё приложение. Share.share держит промис, пока
// системный лист открыт, и второй вызов плагин отклоняет английским «Can't
// share while sharing is in progress». Повторное нажатие в это время — не
// ошибка, а ничего: возвращаем false, экран молчит.
let inFlight = false;

async function once(fn) {
  if (inFlight) return false;
  inFlight = true;
  try {
    await fn();
    return true;
  } finally {
    inFlight = false;
  }
}

/** Открыть файл отчёта в системной читалке PDF. false — уже идёт другой вызов. */
export function openPdf(reportId, chartName) {
  return once(async () => {
    const path = await cacheFile(reportId, chartName);
    const { FileOpener } = await import('@capawesome-team/capacitor-file-opener');
    await FileOpener.openFile({ path, mimeType: 'application/pdf' });
  });
}

/** Отдать файл отчёта в системный лист «Поделиться». false — уже идёт другой вызов. */
export function sharePdf(reportId, chartName) {
  return once(async () => {
    const url = await cacheFile(reportId, chartName);
    const { Share } = await import('@capacitor/share');
    try {
      await Share.share({ title: pdfFileName(chartName), url, dialogTitle: 'Сохранить или отправить PDF' });
    } catch (e) {
      // Закрыл лист, ничего не выбрав, — это не ошибка.
      if (!/cancel/i.test(String(e?.message || e))) throw e;
    }
  });
}
