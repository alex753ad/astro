/**
 * useCompactNow.js — включать ли компактную полоску «сейчас»
 * (FeedNowCompact.jsx) при текущей позиции прокрутки.
 *
 * ⚠️ Состояние меняется ТОЛЬКО на пересечении порога, а не на каждом кадре.
 * Требование владельца 15.09.2026, и оно не про аккуратность: в ленте 148
 * секций и больше сотни карточек — `setState` на каждом событии прокрутки
 * перерисовывал бы весь список, пока палец на экране. Поэтому текущее
 * значение живёт в `ref`, а `setState` зовётся только когда оно меняется.
 *
 * ⚠️ Гистерезис (`HYSTERESIS_PX`) — не украшение. Порог один и тот же на
 * включение и выключение означает, что человек, остановивший прокрутку ровно
 * на границе, получает мигание: полоска то появляется, то исчезает от
 * дрожания пальца в один-два пикселя. Поэтому выключается она НИЖЕ, чем
 * включилась.
 *
 * ⚠️ Порог измеряется один раз (и на `resize`), а не при каждом событии
 * прокрутки: `getBoundingClientRect` — чтение раскладки, и вызывать его на
 * каждом кадре прокрутки значит просить браузер пересчитать раскладку столько
 * же раз. `scrollTop` таким чтением не является.
 *
 * Возвращает true/false. Ref на измеряемый блок передаётся снаружи — это та
 * самая развёрнутая полоса, за уход которой с экрана мы и следим.
 */

import { useEffect, useRef, useState } from 'react';

/** На сколько ниже порога включения полоска гаснет. */
const HYSTERESIS_PX = 40;

export default function useCompactNow(scrollRef, anchorRef, enabled) {
  const [compact, setCompact] = useState(false);
  const compactRef = useRef(false);

  useEffect(() => {
    const scroller = scrollRef?.current;
    const anchor = anchorRef?.current;
    if (!enabled || !scroller || !anchor) {
      // Экран ушёл в загрузку/ошибку — полоску гасим, иначе она останется
      // висеть поверх состояния, к которому не относится.
      if (compactRef.current) { compactRef.current = false; setCompact(false); }
      return undefined;
    }

    let threshold = 0;
    const measure = () => {
      // Низ развёрнутой полосы в координатах прокрутки скроллера.
      threshold = anchor.getBoundingClientRect().bottom
        - scroller.getBoundingClientRect().top
        + scroller.scrollTop;
    };

    const apply = () => {
      const y = scroller.scrollTop;
      const next = compactRef.current
        ? y > threshold - HYSTERESIS_PX
        : y > threshold;
      if (next !== compactRef.current) {
        compactRef.current = next;
        setCompact(next);
      }
    };

    const onResize = () => { measure(); apply(); };

    measure();
    apply();
    scroller.addEventListener('scroll', apply, { passive: true });
    window.addEventListener('resize', onResize);
    return () => {
      scroller.removeEventListener('scroll', apply);
      window.removeEventListener('resize', onResize);
    };
  }, [scrollRef, anchorRef, enabled]);

  return compact;
}
