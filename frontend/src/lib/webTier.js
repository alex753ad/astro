/**
 * webTier.js — живой тариф для веба.
 *
 * Привязка общей машинерии (`lib/subscriptionSource.js`) к тому, как ходит
 * веб: `getSubscription(token)` из `api/client.js`. В приложении такая же
 * привязка живёт в `mobile/lib/tierSource.js` — отличается только этой
 * строкой.
 *
 * ⚠️ Зачем это вебу. `user.tier` из `useAuth` обновляется вместе с токеном,
 * то есть до 15 минут показывает старое значение. Через `userTier` он уходит
 * не только в приписку под разбором, но и в `TransitTimeline` — а там от него
 * зависит ВИТРИНА: горизонт транзитов и то, какие события считаются
 * доступными. Человек, оплативший Лиру, до четверти часа видел горизонт
 * бесплатного тарифа.
 *
 * ⚠️ Отличие от приложения, сделанное намеренно: пока живой тариф не приехал,
 * веб откатывается на сохранённый (`fallbackTier`), а не показывает пустоту.
 * В приложении на незнании приписки просто нет — там это дёшево. На вебе
 * тем же правилом пришлось бы либо мигать заглушкой кабинета астролога
 * (`CRMPage` целиком за гейтом `tier !== 'premium'`), либо на долю секунды
 * прятать витрину транзитов. Мигание интерфейса — плата хуже, чем доля
 * секунды старого значения: окно устаревания и так сжимается с 15 минут до
 * времени одного запроса.
 */

import { useEffect, useState } from 'react';

import { getSubscription as fetchSubscription } from '../api/client';
import { createSubscriptionSource } from './subscriptionSource';

const source = createSubscriptionSource(
  () => fetchSubscription(localStorage.getItem('astro_access_token')),
);

export const {
  getSubscription,
  onSubscription,
  peekSubscription,
  resetSubscription,
} = source;

/**
 * Живой тариф с откатом на сохранённый.
 *
 * @param {string|null|undefined} fallbackTier — `user.tier` из useAuth
 * @returns {{tier: string, known: boolean}} `known` — тариф подтверждён
 *          сервером в этой сессии, а не взят из хранилища.
 */
export function useWebTier(fallbackTier) {
  const [sub, setSub] = useState(() => peekSubscription());

  useEffect(() => {
    const off = onSubscription(setSub);
    // Запрос дедуплицируется: сколько бы страниц ни спросило разом, уйдёт
    // один. Ошибку глотаем — останется откат на сохранённый тариф.
    getSubscription().catch(() => {});
    return off;
  }, []);

  const live = sub?.tier || null;
  return {
    tier: live || fallbackTier || 'free',
    known: Boolean(live),
  };
}
