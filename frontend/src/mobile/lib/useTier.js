/**
 * useTier.js — тариф для экрана: значение и признак того, что оно ЗНАЧИМО.
 *
 * Отдельный файл, а не функция внутри tierSource.js, по той же причине, по
 * которой в проекте вынесены refreshSchedule.js и interpretRules.js: хук без
 * DOM-окружения не проверить, и всё решающее должно жить вне него. Здесь
 * остался только React-обвес; правило «что показывать» — `upsellForTier` в
 * `interpretRules.js`, оно и покрыто тестами.
 *
 * ⚠️ `known: false` — не «тариф free», а «мы ещё не знаем». Разница
 * принципиальная: `interpretationUpsell(undefined)` отдаёт ветку free, и
 * именно так платящий получал предложение купить то, что у него есть.
 * Показывать приписку на незнании нельзя — лучше не показать вовсе.
 */

import { useEffect, useState } from 'react';

import { getSubscription, onSubscription, peekSubscription } from './tierSource';

export default function useTier() {
  const [sub, setSub] = useState(() => peekSubscription());

  useEffect(() => {
    const off = onSubscription(setSub);
    // Запрос дедуплицируется в tierSource: сколько бы экранов ни
    // смонтировалось разом, уйдёт один. Ошибку глотаем — `known` останется
    // false, и приписки просто не будет.
    getSubscription().catch(() => {});
    return off;
  }, []);

  return { tier: sub?.tier ?? null, known: Boolean(sub?.tier) };
}
