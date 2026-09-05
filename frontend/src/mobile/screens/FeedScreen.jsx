/**
 * FeedScreen.jsx — экран «Лента» (SPEC_FEED_SCREEN.md, первый заход).
 *
 * Сделано в этом заходе: поток событий, липкие заголовки дней, карточка
 * события, состояния загрузки/ошибки/отсутствия карты, открытие на
 * сегодняшнем дне.
 *
 * НЕ сделано, вынесено во второй заход по решению владельца: полоса
 * «сейчас» с долгосрочными периодами (§4), свёртка лунных транзитов (§7),
 * карточка края горизонта (§9).
 *
 * ⚠️ `planner_longterm` уже сейчас изъят из потока (§4, §5: «изымаются
 * полностью»), хотя полосы для него ещё нет — то есть пять этих событий в
 * первом заходе не показываются нигде. Оставить их в потоке было бы хуже
 * молчаливой потери: их `at` лежит на годы раньше окна (Плутон — 2012), и
 * лента открывалась бы заголовком «17 ноября 2012» над всем остальным. По
 * той же причине после фильтрации в потоке не остаётся ни одного события с
 * `started_before` — единственный вид, который его давал, только что убран
 * (§5).
 *
 * Прокрутка живёт в TabShell.jsx, одна на все вкладки, и здесь её заводить
 * нельзя: собственный `overflow` на любом предке заголовка сломал бы
 * `position: sticky` (подробности — в FeedDayHeader.jsx).
 */

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import FeedDayHeader from '../components/FeedDayHeader';
import FeedEventCard from '../components/FeedEventCard';
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
  const todayRef = useRef(null);
  const scrolledRef = useRef(false);

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

  const today = localToday();
  // planner_longterm — в полосу «сейчас» (§4), а не в поток. См. шапку.
  const events = (feed?.events || []).filter((e) => e.kind !== 'planner_longterm');
  const days = groupByDay(events);

  // §10: лента открывается на сегодня, прошлое отматывается вверх.
  // Якорь — заголовок сегодняшнего дня; если событий сегодня нет, ref
  // достаётся ближайшему следующему дню (см. ниже, при отрисовке).
  // useLayoutEffect, а не useEffect: прокрутка обязана произойти ДО того,
  // как кадр покажут, иначе виден скачок с начала месяца на сегодня.
  useLayoutEffect(() => {
    if (status !== 'ready' || scrolledRef.current) return;
    if (todayRef.current) {
      todayRef.current.scrollIntoView({ block: 'start' });
      scrolledRef.current = true;
    }
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
  // день после сегодняшнего. Ищется один раз на список, а не в цикле
  // отрисовки, чтобы ref достался ровно одному заголовку.
  const anchorDate = (days.find((d) => d.date >= today) || days[days.length - 1]).date;

  return (
    <div style={PAGE_PADDING}>
      {days.map((day) => (
        <section key={day.date} ref={day.date === anchorDate ? todayRef : undefined}>
          <FeedDayHeader label={dayLabel(day.date, today)} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 16 }}>
            {day.events.map((event) => (
              <FeedEventCard key={event.key} event={event} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
