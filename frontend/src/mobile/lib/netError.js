/**
 * netError.js — какой это сбой и что сказать человеку.
 *
 * До 24.09.2026 экраны показывали `err.message` как есть, и без сети это
 * было «Failed to fetch» — по-английски, от браузера. Теперь у сетевых
 * ошибок есть `kind`, и текст отвечает на два вопроса: что случилось и что
 * делать.
 *
 *   offline — запрос не ушёл (самолёт, нет покрытия, белые списки с
 *             мгновенным отказом);
 *   timeout — ушёл и не вернулся за отведённое время;
 *   server  — сервер ответил 5xx.
 *
 * ⚠️ Ни offline, ни timeout не поломка — в Sentry они не уходят
 * (`isNetworkNoise`, фильтр в main.mobile.jsx).
 */

export const NET_TEXT = {
  offline: 'Нет сети. Покажем, когда появится.',
  timeout: 'Сервер долго не отвечает. Попробуем ещё раз сами — или нажми «Повторить».',
  server: 'На сервере сбой. Попробуй через пару минут.',
};

/**
 * То же для ДЕЙСТВИЙ (вход, сохранение, удаление): «покажем, когда
 * появится» тут неправда — само ничего не повторится. ⚠️ У таймаута записи
 * исход неизвестен: запрос мог дойти, поэтому «проверь», а не «не сохранено».
 */
export const NET_WRITE_TEXT = {
  offline: 'Нет сети — ничего не отправлено. Подключись и попробуй ещё раз.',
  timeout: 'Сервер долго не отвечает. Проверь, сохранилось ли, и попробуй ещё раз.',
  server: 'На сервере сбой. Попробуй через пару минут.',
};

export class NetError extends Error {
  constructor(kind, status, { write = false } = {}) {
    const texts = write ? NET_WRITE_TEXT : NET_TEXT;
    super(texts[kind] || texts.offline);
    this.name = 'NetError';
    this.kind = kind;
    if (status) this.status = status;
  }
}

/**
 * `fetch` без связи отклоняется TypeError'ом: «Failed to fetch» в Chromium
 * (Android WebView), «Load failed» в Safari, «NetworkError…» в Firefox.
 */
export function isFetchFailure(err) {
  // ⚠️ Только TypeError С ТАКИМ текстом: «Cannot read properties of
  // undefined» — тоже TypeError, и это настоящая поломка, её глушить нельзя.
  return (err instanceof TypeError || err?.name === 'TypeError')
    && /failed to fetch|load failed|networkerror|network request failed/i.test(String(err?.message || ''));
}

export function netKind(err) {
  if (err?.kind === 'offline' || err?.kind === 'timeout' || err?.kind === 'server') return err.kind;
  if (isFetchFailure(err)) return 'offline';
  return null;
}

/** Нет связи или таймаут — показывать сохранённое, а не ошибку. */
export function isConnectivity(err) {
  const k = netKind(err);
  return k === 'offline' || k === 'timeout';
}

/** Текст для экрана: сетевой — свой, иначе сообщение ошибки или запасной. */
export function errorText(err, fallback, { write = false } = {}) {
  const k = netKind(err);
  if (k) return err?.kind === k && err.message ? err.message : (write ? NET_WRITE_TEXT : NET_TEXT)[k];
  return err?.message || fallback;
}

/**
 * Строка ошибки, уже ставшая текстом (useAuth кладёт в `error` сообщение
 * исключения как есть): браузерное «Failed to fetch» — в человеческое.
 * Для входа и регистрации, которые ходят мимо authFetchWithTimeout.
 */
export function humanizeErrorText(text) {
  return isFetchFailure({ name: 'TypeError', message: text }) ? NET_WRITE_TEXT.offline : text;
}

/** Для Sentry: offline и timeout — шум, а не поломка. */
export function isNetworkNoise(event, hint) {
  const err = hint?.originalException;
  if (err && isConnectivity(err)) return true;
  const values = event?.exception?.values || [];
  return values.some((v) => (
    v?.type === 'NetError' && /^(Нет сети|Сервер долго)/.test(String(v?.value || ''))
  ) || (v?.type === 'TypeError' && isFetchFailure({ name: 'TypeError', message: v?.value })));
}
