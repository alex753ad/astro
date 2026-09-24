/**
 * useReconnect.js — перезапросить, когда связь, скорее всего, вернулась.
 *
 * Три повода (решение владельца 24.09.2026): событие `online`, возврат
 * приложения из фона и повтор раз в 30 секунд.
 *
 * ⚠️ Всё это — ТОЛЬКО пока `waiting` (экран показывает сохранённое или
 * «нет сети») и приложение на экране. В фоне не крутится ничего: интервал
 * снимается на `hidden` и ставится заново на `visible`.
 *
 * ⚠️ Интервал — не перестраховка к `online`. Работает ли `online` в
 * Android WebView надёжно при выходе из режима полёта, на 24.09.2026 не
 * проверено; без интервала приёмка «включил сеть — обновилось само»
 * держалась бы на этом непроверенном допущении.
 */

import { useEffect, useRef } from 'react';

export const RECONNECT_EVERY_MS = 30000;

export default function useReconnect(waiting, reload) {
  const reloadRef = useRef(reload);
  reloadRef.current = reload;

  useEffect(() => {
    if (!waiting) return undefined;
    let timer = null;
    const fire = () => { reloadRef.current(); };
    const arm = () => {
      clearInterval(timer);
      timer = document.visibilityState === 'visible' ? setInterval(fire, RECONNECT_EVERY_MS) : null;
    };
    const onVisible = () => {
      arm();
      if (document.visibilityState === 'visible') fire();
    };
    arm();
    window.addEventListener('online', fire);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(timer);
      window.removeEventListener('online', fire);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [waiting]);
}
