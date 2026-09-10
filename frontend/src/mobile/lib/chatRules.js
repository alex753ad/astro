/**
 * chatRules.js — чем кончился запрос в чат, что показать и куда прокручивать.
 *
 * Чистые функции: DOM-окружения для тестов в проекте нет, и всё решающее
 * обязано жить вне компонента. Тот же приём, что в `interpretRules.js` и
 * `transitInterpretRules.js` рядом.
 *
 * ⚠️ Отказы у чата приходят ДВУМЯ разными путями, и путать их нельзя:
 *
 *   · ДО начала потока — HTTP-статусом: 403 (тариф), 429 (20 запросов в час),
 *     503 (дневной бюджет AI исчерпан), 404 (карта не найдена или чужая),
 *     400 (пустой вопрос). Эти отказы приходят обычным телом, поток не
 *     начинается вовсе;
 *   · ПОСЛЕ начала — кадром внутри потока: `{"error": <код>, "text": <текст>}`,
 *     за которым всё равно идёт `[DONE]`. Кодов три: `timeout`,
 *     `empty_response`, `stream_failed`.
 *
 * ⚠️ **403 здесь — единственный отказ, текст которого приходится писать на
 * клиенте, и это не отступление от правила «тексты берём с сервера».**
 * `require_tier` отдаёт `detail` ОБЪЕКТОМ (`{error, required, current}`), то
 * есть человеческого текста в ответе нет вовсе — в отличие от разбора
 * транзита, где 403 приходит законченной фразой и показывается дословно.
 * Тарифных ЧИСЕЛ в этом тексте нет намеренно: сетка живёт на сервере, и
 * копировать сюда «2490 ₽» значило бы завести второй источник цены.
 */

/** Что показать, когда сервер не сказал ничего: оборвалась связь. */
export const CHAT_BROKEN_TEXT =
  'Ответ не дошёл. Проверьте связь и попробуйте ещё раз.';

/**
 * Отказ по тарифу. Текст свой — см. предупреждение в шапке.
 * Названия тарифов, а не цены: цену человек увидит на странице тарифов.
 */
export const CHAT_TIER_TEXT =
  'Чат с Аристеей открыт на Лире и Орионе. Там можно спрашивать про свою карту словами.';

export const CHAT_OUTCOMES = Object.freeze({
  TIER: 'tier',
  RATE_LIMIT: 'rate_limit',
  BUDGET: 'budget',
  NO_CHART: 'no_chart',
  BAD_QUESTION: 'bad_question',
  BROKEN: 'broken',
});

/**
 * Коды ошибок, приходящие КАДРОМ внутри потока (`rag_router.py`).
 *
 * Все три означают одно и то же для человека — ответ не сложился, — но
 * повторять имеет смысл везде: ни один из них не про тариф и не про квоту.
 *
 * ⚠️ Расход при этом УЖЕ списан, в отличие от разбора транзита. У чата
 * `increment_monthly_usage` и часовой лимит тратятся ДО потока (так сделано
 * намеренно: ответ уезжает потоком, и после его начала записать расход уже
 * некуда). Значит повтор стоит человеку ещё одной попытки из двадцати в час —
 * поэтому предлагаем повтор, но не делаем его автоматически.
 */
export const CHAT_STREAM_ERROR_CODES = Object.freeze([
  'timeout',
  'empty_response',
  'stream_failed',
]);

/**
 * Классифицирует неуспех.
 *
 * @param {{status?: number, detail?: string}} signal
 *        `status` — HTTP-код (undefined, если отказ пришёл кадром внутри
 *        потока или запрос вообще не доехал);
 *        `detail` — текст сервера либо, для потоковых ошибок, машинный код.
 * @returns {{outcome: string, text: string, showPricing: boolean, canRetry: boolean}}
 */
export function classifyChatError(signal) {
  const status = signal?.status;
  const detail = typeof signal?.detail === 'string' ? signal.detail.trim() : '';

  if (status === 403) {
    return {
      outcome: CHAT_OUTCOMES.TIER,
      // detail здесь объект — до строки не доходит, текст всегда свой.
      text: CHAT_TIER_TEXT,
      showPricing: true,
      canRetry: false,
    };
  }

  if (status === 429) {
    // 20 запросов в час на аккаунт. Текст сервера законченный — показываем
    // дословно; своей копии числа в клиенте нет.
    return {
      outcome: CHAT_OUTCOMES.RATE_LIMIT,
      text: detail || 'Слишком много вопросов подряд. Попробуйте через час.',
      showPricing: false,
      canRetry: false,
    };
  }

  if (status === 503) {
    // Дневной бюджет AI исчерпан — общий с разборами карт. Не тариф: платить
    // человеку не за что, предлагать покупку в этот момент нельзя.
    return {
      outcome: CHAT_OUTCOMES.BUDGET,
      text: detail || 'Аристея сегодня уже отвечать не может. Попробуйте завтра.',
      showPricing: false,
      canRetry: false,
    };
  }

  if (status === 404) {
    return {
      outcome: CHAT_OUTCOMES.NO_CHART,
      // Текст сервера содержит внутренний идентификатор («Chart not found:
      // 3f2a…-uuid») — тот же случай, что в fetchFeed и fetchChart, и та же
      // подмена. Показывать человеку uuid нельзя.
      text: 'Карта не найдена. Возможно, она удалена.',
      showPricing: false,
      canRetry: false,
    };
  }

  if (status === 400) {
    return {
      outcome: CHAT_OUTCOMES.BAD_QUESTION,
      text: detail || 'Вопрос пустой — напишите, что хотите спросить.',
      showPricing: false,
      canRetry: false,
    };
  }

  // Всё остальное — транспорт и потоковые ошибки: обрыв, таймаут, 5xx,
  // `empty_response`. Кнопки тарифов нет: у человека проблема со связью или с
  // моделью, а не с подпиской.
  return {
    outcome: CHAT_OUTCOMES.BROKEN,
    text: CHAT_BROKEN_TEXT,
    showPricing: false,
    canRetry: true,
  };
}

/**
 * Прилипать ли к низу при дописывании текста.
 *
 * ⚠️ Прокрутка «всегда вниз» (`scrollIntoView` на каждое изменение, как в
 * вебовском `RagChat.jsx`) на телефоне не годится по двум независимым
 * причинам:
 *
 *   1. она дерётся с пальцем: человек отлистал вверх перечитать начало ответа,
 *      а его каждым чанком возвращает вниз;
 *   2. высоты меняются ПОСЛЕ прокрутки — локальный Inter догружается и
 *      подменяет запасной шрифт (тот же капкан, что у якоря ленты, CLAUDE.md
 *      «Прокрутка к якорю сбивается подменой шрифта»).
 *
 * Поэтому решение принимается по расстоянию до низа, а касание отменяет
 * прилипание до конца ответа — ровно как повторная прокрутка ленты отменяется
 * первым касанием.
 *
 * @param {{distanceFromBottom: number, userScrolledAway: boolean}} state
 */
export const STICK_THRESHOLD_PX = 48;

export function shouldStickToBottom({ distanceFromBottom, userScrolledAway }) {
  if (userScrolledAway) return false;
  return Number(distanceFromBottom) <= STICK_THRESHOLD_PX;
}

/**
 * Отпустил ли человек низ списка (значит, прилипание отключаем).
 *
 * Отдельная функция, а не сравнение на месте: порог один на оба решения, и
 * разъехаться им нельзя — иначе появится зона, где мы и не прилипаем, и не
 * считаем, что человек ушёл.
 */
export function hasScrolledAway({ distanceFromBottom }) {
  return Number(distanceFromBottom) > STICK_THRESHOLD_PX;
}

/**
 * Что делать с незаконченным ответом при возврате из фона.
 *
 * ⚠️ Поток НЕ перезапрашиваем (решение владельца), и это отличие от натального
 * разбора, где `shouldRefetchOnResume` перезапускает поток. Там разбор
 * идемпотентен и лежит в кэше; здесь повтор — это новый вызов модели, ещё одна
 * попытка из двадцати в час и ВТОРАЯ пара «вопрос-ответ» в серверной истории.
 * Человек увидел бы свой вопрос дважды.
 *
 * Вместо этого честно говорим, что ответ не дошёл, и оставляем повтор ему.
 *
 * @param {{visible: boolean, streaming: boolean}} state
 * @returns {boolean} показать ли «ответ не дошёл»
 */
export function shouldReportInterrupted({ visible, streaming }) {
  return Boolean(visible) && Boolean(streaming);
}
