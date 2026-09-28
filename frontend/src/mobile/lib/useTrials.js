/**
 * useTrials.js — остатки пробных и месячных: разборы транзитов и сообщения
 * чата (решение владельца 28.09.2026). Источник — тот же общий
 * /profile/subscription (tierSource.js), поле `trials`.
 *
 * `null` в поле — лимита нет (или тариф неизвестен). После выданного разбора
 * или ответа зовите `refreshTrials()` — сервер уже списал, число на экране
 * должно это показать.
 */

import { useEffect, useState } from 'react';
import { getSubscription, onSubscription, peekSubscription } from './tierSource';

const EMPTY = { transitLeft: null, chatLeft: null, chatPeriod: null, known: false };

export function trialsFrom(sub) {
  if (!sub) return EMPTY;
  const t = sub.trials || {};
  return {
    transitLeft: t.transit_trials_left ?? null,
    chatLeft: t.chat_left ?? null,
    chatPeriod: t.chat_period ?? null,
    known: true,
  };
}

export function refreshTrials() {
  return getSubscription({ force: true }).catch(() => {});
}

export default function useTrials() {
  const [trials, setTrials] = useState(() => trialsFrom(peekSubscription()));
  useEffect(() => {
    const off = onSubscription((data) => setTrials(trialsFrom(data)));
    getSubscription().catch(() => {});
    return off;
  }, []);
  return trials;
}

/** «Осталось 2 бесплатных разбора» — со склонением. */
export function leftLabel(n, [one, few, many]) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  const word = mod10 === 1 && mod100 !== 11 ? one
    : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? few : many;
  const verb = mod10 === 1 && mod100 !== 11 ? 'Остался' : 'Осталось';
  return `${verb} ${n} ${word}`;
}
