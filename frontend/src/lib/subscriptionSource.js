/**
 * subscriptionSource.js — общая машинерия «один живой источник тарифа».
 *
 * Заведена 09.09.2026, когда та же проблема нашлась на вебе, что и в
 * приложении. Тариф в `useAuth` обновляется только вместе с токеном, то есть
 * до 15 минут показывает старое значение. В приложении из-за этого платящему
 * предлагали купить то, что у него есть; на вебе через `userTier` устаревает
 * ещё и витрина транзитов (`TransitTimeline`) — то есть человек видит чужой
 * горизонт, а не только лишнюю приписку.
 *
 * ⚠️ Здесь именно ФАБРИКА, а не готовый модуль, и причина техническая: веб и
 * приложение ходят на `/profile/subscription` по-разному. Приложение — через
 * `authFetchWithTimeout` (свой предел ожидания, mobile/lib), веб — через
 * `request()` с токеном из localStorage. Общее у них — всё остальное:
 * дедупликация, кэш, подписка, сброс. Копировать это дважды значило бы
 * получить два источника истины про один и тот же тариф — ровно то, от чего
 * файл и заведён.
 *
 * ⚠️ Новых запросов на каждое открытие экрана нет и быть не должно. В
 * приложении `TabShell` монтирует три экрана разом, и залп уже был причиной
 * гейта по сроку токена (CLAUDE.md, «Холодный старт упирается в ЗАДЕРЖИВАЮЩИЙ
 * лимит»). Поэтому запрос дедуплицируется: сколько бы потребителей ни
 * смонтировалось одновременно, уходит один.
 *
 * ⚠️ Кэш живёт ТОЛЬКО в памяти. Записанный на диск, он пережил бы перезапуск
 * и снова стал бы устаревшим — тем самым, от чего избавляемся. Отсутствие
 * ответа честнее старого ответа.
 */

/**
 * @param {() => Promise<object>} fetcher — как ЭТА платформа спрашивает
 *        `/profile/subscription`. Должен бросать при неуспехе.
 * @returns {{getSubscription, onSubscription, peekSubscription, resetSubscription}}
 */
export function createSubscriptionSource(fetcher) {
  let cached = null;      // последний успешный ответ
  let inFlight = null;    // промис незавершённого запроса — для дедупликации
  const listeners = new Set();

  const publish = () => { for (const fn of listeners) fn(cached); };

  /**
   * Подписка. Возвращает функцию отписки.
   * Готовый ответ отдаётся сразу — иначе потребитель, смонтированный после
   * завершения запроса, ждал бы следующего обновления вечно.
   */
  function onSubscription(fn) {
    listeners.add(fn);
    if (cached) fn(cached);
    return () => listeners.delete(fn);
  }

  /**
   * @param {{force?: boolean}} [opts] — `force` игнорирует кэш (жест
   *        обновления: человек тянет экран именно чтобы увидеть новое).
   */
  function getSubscription({ force = false } = {}) {
    if (!force && cached) return Promise.resolve(cached);
    if (inFlight) return inFlight;

    inFlight = Promise.resolve()
      .then(fetcher)
      .then((data) => { cached = data; publish(); return data; })
      .finally(() => { inFlight = null; });

    return inFlight;
  }

  /** Последний известный ответ или null. Синхронно, без запроса. */
  const peekSubscription = () => cached;

  /** Забыть всё — при выходе из аккаунта: тариф чужой. */
  function resetSubscription() {
    cached = null;
    inFlight = null;
    publish();
  }

  return { getSubscription, onSubscription, peekSubscription, resetSubscription };
}
