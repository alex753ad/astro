/**
 * usePullToRefresh.js — жест «потянуть, чтобы обновить». Один на три экрана.
 *
 * Зачем вообще: обновить данные в приложении было нечем. `load()` на всех
 * трёх экранах вызывается только на монтировании, а `TabShell` экраны не
 * размонтирует — карта, построенная на сайте, появлялась только после
 * перезапуска приложения (SESSION_2026-09-08.md).
 *
 * ⚠️ Почему жест, а не перезагрузка на возврате из фона (решение владельца
 * 08.09.2026): из фона поднялись бы ВСЕ ТРИ смонтированных экрана разом —
 * ровно тот залп, ради которого писались гейт по сроку токена и пауза после
 * неудачного обновления (CLAUDE.md, «Холодный старт упирается в
 * ЗАДЕРЖИВАЮЩИЙ лимит»). Жест обновляет один экран и только по явному
 * действию человека.
 *
 * ⚠️ Скроллер у каждой вкладки СВОЙ, общего нет — поэтому хук принимает ref,
 * а не ищет контейнер сам:
 *   • «Лента» — общий скроллер в TabShell.jsx (своего у неё быть не может:
 *     `overflow` на любом предке сломал бы `position: sticky` заголовков
 *     дней, см. FeedDayHeader.jsx);
 *   • «Карта» — список внутри ChartSheet.jsx (у самого экрана прокрутки
 *     нет вовсе: колесо и шторка делят высоту);
 *   • «Ещё» — собственный корневой div экрана.
 *
 * ⚠️ Слушатели вешаются через addEventListener на сам узел, а НЕ через
 * JSX-пропы onTouchMove: React 18 вешает touchstart/touchmove на корень
 * пассивными, и preventDefault() из пропа молча не сработал бы. Здесь он
 * нужен — иначе контейнер начнёт прокручиваться, стоит пальцу пойти обратно
 * вверх посреди жеста.
 *
 * ⚠️ Высота полоски меняется ПРЯМОЙ записью в style, а не через состояние
 * React, и это не микрооптимизация. Палец шлёт touchmove на каждый кадр; на
 * «Ленте» один рендер — это полторы сотни секций с карточками, то есть жест
 * заставлял бы пересобирать весь список 60 раз в секунду и заметно дёргался
 * бы на слабом устройстве. Через состояние проходят только РЕДКИЕ переходы:
 * фаза (idle/refreshing/error) и пересечение порога — не чаще пары раз за
 * жест.
 *
 * Библиотеки нет намеренно: framer-motion в зависимостях есть, но
 * соглашение проекта — «только поверх готовых компонентов», а здесь своя
 * механика с чтением scrollTop, к которой его drag отношения не имеет.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

/** Сколько нужно протянуть, чтобы жест сработал (после сопротивления). */
export const PULL_THRESHOLD = 64;

/** Дальше палец тянет, а полоска не растёт — иначе жест выглядит бездонным. */
const MAX_PULL = 96;

/** Палец проходит вдвое больше, чем едет полоска: без этого жест «липкий». */
const RESISTANCE = 0.5;

/**
 * Сколько держится «Не удалось обновить».
 *
 * Ошибка обязана быть видимой, но не должна уводить экран в состояние
 * `error`: там полноэкранное «Не удалось загрузить…», и один неудачный
 * жест спрятал бы за ним уже загруженные и по-прежнему годные данные.
 */
export const ERROR_HOLD_MS = 2200;

/** Пока сдвиг меньше — направление ещё не понятно, решение не принимаем. */
const DIRECTION_SLOP = 8;

/**
 * Чистые функции ниже — единственная часть жеста, которую в этом проекте
 * вообще можно проверить: DOM-окружения для тестов нет (ни jsdom, ни
 * testing-library), и всё, что живёт внутри эффекта с touch-событиями,
 * проверяется только руками на устройстве. Поэтому решения «куда поехал
 * палец» и «насколько выросла полоска» вынесены сюда и покрыты
 * usePullToRefresh.test.js — по образцу lib/refreshSchedule.js, где так же
 * поступили с расписанием обновления сессии и где ровно из-за
 * непроверяемости внутри хука два дефекта прожили незамеченными.
 */

/**
 * Что делать с начавшимся движением пальца.
 *
 *   'pull'      — вертикально вниз, тянем;
 *   'abandon'   — вверх или вбок: это обычная прокрутка (или горизонтальная
 *                 полоска дней на «Ленте»), жест не наш и больше не наш до
 *                 следующего касания;
 *   'undecided' — сдвиг ещё в пределах слопа, решение рано принимать.
 */
export function gestureDecision(dx, dy) {
  if (Math.abs(dx) >= Math.abs(dy)) return 'abandon';
  if (dy <= 0) return 'abandon';
  if (Math.abs(dy) < DIRECTION_SLOP) return 'undecided';
  return 'pull';
}

/** Насколько выросла полоска при сдвиге пальца на `dy`. */
export function pullOffset(dy) {
  if (dy <= 0) return 0;
  return Math.min(dy * RESISTANCE, MAX_PULL);
}

/**
 * @param scrollRef  ref на прокручиваемый узел (у каждой вкладки свой)
 * @param onRefresh  что обновлять; ОБЯЗАН бросать исключение при неудаче —
 *                   молчаливый отказ здесь неотличим от успеха
 * @param enabled    жест включён (обычно: вкладка активна и состояние ready)
 * @returns { state, ready, indicatorRef } — ref вешается на узел полоски:
 *          её высоту хук ведёт сам, мимо рендера (см. шапку)
 */
export default function usePullToRefresh(scrollRef, onRefresh, enabled = true) {
  const [state, setState] = useState('idle');
  const [ready, setReady] = useState(false);
  const indicatorRef = useRef(null);

  // Фаза нужна и в обработчиках событий, которые живут вне рендера:
  // читать её из state там значило бы получить значение с прошлого рендера.
  const phaseRef = useRef('idle');
  const setPhase = useCallback((next) => {
    phaseRef.current = next;
    setState(next);
  }, []);

  // Свежий колбэк без переподписки на события: пересоздавать слушатели на
  // каждый рендер экрана — терять начатый жест на ровном месте.
  const onRefreshRef = useRef(onRefresh);
  useEffect(() => { onRefreshRef.current = onRefresh; }, [onRefresh]);

  useEffect(() => {
    const node = scrollRef?.current;
    if (!enabled || !node) return undefined;

    let startY = 0;
    let startX = 0;
    let armed = false;    // жест начат у самого верха — можно тянуть
    let pulling = false;  // направление распознано, тянем
    let pulled = 0;
    let errorTimer = null;

    // Высота — прямо в style, мимо рендера.
    //
    // ⚠️ Возвращая полоску в покой, писать сюда НОЛЬ, а не очищать стиль.
    // React применяет только различия: в его памяти высота осталась той,
    // что он выставил в прошлом рендере (0 в покое), и после `style.height
    // = ''` он не увидит расхождения и ничего не перепишет. Элемент
    // остался бы высотой по содержимому — на экране висела бы полоска с
    // текстом «Потяните, чтобы обновить», которую ничем не убрать.
    const draw = (px) => {
      const el = indicatorRef.current;
      if (el) el.style.height = `${px}px`;
    };

    const reset = () => { armed = false; pulling = false; pulled = 0; };

    const onStart = (e) => {
      if (phaseRef.current === 'refreshing' || e.touches.length !== 1) {
        reset();
        return;
      }
      // Тянуть можно только от верхнего края: иначе жест воровал бы
      // обычную прокрутку списка.
      armed = node.scrollTop <= 0;
      pulling = false;
      pulled = 0;
      startY = e.touches[0].clientY;
      startX = e.touches[0].clientX;
    };

    const onMove = (e) => {
      if (!armed || e.touches.length !== 1) return;
      const dy = e.touches[0].clientY - startY;
      const dx = e.touches[0].clientX - startX;

      if (!pulling) {
        // ⚠️ Проверка направления обязательна: на «Ленте» жест начинается
        // ровно там, где лежит горизонтальная полоска дней (FeedDayStrip,
        // overflowX: auto). Без неё горизонтальная прокрутка полоски и
        // вертикальное потягивание спорили бы за один и тот же палец.
        const decision = gestureDecision(dx, dy);
        if (decision === 'undecided') return;
        if (decision === 'abandon') { armed = false; return; }
        pulling = true;
      }

      if (dy <= 0) { pulled = 0; draw(0); setReady(false); return; }
      e.preventDefault();
      pulled = pullOffset(dy);
      draw(pulled);
      // Через состояние проходит только сам факт пересечения порога —
      // это меняет надпись, а не высоту, и случается раз-два за жест.
      setReady(pulled >= PULL_THRESHOLD);
    };

    const onEnd = async () => {
      if (!pulling) { reset(); return; }
      const trigger = pulled >= PULL_THRESHOLD;
      reset();
      draw(0);
      setReady(false);
      if (!trigger) return;

      setPhase('refreshing');
      try {
        await onRefreshRef.current?.();
        setPhase('idle');
      } catch {
        // Данные на экране остаются прежними — они не хуже, чем были до
        // жеста. Показываем отказ той же полоской и убираем сами.
        setPhase('error');
        errorTimer = setTimeout(() => setPhase('idle'), ERROR_HOLD_MS);
      }
    };

    // passive: false только у touchmove — там нужен preventDefault.
    node.addEventListener('touchstart', onStart, { passive: true });
    node.addEventListener('touchmove', onMove, { passive: false });
    node.addEventListener('touchend', onEnd);
    node.addEventListener('touchcancel', onEnd);

    return () => {
      draw(0);
      node.removeEventListener('touchstart', onStart);
      node.removeEventListener('touchmove', onMove);
      node.removeEventListener('touchend', onEnd);
      node.removeEventListener('touchcancel', onEnd);
      if (errorTimer) clearTimeout(errorTimer);
    };
  }, [enabled, scrollRef, setPhase]);

  return { state, ready, indicatorRef };
}
