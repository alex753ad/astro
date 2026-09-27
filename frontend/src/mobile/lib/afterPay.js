/**
 * afterPay.js — куда вернуть человека после оплаты из листа (решение
 * владельца 27.09.2026): туда, откуда он нажал, и открыть тот элемент
 * (период, транзит, чат) — если купленный тариф его открывает.
 *
 * `returnTo` кладётся к ожидающему платежу (payApi.rememberPending) —
 * приложение могло быть выгружено, пока человек платил в браузере.
 * Открытие элемента разносит шина ниже: лента открывает событие по ключу,
 * кнопка чата — чат.
 */

import { opensFeature } from '../../lib/offerRule';

/**
 * @param {{path?: string, kind?: 'event'|'chat', key?: string, feature?: string}|null} returnTo
 * @param {string} tier — купленный тариф
 * @returns {{path: string|null, open: {kind: string, key?: string}|null}}
 */
export function returnAfterPay(returnTo, tier) {
  if (!returnTo) return { path: null, open: null };
  const opens = Boolean(returnTo.kind && returnTo.feature && opensFeature(returnTo.feature, tier));
  return {
    path: returnTo.path || null,
    open: opens ? { kind: returnTo.kind, ...(returnTo.key ? { key: returnTo.key } : {}) } : null,
  };
}

const listeners = new Set();

export function emitAfterPay(open) {
  for (const fn of [...listeners]) fn(open);
}

export function onAfterPay(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Какая функция стоит за событием ленты (lib/offerRule.js). */
export function featureOfEvent(event) {
  switch (event?.kind) {
    case 'planner_longterm': return 'planner_longterm';
    case 'planner_period': return 'planner_period';
    case 'planner_moon_house': return 'planner_moon';
    case 'transit': return 'transit';
    default: return null;
  }
}
