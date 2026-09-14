/**
 * HintOverlay.jsx — подсказки поверх экрана: затемнение, подсвеченный
 * элемент, короткая реплика, «Далее» / «Понятно» (SPEC_ONBOARDING.md §8).
 *
 * Общий для «Карты» и «Ленты». Шаги приходят снаружи вместе с картой
 * ref'ов — компонент не знает, что именно подсвечивает.
 *
 * ⚠️ СЛОЙ. z-index в приложении сегодня: липкий заголовок дня — 1, кнопка
 * чата (AristeaFab) — 5, панель события — 20/21, шторка чата — 30/31.
 * Поэтому здесь 40/41: с меньшим числом кнопка чата и панель события
 * прорисуются ПОВЕРХ затемнения — она `position: fixed` и в раскладке
 * скроллера не участвует вовсе. Кнопку чата на время подсказок вдобавок
 * прячет TabShell (она уводит в чат посреди объяснения).
 *
 * ⚠️ КОГДА ЗАМЕРЯТЬ. Координаты снимаются только после того, как устоялась
 * раскладка: `document.fonts.ready`, затем ещё один кадр. Это тот же
 * капкан, что уже сработал на открытии «Ленты» на сегодняшнем дне —
 * локальный Inter догружается, высоты пересчитываются, и всё, измеренное
 * раньше, уезжает (CLAUDE.md, «Прокрутка к якорю сбивается подменой
 * шрифта»). Симптом здесь другой и оттого не сразу узнаваемый: рамка
 * встанет рядом с элементом, а не на нём.
 *
 * Затемнение сделано не четырьмя прямоугольниками вокруг выреза, а одним
 * прозрачным блоком с огромной тенью (`box-shadow: 0 0 0 9999px`): вырез
 * тогда всегда точно совпадает с рамкой, и их не нужно держать в синхроне
 * между собой.
 */

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { HINT_BUTTONS } from '../lib/onboardingCopy';

const DIM = 'rgba(0,0,0,0.45)';   // то же значение, что у AristeaChatStub — двух разных затемнений в приложении быть не должно
const PAD = 6;                     // отступ рамки от элемента
const GAP = 12;                    // зазор между рамкой и репликой
const CARD_MIN_H = 132;            // грубая оценка высоты реплики: нужна до её отрисовки, чтобы выбрать сторону

export default function HintOverlay({ steps, anchors, onClose }) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState(null);
  const rafRef = useRef(0);

  const step = steps[index];
  const isLast = index === steps.length - 1;

  const measure = useCallback(() => {
    const el = anchors[step?.anchor]?.current;
    if (!el) { setRect(null); return; }
    const r = el.getBoundingClientRect();
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, [anchors, step]);

  // Прокрутка к элементу, если он вне видимой области. Прокрутка в
  // приложении одна на все вкладки и живёт в TabShell.jsx — свой overflow
  // здесь заводить нельзя, он сломал бы sticky у заголовков дней
  // (FeedDayHeader.jsx). scrollIntoView сам найдёт нужный скроллер.
  useLayoutEffect(() => {
    const el = anchors[step?.anchor]?.current;
    if (!el) return undefined;

    const r = el.getBoundingClientRect();
    const offscreen = r.top < 0 || r.bottom > window.innerHeight;
    if (offscreen) el.scrollIntoView({ block: 'center', behavior: 'auto' });

    let cancelled = false;
    const remeasure = () => {
      if (cancelled) return;
      // Кадр после прокрутки: до него getBoundingClientRect вернёт
      // координаты ДО неё.
      rafRef.current = requestAnimationFrame(measure);
    };

    remeasure();
    // Второй проход — когда шрифты доехали и высоты пересчитались.
    if (document.fonts?.ready) document.fonts.ready.then(remeasure).catch(() => {});

    return () => { cancelled = true; cancelAnimationFrame(rafRef.current); };
  }, [anchors, step, measure]);

  // Поворот экрана и любое изменение размеров: рамка обязана остаться на
  // своём элементе (п. 7 чек-листа приёмки, SPEC_ONBOARDING.md §14).
  useEffect(() => {
    const onResize = () => measure();
    window.addEventListener('resize', onResize);
    window.addEventListener('orientationchange', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      window.removeEventListener('orientationchange', onResize);
    };
  }, [measure]);

  const finish = () => { if (isLast) onClose(); else setIndex((i) => i + 1); };

  // Реплика встаёт под элементом, а если снизу не помещается — над ним.
  const below = rect ? rect.top + rect.height + GAP : 0;
  const fitsBelow = rect ? below + CARD_MIN_H < window.innerHeight : true;

  return (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 40 }}
      role="dialog"
      aria-modal="true"
      // Тап по затемнению намеренно ничего не делает: шаги закрываются
      // явными кнопками. Случайное касание не должно обрывать объяснение.
      onClick={(e) => e.stopPropagation()}
    >
      {rect ? (
        <div
          style={{
            position: 'absolute',
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            borderRadius: 'var(--radius-lg)',
            border: '2px solid var(--accent)',
            boxShadow: `0 0 0 9999px ${DIM}`,
            pointerEvents: 'none',
          }}
        />
      ) : (
        // Элемент не найден (экран перерисовался, шаг указывает на то, чего
        // сейчас нет) — показываем реплику на ровном затемнении, а не
        // прячем шаг: текст полезен и без подсветки.
        <div style={{ position: 'absolute', inset: 0, background: DIM }} />
      )}

      <div
        style={{
          position: 'absolute',
          left: 16,
          right: 16,
          ...(rect && fitsBelow ? { top: below } : {}),
          ...(rect && !fitsBelow ? { top: Math.max(16, rect.top - GAP - CARD_MIN_H) } : {}),
          ...(rect ? {} : { top: '50%', transform: 'translateY(-50%)' }),
          zIndex: 41,
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          padding: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}
      >
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-primary)' }}>
          {step?.text}
        </p>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontVariantNumeric: 'tabular-nums' }}>
            {index + 1} / {steps.length}
          </span>
          <button
            type="button"
            className="mobile-btn-primary"
            style={{ marginLeft: 'auto', width: 'auto', padding: '10px 20px' }}
            onClick={finish}
          >
            {isLast ? HINT_BUTTONS.done : HINT_BUTTONS.next}
          </button>
        </div>
      </div>
    </div>
  );
}
