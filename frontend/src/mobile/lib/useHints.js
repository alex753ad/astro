/**
 * useHints.js — общая логика показа подсказок для «Карты» и «Ленты»
 * (SPEC_ONBOARDING.md §8, §9).
 *
 * Держит одно решение в одном месте: когда подсказки открываются сами,
 * когда их можно открыть кнопкой и когда ставится флаг «видел». Экраны
 * отличаются только тем, ЧТО подсвечивают, — эта часть остаётся у них.
 *
 * ⚠️ `ready` — не «компонент смонтирован», а «данные экрана загружены и
 * отрисованы». Пока данные не пришли, подсвечивать нечего, и рамка ушла бы
 * в пустоту. У обоих экранов для этого уже есть своё состояние (`status`),
 * заводить новое не нужно:
 *   «Карта» — status === 'ready';
 *   «Лента» — status === 'ready' И days.length > 0.
 * Состояния loading / error / no-chart / пустое окно подсказок не
 * показывают вовсе — включая ручной вызов: на них и кнопки «?» нет,
 * объяснять нечего.
 */

import { useCallback, useEffect, useState } from 'react';
import { HINTS_KEYS, isSeen, markSeen } from './onboardingFlags';

export default function useHints(screen, ready) {
  const key = HINTS_KEYS[screen];
  const [open, setOpen] = useState(false);

  // Автопоказ — один раз, при первом переходе экрана в готовое состояние.
  // Флаг проверяется здесь, а не в рендере: isSeen ходит в localStorage.
  useEffect(() => {
    if (ready && !isSeen(key)) setOpen(true);
  }, [ready, key]);

  // ⚠️ Флаг ставится при ЗАКРЫТИИ (последний шаг, «Понятно»), а не при
  // показе: свернувший приложение на середине увидит подсказки снова
  // (SPEC_ONBOARDING.md §6).
  const close = useCallback(() => {
    setOpen(false);
    markSeen(key);
  }, [key]);

  // Ручной вызов кнопкой «?». Флаг при этом не трогаем: он уже стоит (или
  // встанет при закрытии), а повторный вызов — не «первый показ».
  const show = useCallback(() => setOpen(true), []);

  return { open: open && ready, show, close };
}
