/**
 * transitInterpretRules.js — чем кончился разбор транзита и что показать.
 *
 * Чистые функции: DOM-окружения для тестов в проекте нет, и всё решающее
 * обязано жить вне компонента. Тот же приём, что в interpretRules.js рядом.
 *
 * ⚠️ Здесь классификация по HTTP-СТАТУСУ, а в натальном разборе
 * (`interpretRules.js`) — по событию внутри потока. Это не непоследовательность,
 * а разные ручки:
 *
 *   · натальный разбор читается через `EventSource`, который не даёт JS ни
 *     кода ответа, ни тела. Поэтому сервер шлёт отказ ПЕРВЫМ СОБЫТИЕМ потока,
 *     а не статусом (`backend/main.py`, ветка `limit_error`);
 *   · разбор транзита — `POST /chart/{id}/transits/event/interpret`, и
 *     `EventSource` к нему непригоден в принципе: он умеет только GET.
 *     Читается обычным `fetch`, у которого код и тело доступны, поэтому
 *     отказы остались настоящими статусами — 403 и 429.
 *
 * **Ветка «error первым событием» здесь мёртвая.** Скопировать сюда
 * `classifyOutcome` из натального было бы худшим решением, чем написать своё:
 * оно бы молча не сработало.
 *
 * ⚠️ Тарифных чисел и таблиц доступа в клиенте нет и быть не должно. Тексты
 * 403 и 429 приходят с сервера готовыми (`rate_limits.py`, `main.py`) — в них
 * уже названы и тариф, и число. Показываем их дословно.
 */

import { interpretationUpsell } from '../../lib/interpretationUpsell';

/** Что показать, когда сервер не сказал ничего: оборвалась связь. */
export const TRANSIT_BROKEN_TEXT =
  'Не удалось получить разбор. Проверьте связь и попробуйте снова.';

/** Запасной текст для отказа аутентификации — на случай пустого тела. */
export const TRANSIT_ANON_TEXT = 'Войдите в аккаунт, чтобы получить разбор транзита.';

export const TRANSIT_OUTCOMES = Object.freeze({
  DONE: 'done',
  NOT_SIGNIFICANT: 'not_significant',
  ANON: 'anon',
  RATE_LIMIT: 'rate_limit',
  BROKEN: 'broken',
});

/**
 * Классифицирует неуспех запроса разбора транзита.
 *
 * @param {{status?: number, detail?: string, authenticated?: boolean}} signal
 *        `status` — HTTP-код (undefined, если запрос вообще не доехал);
 *        `detail` — текст сервера;
 *        `authenticated` — есть ли сессия. По нему и только по нему
 *        различаются два 403.
 * @returns {{outcome: string, text: string, showPricing: boolean, canRetry: boolean}}
 *
 * ⚠️ Два 403 различаются НЕ по тексту. У сервера их два разных: «на бесплатном
 * тарифе открыт разбор 2 самых значимых транзитов» и «войдите в аккаунт».
 * Сравнивать их содержимое значило бы привязать клиент к формулировке, которую
 * правят в маркетинговых целях, — и тихо сломаться при первой же правке.
 * Признак берётся оттуда, где он достоверен: есть сессия или нет.
 *
 * ⚠️ Расход при неуспехе НЕ списан ни в одном из случаев. `commit_transit_ai`
 * (`rate_limits.py`) вызывается только после полностью выданного текста, а 403
 * и 429 поднимаются до генерации. Поэтому повтор безопасен везде, где он
 * вообще имеет смысл, — а смысл он имеет только при обрыве: отказ по тарифу
 * повторится тем же отказом.
 */
export function classifyTransitError(signal) {
  const status = signal?.status;
  const detail = typeof signal?.detail === 'string' ? signal.detail.trim() : '';

  if (status === 403 && !signal?.authenticated) {
    return {
      outcome: TRANSIT_OUTCOMES.ANON,
      text: detail || TRANSIT_ANON_TEXT,
      showPricing: false,
      canRetry: false,
    };
  }

  if (status === 403) {
    // Free попросил разбор незначимого транзита. Текст сервера законченный:
    // в нём сказано, сколько разборов открыто и что делать дальше.
    return {
      outcome: TRANSIT_OUTCOMES.NOT_SIGNIFICANT,
      text: detail || 'Разбор этого транзита доступен на старшем тарифе.',
      showPricing: true,
      canRetry: false,
    };
  }

  if (status === 429) {
    // Вега исчерпала месячную квоту. Число в тексте — серверное; своей копии
    // квоты в клиенте нет, и заранее мы не предупреждаем (решение владельца).
    return {
      outcome: TRANSIT_OUTCOMES.RATE_LIMIT,
      text: detail || 'Лимит разборов транзитов на этот месяц исчерпан.',
      showPricing: true,
      canRetry: false,
    };
  }

  // Всё остальное — транспорт: обрыв, таймаут, 5xx, ошибка внутри потока.
  // Кнопки тарифов здесь нет: у человека проблема со связью, а не с
  // подпиской, и предлагать ему покупку в этот момент бессмысленно.
  return {
    outcome: TRANSIT_OUTCOMES.BROKEN,
    text: TRANSIT_BROKEN_TEXT,
    showPricing: false,
    canRetry: true,
  };
}

/**
 * Приписка про старший тариф под готовым разбором транзита.
 *
 * Правило то же, что у натального (`upsellForTier`, interpretRules.js), и по
 * той же причине: тариф из общего источника, а на незнании ничего не
 * показываем — «тариф ещё не приехал» и «тариф бесплатный» разные вещи.
 *
 * @param {{tier: string|null, known: boolean, finished: boolean, failed: boolean}} state
 */
export function transitUpsellFor({ tier, known, finished, failed }) {
  if (!finished || failed) return null;
  if (!known || !tier) return null;
  return interpretationUpsell(tier);
}
