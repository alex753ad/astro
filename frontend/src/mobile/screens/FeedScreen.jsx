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

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import FeedDayHeader from '../components/FeedDayHeader';
import FeedDayStrip from '../components/FeedDayStrip';
import FeedEventCard from '../components/FeedEventCard';
import FeedEventPanel from '../components/FeedEventPanel';
import FeedHorizonCard from '../components/FeedHorizonCard';
import FeedLunarFold, { isLunarBackground } from '../components/FeedLunarFold';
import FeedNowStrip from '../components/FeedNowStrip';
import FeedSkeleton from '../components/FeedSkeleton';
import FeedTimelineNode from '../components/FeedTimelineNode';
import { feedWindow, fetchFeed, resolvePrimaryChartId } from '../lib/feedApi';
import { dateShort, dayLabel, groupByDay, localToday, timePart } from '../lib/feedTime';
import { dotColor, dotSize } from '../lib/feedTimelineDot';

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
  // Один узел на дату — используется и для якоря открытия (§10), и для тапа
  // по полоске дней (§7): второе не заводит свой отдельный набор рефов.
  const dayRefs = useRef(new Map());

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
  // Фильтрация по kind живёт здесь и внутри FeedNowStrip.jsx одновременно —
  // не дублирование правила, а две независимые выборки из одного массива:
  // тут нужны все, КРОМЕ долгосрочных, там — не только они, а весь список
  // (полосе ещё нужны период Солнца и ближайшая фаза Луны, §6).
  const allEvents = feed?.events || [];
  const events = allEvents.filter((e) => e.kind !== 'planner_longterm');
  const days = groupByDay(events);

  /**
   * Точки полоски дней (§7) — по дате, до 3 цветов, тем же dotColor(), что и
   * у узла на линии (одна таблица цветов на оба места). Лунные транзиты
   * (importance: low) не считаются намеренно: у них своя, отдельная от
   * важных событий природа (§7 сама это оговаривает), и посчитай их —
   * у каждого дня был бы полный ряд из трёх точек, индикатор перестал бы
   * что-либо различать.
   */
  const dotsByDay = useMemo(() => {
    const map = new Map();
    for (const e of events) {
      if (e.importance === 'low') continue;
      const date = e.at.slice(0, 10);
      const arr = map.get(date) || [];
      if (arr.length < 3) { arr.push(dotColor(e)); map.set(date, arr); }
    }
    return map;
  }, [events]);

  const scrollToDay = useCallback((date) => {
    userMovedRef.current = true; // тап по полоске — это осознанное движение, а не подгрузка шрифта
    const target = days.find((d) => d.date >= date) || days[days.length - 1];
    dayRefs.current.get(target?.date)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, [days]);

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
      <FeedNowStrip events={allEvents} today={today} />
      <FeedDayStrip
        from={feed?.horizon?.from}
        to={feed?.horizon?.to}
        today={today}
        dotsByDay={dotsByDay}
        onSelectDay={scrollToDay}
      />

      {days.map((day) => {
        // Фон дня отделяется от событий: §7 сворачивает лунные транзиты и
        // проходы Луны по домам, но не фазы и не затмения — у тех своя
        // важность, и они остаются в потоке как события.
        const background = day.events.filter(isLunarBackground);
        const foreground = day.events.filter((e) => !isLunarBackground(e));
        // При одном лунном событии свёртывать нечего — «ещё 1 лунное»
        // ничего не сокращает, только добавляет лишний тап. Показываем его
        // как обычный узел линии; сворачиваем только от двух и больше.
        const soloLunar = background.length === 1 ? background[0] : null;
        const foldedLunar = background.length > 1 ? background : [];
        return (
          <section
            key={day.date}
            ref={(el) => {
              if (el) dayRefs.current.set(day.date, el); else dayRefs.current.delete(day.date);
              if (day.date === anchorDate) anchorRef.current = el;
            }}
          >
            <FeedDayHeader label={dayLabel(day.date, today)} />
            {foreground.map((event) => {
              // Период (planner_period) метится датой начала, точка —
              // временем (§3). Оба признака — те же, что задают высоту
              // карточки в FeedEventCard.jsx (durationHeight), не выдумка.
              const isPeriod = Boolean(event.ends_at && event.duration_days);
              return (
                <FeedTimelineNode
                  key={event.key}
                  time={isPeriod ? dateShort(event.at) : timePart(event.at)}
                  bold={isPeriod}
                  color={dotColor(event)}
                  size={dotSize(event)}
                >
                  <FeedEventCard event={event} onOpen={setSelected} />
                </FeedTimelineNode>
              );
            })}
            {soloLunar && (
              <FeedTimelineNode
                key={soloLunar.key}
                time={timePart(soloLunar.at)}
                color={dotColor(soloLunar)}
                size={dotSize(soloLunar)}
              >
                <FeedEventCard event={soloLunar} onOpen={setSelected} />
              </FeedTimelineNode>
            )}
            {foldedLunar.length > 0 && (
              <FeedTimelineNode time="" gap={16}>
                <FeedLunarFold events={foldedLunar} onOpen={setSelected} />
              </FeedTimelineNode>
            )}
          </section>
        );
      })}

      <FeedHorizonCard horizon={feed?.horizon} />

      <FeedEventPanel event={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
