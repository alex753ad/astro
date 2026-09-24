/**
 * offlineCache.js — последнее загруженное, чтобы приложение было полезным
 * без сети (решение владельца 24.09.2026).
 *
 * Почему Capacitor Preferences, а не localStorage и не файлы:
 *   · localStorage WebView система вправе вычистить при нехватке места, и
 *     его читает любой JS в webview — тот же довод, что в authTransport.js;
 *   · файлы — это `@capacitor/filesystem`, новый нативный плагин, то есть
 *     отдельное решение владельца. Preferences уже стоит.
 * ⚠️ Цена Preferences: на Android это SharedPreferences, файл целиком живёт в
 * памяти и переписывается на каждой записи. Поэтому сюда кладётся ОБРЕЗАННАЯ
 * лента (`trimFeed`), а не всё окно в 365 дней.
 *
 * ⚠️ Версия формата — в КЛЮЧЕ. Поднял `CACHE_VERSION` — записи прежней
 * версии не читаются и стираются при первом обращении. Нечитаемая запись
 * (битый JSON, чужой владелец) выбрасывается молча: кэш — удобство, падать
 * из-за него экран не должен.
 *
 * ⚠️ Каждая запись помечена владельцем (`sub` access-токена) и показывается
 * только ему. Плюс при потере сессии стирается всё (MobileApp.jsx,
 * RequireAuth) — телефон бывает общим.
 *
 * ⚠️ Объект плагина не возвращается и не await-ится — только обёртка
 * `{ plugin }` (CLAUDE.md, «Объект плагина Capacitor нельзя возвращать из
 * async-функции»). Тест подделывает плагин thenable-Proxy'ем, как настоящий.
 */

import { IS_MOBILE } from '../../api/authTransport';
import { tokenSubject } from '../../lib/jwt';
import { shiftDays } from './feedTime';

const PREFIX = 'aristea_offline:';
export const CACHE_VERSION = 1;
const KEY_PREFIX = `${PREFIX}v${CACHE_VERSION}:`;

export function createOfflineCache({ storage, owner, now = () => Date.now() }) {
  let swept = null;

  // ⚠️ Отдаёт ОБЁРТКУ `{ plugin }`, а не плагин: `return s.plugin` из
  // async-функции повесил бы вызов навсегда — ровно это и поймал тест при
  // первом прогоне 24.09.2026.
  async function wrapped() {
    return (await storage()) || null;
  }

  // Записи других версий — один раз за процесс, до первого чтения.
  function sweepOldVersions() {
    if (!swept) {
      swept = (async () => {
        try {
          const w = await wrapped();
          const p = w && w.plugin;
          if (!p) return;
          const { keys } = await p.keys();
          for (const k of keys || []) {
            if (k.startsWith(PREFIX) && !k.startsWith(KEY_PREFIX)) await p.remove({ key: k });
          }
        } catch { /* кэш — удобство */ }
      })();
    }
    return swept;
  }

  async function read(name) {
    try {
      await sweepOldVersions();
      const w = await wrapped();
      const p = w && w.plugin;
      if (!p) return null;
      const { value } = await p.get({ key: KEY_PREFIX + name });
      if (!value) return null;
      let entry;
      try { entry = JSON.parse(value); } catch { entry = null; }
      const me = owner();
      if (!entry || typeof entry !== 'object' || !me || entry.owner !== me || !('data' in entry)) {
        await p.remove({ key: KEY_PREFIX + name });
        return null;
      }
      return { data: entry.data, savedAt: entry.savedAt };
    } catch {
      return null;
    }
  }

  async function write(name, data) {
    try {
      const me = owner();
      const w = await wrapped();
      const p = w && w.plugin;
      if (!p || !me) return;
      await p.set({ key: KEY_PREFIX + name, value: JSON.stringify({ owner: me, savedAt: now(), data }) });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[offline] запись в кэш не удалась:', name, err);
    }
  }

  async function remove(name) {
    try {
      const w = await wrapped();
      const p = w && w.plugin;
      if (p) await p.remove({ key: KEY_PREFIX + name });
    } catch { /* кэш — удобство */ }
  }

  /** Имена своей версии, начинающиеся с `start`. */
  async function names(start = '') {
    try {
      const w = await wrapped();
      const p = w && w.plugin;
      if (!p) return [];
      const { keys } = await p.keys();
      return (keys || []).filter((k) => k.startsWith(KEY_PREFIX + start)).map((k) => k.slice(KEY_PREFIX.length));
    } catch {
      return [];
    }
  }

  /** Всё, всех версий. При потере сессии. */
  async function clearAll() {
    try {
      const w = await wrapped();
      const p = w && w.plugin;
      if (!p) return;
      const { keys } = await p.keys();
      for (const k of keys || []) if (k.startsWith(PREFIX)) await p.remove({ key: k });
    } catch { /* кэш — удобство */ }
  }

  return { read, write, remove, names, clearAll };
}

async function preferences() {
  if (!IS_MOBILE) return null;
  const mod = await import('@capacitor/preferences');
  return { plugin: mod.Preferences };
}

function currentOwner() {
  try {
    return tokenSubject(localStorage.getItem('astro_access_token'));
  } catch {
    return null;
  }
}

export const offlineCache = createOfflineCache({ storage: preferences, owner: currentOwner });

// ── Что и как кладём ────────────────────────────────────────────────────

export const FEED_PAST_DAYS = 7;
export const FEED_AHEAD_DAYS = 30;

/**
 * Лента на ближайшие дни — для кэша.
 *
 * Событие остаётся, если хоть как-то задевает окно: период Сатурна,
 * начавшийся полгода назад, нужен полосе «сейчас».
 *
 * ⚠️ `horizon` сужается до окна, а `next_tier` выбрасывается. Иначе
 * карточка «Дальше — до …, открывается на Лире» стояла бы через месяц
 * после сегодняшнего дня и врала бы о том, где кончается лента, — и
 * заодно продавала бы тариф человеку, чей тариф без сети неизвестен.
 */
export function trimFeed(feed, today) {
  if (!feed || typeof feed !== 'object') return feed;
  const from = shiftDays(today, -FEED_PAST_DAYS);
  const to = shiftDays(today, FEED_AHEAD_DAYS);
  const events = (feed.events || []).filter((e) => {
    const start = String(e?.at || '').slice(0, 10);
    const end = String(e?.ends_at || e?.at || '').slice(0, 10);
    return start && start <= to && end >= from;
  });
  const h = feed.horizon || {};
  const { next_tier: _drop, ...rest } = h;
  const horizon = {
    ...rest,
    from: h.from && h.from > from ? h.from : from,
    to: h.to && h.to < to ? h.to : to,
  };
  return { ...feed, events, horizon };
}

/**
 * Список карт. Основная сменилась — сохранённый разбор прежней стирается
 * (решение владельца 24.09.2026: разбор хранится только основной карты).
 */
export async function rememberCharts(data, primaryId, cache = offlineCache) {
  await cache.write('charts', data);
  const interp = await cache.read('interp');
  if (interp && interp.data?.chartId !== primaryId) await cache.remove('interp');
}

/** Разбор — только если это основная карта по последнему списку. */
export async function rememberInterpretation(chartId, sections, cache = offlineCache) {
  const charts = await cache.read('charts');
  const primary = charts?.data?.charts?.find((c) => c.is_primary) || charts?.data?.charts?.[0];
  if (!chartId || primary?.id !== chartId) return;
  await cache.write('interp', { chartId, sections });
}

export async function cachedInterpretation(chartId, cache = offlineCache) {
  const hit = await cache.read('interp');
  return hit?.data?.chartId === chartId ? hit.data.sections : null;
}

/**
 * Прогнозы — по записи на ключ, чтобы две карточки, сохраняющие разом, не
 * затирали друг друга. Старые чистятся на записи: дневные раньше вчера,
 * лунные старше 40 дней.
 */
export function dayForecastKey(chartId, date) {
  return `forecast:day:${date}:${chartId}`;
}

export function lunationForecastKey(chartId, phase, date) {
  return `forecast:lunation:${date}:${phase}:${chartId}`;
}

export function staleForecastNames(names, today) {
  const dayEdge = shiftDays(today, -1);
  const lunEdge = shiftDays(today, -40);
  return names.filter((n) => {
    const [, kind, date] = n.split(':');
    if (kind === 'day') return date < dayEdge;
    if (kind === 'lunation') return date < lunEdge;
    return false;
  });
}

export async function rememberForecast(name, data, today) {
  await offlineCache.write(name, data);
  for (const old of staleForecastNames(await offlineCache.names('forecast:'), today)) {
    await offlineCache.remove(old);
  }
}
