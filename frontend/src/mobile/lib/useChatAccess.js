/**
 * useChatAccess.js — доступен ли чат с Аристеей текущему тарифу.
 *
 * Источник — GET /profile/subscription, поле `features.rag_chat`, а не
 * локальная таблица тарифов: какие именно тарифы дают чат, решает сервер
 * (тот же принцип, что для блока тарифа на «Ещё» — не заводить свою копию
 * тарифной сетки на клиенте, SPEC_MORE_SCREEN.md §4.1).
 *
 * Пока запрос не завершился — `hasAccess: false`. Ошибка запроса — тоже
 * `false`: кнопка-заглушка на free выглядит лишней секунду, но показать
 * рабочую кнопку тому, кому чат не положен, хуже.
 */

import { useEffect, useState } from 'react';
import { getSubscription, onSubscription, peekSubscription } from './tierSource';

export default function useChatAccess() {
  const [hasAccess, setHasAccess] = useState(
    () => !!peekSubscription()?.features?.rag_chat,
  );

  useEffect(() => {
    const off = onSubscription((data) => setHasAccess(!!data?.features?.rag_chat));
    // Свой запрос отсюда убран 09.09.2026: подписка теперь общая
    // (tierSource.js), и на холодном старте уходит ОДИН запрос на всех
    // потребителей вместо прежних двух.
    getSubscription().catch(() => {}); // остаётся false — см. докстринг
    return off;
  }, []);

  return hasAccess;
}
