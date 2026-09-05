/**
 * FeedScreen.jsx — экран «Лента» (SPEC_FEED_SCREEN.md).
 *
 * Первый заход: поток событий, липкие заголовки дней, карточка события,
 * панель события по тапу, состояния загрузки/ошибки/отсутствия карты,
 * открытие на сегодняшнем дне.
 *
 * Второй заход добавил: полосу «сейчас» с долгосрочными периодами (§4),
 * свёртку лунного фона внутри дня (§7), карточку края горизонта (§9).
 *
 * ⚠️ `planner_longterm` изъят из потока (§4, §5: «изымаются полностью») и
 * живёт только в полосе сверху. Оставить их в потоке нельзя: их `at` лежит
 * на годы раньше окна (Плутон — 2012), и лента открывалась бы заголовком
 * «17 ноября 2012» над всем остальным. По той же причине после фильтрации
 * в потоке не остаётся ни одного события с `started_before` — единственный
 * вид, который его давал, только что убран.
 *
 * Прокрутка живёт в TabShell.jsx, одна на все вкладки, и здесь её заводить
 * нельзя: собственный `overflow` на любом предке заголовка сломал бы
 * `position: sticky` (подробности — в FeedDayHeader.jsx).
 */

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import FeedDayHeader from '../components/FeedDayHeader';
import FeedEventCard from '../components/FeedEventCard';
import FeedEventPanel from '../components/FeedEventPanel';
import FeedHorizonCard from '../components/FeedHorizonCard';
import FeedLunarFold, { isLunarBackground } from '../components/FeedLunarFold';
import FeedNowStrip from '../components/FeedNowStrip';
import FeedSkeleton from '../components/FeedSkeleton';
import { feedWindow, fetchFeed, resolvePrimaryChartId } from '../lib/feedApi';
import { dayLabel, groupByDay, localToday } from '../lib/feedTime';

const PAGE_PADDING = { padding: '0 16px 24px' };

function CenteredNotice({ title, text, action, onAction }) {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
        padding: '48px 24px',
        textAlign: 'center',
      }}
    >
      <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
        {title}
      </p>
      {text && (
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
          {text}
        </p>
      )}
      {action && (
        <button type="button" className="mobile-link" onClick={onAction} style={{ marginTop: 4 }}>
          {action}
        </button>
      )}
    </div>
  );
}

export default function FeedScreen() {
  // 'loading' | 'ready' | 'error' | 'no-chart'
  const [status, setStatus] = useState('loading');
  const [feed, setFeed] = useState(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const anchorRef = useRef(null);
  const userMovedRef = useRef(false);

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      const chartId = await resolvePrimaryChartId();
      if (!chartId) {
        setStatus('no-chart');
        return;
      }
      const data = await fetchFeed(chartId, feedWindow());
      setFeed(data);
      setStatus('ready');
    } catch (err) {
      // Текст уже человеческий: feedApi подменяет и «Chart not found»,
      // и сетевой сбой. Сюда попадает то, что можно показать как есть.
      setError(err?.message || 'Не удалось загрузить ленту.');
      setStatus('error');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Как только человек сам тронул ленту — перестаём её двигать. Иначе
  // до-прокрутка после подгрузки шрифта дёрнула бы экран из-под пальца.
  useEffect(() => {
    const moved = () => { userMovedRef.current = true; };
    window.addEventListener('touchstart', moved, { passive: true });
    window.addEventListener('wheel', moved, { passive: true });
    window.addEventListener('keydown', moved);
    return () => {
      window.removeEventListener('touchstart', moved);
      window.removeEventListener('wheel', moved);
      window.removeEventListener('keydown', moved);
    };
  }, []);

  const today = localToday();
  // planner_longterm — в полосу «сейчас» (§4), а не в поток. См. шапку.
  const allEvents = feed?.events || [];
  const longterm = allEvents.filter((e) => e.kind === 'planner_longterm');
  const events = allEvents.filter((e) => e.kind !== 'planner_longterm');
  const days = groupByDay(events);

  /**
   * §10: лента открывается на сегодня, прошлое отматывается вверх.
   *
   * Прокрутка повторяется трижды, и это не перестраховка. Одного вызова в
   * layout-эффекте не хватило (проверено первым заходом: лента открывалась
   * на 5 августа, начале окна, а не на сегодня). Причина — сдвиг раскладки
   * ПОСЛЕ первой прокрутки: до анкера лежит около полутора сотен карточек,
   * и когда локальный Inter доезжает и подменяет запасной шрифт, высоты
   * всех этих карточек пересчитываются. Якорь уезжает вниз ровно на
   * накопленную разницу, а экран остаётся там, где был, — то есть заметно
   * выше нужного дня.
   *
   *   1) сразу в layout-эффекте — до первого кадра, как требует §10;
   *   2) на следующем кадре — после того как браузер разложил список;
   *   3) по document.fonts.ready — после подмены шрифта, главный сдвиг.
   *
   * Любая из трёх отменяется, если человек уже тронул экран сам.
   */
  useLayoutEffect(() => {
    if (status !== 'ready' || !anchorRef.current) return undefined;

    let cancelled = false;
    const jump = () => {
      if (cancelled || userMovedRef.current || !anchorRef.current) return;
      anchorRef.current.scrollIntoView({ block: 'start', behavior: 'instant' });
    };

    jump();
    const raf = requestAnimationFrame(jump);
    document.fonts?.ready?.then(jump);

    return () => { cancelled = true; cancelAnimationFrame(raf); };
  }, [status, days.length]);

  if (status === 'loading') {
    return <div style={PAGE_PADDING}><FeedSkeleton /></div>;
  }

  if (status === 'error') {
    return <CenteredNotice title="Не удалось загрузить ленту" text={error} action="Повторить" onAction={load} />;
  }

  if (status === 'no-chart') {
    return (
      <CenteredNotice
        title="Пока нет ни одной карты"
        text="Лента строится по натальной карте. Постройте её на вкладке «Карта» — события появятся здесь."
      />
    );
  }

  if (days.length === 0) {
    return <CenteredNotice title="В этом окне событий нет" text="Попробуйте обновить ленту позже." action="Обновить" onAction={load} />;
  }

  // Якорь открытия: сегодняшний день, а если событий сегодня нет — первый
  // день после сегодняшнего (§10). Ищется один раз на список, а не в цикле
  // отрисовки, чтобы ref достался ровно одному заголовку.
  const anchorDate = (days.find((d) => d.date >= today) || days[days.length - 1]).date;

  return (
    <div style={PAGE_PADDING}>
      {/* Полоса «сейчас» — вне прокрутки потока по §3, но внутри общего
          скроллера: собственный overflow здесь сломал бы sticky заголовков
          (см. FeedDayHeader.jsx), а прибивать полосу к верху экрана
          спецификация не просит. */}
      <FeedNowStrip events={longterm} />

      {days.map((day) => {
        // Фон дня отделяется от событий: §7 сворачивает лунные транзиты и
        // проходы Луны по домам, но не фазы и не затмения — у тех своя
        // важность, и они остаются в потоке как события.
        const background = day.events.filter(isLunarBackground);
        const foreground = day.events.filter((e) => !isLunarBackground(e));
        return (
          <section key={day.date} ref={day.date === anchorDate ? anchorRef : undefined}>
            <FeedDayHeader label={dayLabel(day.date, today)} />
            {foreground.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: background.length ? 12 : 16 }}>
                {foreground.map((event) => (
                  <FeedEventCard key={event.key} event={event} onOpen={setSelected} />
                ))}
              </div>
            )}
            <FeedLunarFold events={background} onOpen={setSelected} />
          </section>
        );
      })}

      <FeedHorizonCard horizon={feed?.horizon} />

      <FeedEventPanel event={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
