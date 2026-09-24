/**
 * useChatAccess.js — доступен ли чат с Аристеей текущему тарифу.
 *
 * Источник — GET /profile/subscription, поле `features.rag_chat`, а не
 * локальная таблица тарифов: какие именно тарифы дают чат, решает сервер
 * (тот же принцип, что для блока тарифа на «Ещё» — не заводить свою копию
 * тарифной сетки на клиенте, SPEC_MORE_SCREEN.md §4.1).
 *
 * Пока запрос не завершился или он не удался — `null` (см. chatAccessFrom):
 * кнопки нет вовсе. Ни рабочей — тому, кому чат не положен, ни замка —
 * тому, кто за чат заплатил.
 */

import { useEffect, useState } from 'react';
import { getSubscription, onSubscription, peekSubscription } from './tierSource';

/**
 * `null` — тариф неизвестен (ещё грузится или нет сети). С 24.09.2026 это
 * отдельное состояние, а не `false`: `false` рисует замок и ведёт к блоку
 * тарифа, то есть без сети платящему показывали бы пейволл на то, что у
 * него есть (решение владельца: неизвестный тариф пейволла не включает).
 */
export function chatAccessFrom(sub) {
  return sub ? Boolean(sub.features?.rag_chat) : null;
}

export default function useChatAccess() {
  const [hasAccess, setHasAccess] = useState(() => chatAccessFrom(peekSubscription()));

  useEffect(() => {
    const off = onSubscription((data) => setHasAccess(chatAccessFrom(data)));
    // Свой запрос отсюда убран 09.09.2026: подписка теперь общая
    // (tierSource.js), и на холодном старте уходит ОДИН запрос на всех
    // потребителей вместо прежних двух.
    getSubscription().catch(() => {}); // остаётся false — см. докстринг
    return off;
  }, []);

  return hasAccess;
}
