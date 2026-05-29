/**
 * useStreak.js — D5
 *
 * Отслеживает дни подряд, когда пользователь открывал свою карту.
 * Хранит в localStorage:
 *   astrea_streak_dates  — массив дат ISO (YYYY-MM-DD), дедуплицированный
 *   astrea_streak_count  — текущий стрик (дней подряд)
 *   astrea_streak_last   — последняя дата визита
 */

import { useState, useEffect } from 'react';

const KEY_DATES = 'astrea_streak_dates';
const KEY_COUNT = 'astrea_streak_count';
const KEY_LAST  = 'astrea_streak_last';

function today() {
  return new Date().toISOString().slice(0, 10);
}

function yesterday() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

function calcStreak(dates) {
  if (!dates.length) return 0;
  const sorted = [...new Set(dates)].sort().reverse();
  let streak = 1;
  for (let i = 0; i < sorted.length - 1; i++) {
    const curr = new Date(sorted[i]);
    const prev = new Date(sorted[i + 1]);
    const diff = (curr - prev) / (1000 * 60 * 60 * 24);
    if (diff === 1) {
      streak++;
    } else {
      break;
    }
  }
  return streak;
}

export default function useStreak() {
  const [streak, setStreak] = useState(0);
  const [isNew,  setIsNew]  = useState(false); // true если стрик вырос сегодня

  useEffect(() => {
    const todayStr = today();
    const lastStr  = localStorage.getItem(KEY_LAST) || '';

    // Уже записывали сегодня — просто читаем
    if (lastStr === todayStr) {
      const count = parseInt(localStorage.getItem(KEY_COUNT) || '1', 10);
      setStreak(count);
      return;
    }

    // Новый день
    let dates = [];
    try { dates = JSON.parse(localStorage.getItem(KEY_DATES) || '[]'); } catch {}

    dates.push(todayStr);
    const count = calcStreak(dates);

    localStorage.setItem(KEY_DATES,  JSON.stringify(dates));
    localStorage.setItem(KEY_COUNT,  String(count));
    localStorage.setItem(KEY_LAST,   todayStr);

    setStreak(count);
    setIsNew(count > 1); // показываем анимацию если стрик растёт
  }, []);

  return { streak, isNew };
}

// ── Push-уведомление через Service Worker ─────────────────
// Планирует локальный будильник через postMessage в SW,
// если пользователь не заходил >2 дней.

export function schedulePushReminder() {
  if (!('serviceWorker' in navigator)) return;
  const lastStr = localStorage.getItem(KEY_LAST) || '';
  if (!lastStr) return;

  const last = new Date(lastStr);
  const now  = new Date();
  const daysSince = (now - last) / (1000 * 60 * 60 * 24);

  if (daysSince < 2) return; // заходил недавно — не беспокоим

  navigator.serviceWorker.ready.then(reg => {
    if (!reg.active) return;
    // SW получит сообщение и покажет уведомление через 5 сек (демо)
    // В продакшн заменить на реальный Push API
    reg.active.postMessage({
      type: 'SCHEDULE_REMINDER',
      title: '✦ Astrea Timeline',
      body: `Вы не заглядывали в карту ${Math.floor(daysSince)} дн. Посмотрите, что происходит сейчас!`,
      delayMs: 5000,
    });
  }).catch(() => {});
}
