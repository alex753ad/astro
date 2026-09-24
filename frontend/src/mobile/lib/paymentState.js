/**
 * paymentState.js — что сказать человеку про его платёж. Без React и сети.
 *
 * Ответ `GET /payments/status/{id}` (+ признак «нет сети» и число попыток) →
 * заголовок, текст и вид экрана. Правило одно для всех состояний: человек в
 * этот момент думает о деньгах, поэтому каждый текст отвечает на вопрос «а
 * деньги?» — списаны ли, пропадут ли, что будет дальше.
 *
 * Вынесено из PaySheet ради теста: экран ожидания — место, где «поддержка
 * молчит» начинается, и каждая ветка обязана быть проверена.
 */

import { TIER_NAMES } from '../../constants';

/** Сколько раз спрашиваем подряд, пока экран открыт (раз в 3 с ≈ минута). */
export const MAX_POLLS = 20;
export const POLL_MS = 3000;

function untilText(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return ` до ${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

/**
 * @param {object|null} status — ответ сервера или null (ещё не ответил)
 * @param {{offline?: boolean, polls?: number, tier?: string}} ctx
 * @returns {{kind: 'wait'|'ok'|'fail'|'later', title: string, text: string, done: boolean}}
 */
export function describePayment(status, { offline = false, polls = 0, tier } = {}) {
  const name = TIER_NAMES[status?.tier] || TIER_NAMES[tier] || '';

  if (status?.state === 'succeeded') {
    return {
      kind: 'ok', done: true,
      title: 'Оплата прошла',
      text: `Тариф ${TIER_NAMES[status.tier] || name} включён${untilText(status.active_until)}.`,
    };
  }
  if (status?.state === 'canceled') {
    return {
      kind: 'fail', done: true,
      title: 'Оплата не прошла',
      text: `${status.reason || 'Платёж отменён.'} Деньги не списаны — можно попробовать ещё раз.`,
    };
  }
  if (status?.state === 'review') {
    return {
      kind: 'later', done: true,
      title: 'Оплата получена, проверяем',
      text: 'Деньги пришли, но тариф автоматически не включился. Мы уже получили сигнал и разберёмся. '
        + 'Если хочешь ускорить — напиши в поддержку.',
    };
  }
  if (offline) {
    return {
      kind: 'later', done: false,
      title: 'Нет сети',
      text: 'Проверим оплату, когда связь вернётся. Если деньги списались, тариф включится сам — они не пропадут.',
    };
  }
  if (polls >= MAX_POLLS) {
    return {
      kind: 'later', done: true,
      title: 'Банк ещё не подтвердил оплату',
      text: 'Так бывает. Тариф включится сам, как только придёт подтверждение, — проверим ещё раз, '
        + 'когда откроешь приложение. Если деньги списались, а тарифа нет больше суток, напиши в поддержку.',
    };
  }
  return {
    kind: 'wait', done: false,
    title: 'Проверяем оплату…',
    text: status?.state === 'unknown'
      ? 'Платёжный сервис отвечает медленно. Подождём ещё немного.'
      : 'Обычно это несколько секунд. Можно не ждать: тариф включится сам.',
  };
}
