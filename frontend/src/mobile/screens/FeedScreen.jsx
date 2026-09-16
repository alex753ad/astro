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
 * «17 ноября 2012» над всем остальным. С 16.09.2026 чип в полосе снова
 * нажимаем и открывает ту же панель события — то есть срок и рекомендации
 * долгосрочного периода доступны, а поток от них не страдает.
 *
 * ⚠️ `started_before` после этой фильтрации больше НЕ пуст, хотя до
 * 16.09.2026 был: проход Луны по дому, идущий на момент начала окна, приходит
 * со своим настоящим началом за левым краем (граница считается по проходам, а
 * не по полуночи — backend/transit/house_passages.py). Таких событий ровно
 * одно на ленту, и оно даёт один лишний день в самом начале списка — на месяц
 * в прошлом, куда почти не прокручивают. Флаг по-прежнему не рисуется нигде;
 * если понадобится — это место, где о нём надо помнить.
 *
 * Третий заход (15.09.2026, DESIGN_SYSTEM.md §5) сделал день БЛОКОМ: ритм
 * ленты задаёт ОБЪЁМ, а не кегль. Рядовое событие в нераскрытом дне сжато в
 * одну строку (FeedEventRow.jsx), карточкой остаётся только крупное
 * (feedRank.js), лунный фон приглушён, а раскрыт ровно один день — тот, на
 * котором лента открывается, и он же единственная поднятая поверхность.
 *
 * ⚠️ Раскрытый день привязан к `anchorDate`, а НЕ к `today`. Это не то же
 * самое: дни строятся из событий, и дня без событий в списке нет вовсе —
 * значит при пустом сегодня раскрывать было бы нечего, лента открылась бы на
 * сжатом дне, и обещание «сегодняшний день раскрыт» не выполнялось бы. По
 * боевой выдаче это не редкость: 68 дней из 148 не содержат ни одной карточки.
 * Пометку «Сегодня» при этом рисует заголовок и только настоящему сегодня —
 * раскрытый день и сегодняшний день могут не совпадать, и врать об этом
 * нельзя.
 *
 * Прокрутка живёт в TabShell.jsx, одна на все вкладки. Прежний довод «свой
 * `overflow` сломает липкие заголовки» с 15.09.2026 недействителен —
 * липкости у заголовков дня больше нет (FeedDayHeader.jsx). Но заводить
 * собственный скроллер здесь всё равно нельзя: на него завязаны жест
 * обновления, открытие на сегодняшнем дне, компактная полоса и дата дня у
 * кромки — все они получают скроллер снаружи, из TabShell.
 */

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import FeedDayHeader from '../components/FeedDayHeader';
import FeedDayStrip from '../components/FeedDayStrip';
import FeedEventCard from '../components/FeedEventCard';
import FeedEventRow from '../components/FeedEventRow';
import FeedEventPanel from '../components/FeedEventPanel';
import FeedHorizonCard from '../components/FeedHorizonCard';
import FeedLunarFold, { isLunarBackground } from '../components/FeedLunarFold';
import FeedNowStrip from '../components/FeedNowStrip';
import FeedNowCompact from '../components/FeedNowCompact';
import PullIndicator from '../components/PullIndicator';
import FeedSkeleton from '../components/FeedSkeleton';
import FeedTimelineNode from '../components/FeedTimelineNode';
import HintOverlay from '../components/HintOverlay';
import { FEED_HINTS } from '../lib/onboardingCopy';
import usePullToRefresh from '../lib/usePullToRefresh';
import useHints from '../lib/useHints';
import useCompactNow from '../lib/useCompactNow';
import { feedWindow, fetchFeed, resolvePrimaryChart } from '../lib/feedApi';
import { dateShort, groupByDay, localToday, timePart, weekdayShort } from '../lib/feedTime';
import { pickAnchorDate } from '../lib/feedAnchor';
import { splitDayEvents } from '../lib/feedDayOrder';
import { isMajorEvent } from '../lib/feedRank';
import { dotColor, dotSize } from '../lib/feedTimelineDot';
import useAuth from '../../hooks/useAuth.jsx';

// ⚠️ Нижний запас — ЗДЕСЬ, а не только на скроллере (TabShell.jsx). Приёмка
// 15.09.2026: последние строки ленты уходили под кнопку чата. Замер при
// точной геометрии (скроллер 788, кнопка 52 при bottom = таб-бар + 16):
// низ последнего элемента 764 против верха кнопки 720 — 44 px содержимого
// под кнопкой. Паддинг скроллера до содержимого не доезжал; отступ в самом
// потоке от этого не зависит вовсе.
//
// 96 = 52 (кнопка) + 16 (её отступ снизу) + 16 запаса + 12 на тень.
/** Насколько нужно прокрутить, чтобы шапка свернулась. См. эффект ниже. */
const HEADER_COLLAPSE_PX = 24;

/*
 * ⚠️ 16px по бокам — и трогать их нельзя ради ширины карточки периода.
 * Пятый заход 16.09.2026 срезал их до 8, и вместе с карточкой влево уехала
 * ВСЯ лента: заголовки дней встали почти у кромки, «Уран: начало
 * ретроградности» упёрся в правый край. Поле страницы держит не карточку, а
 * весь экран — заголовки, разделители, линию.
 *
 * Ширина расшифровки берётся ВНУТРИ карточки: её собственные поля, отступ
 * пунктов и зазор до вертикальной линии. Там же она и осталась.
 */
const PAGE_PADDING = { padding: '0 16px 96px' };

function CenteredNotice({ title, text, action, onAction, secondary, onSecondary }) {
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
      {secondary && (
        <button
          type="button"
          className="mobile-link"
          onClick={onSecondary}
          style={{ marginTop: 2, fontSize: 13, color: 'var(--text-secondary)' }}
        >
          {secondary}
        </button>
      )}
    </div>
  );
}

export default function FeedScreen({ active = true, onHintsToggle, scrollRef, chartsVersion = 0, onChartResolved }) {
  // 'loading' | 'ready' | 'error' | 'no-chart'
  const [status, setStatus] = useState('loading');
  const [feed, setFeed] = useState(null);
  const [error, setError] = useState('');
  const { logout } = useAuth();
  const [selected, setSelected] = useState(null);
  /**
   * Периоды планера, которые человек ПЕРЕКЛЮЧИЛ вручную (ключи событий).
   *
   * ⚠️ Это множество «наоборот от умолчания», а не «раскрытых». Умолчание
   * зависит от дня: в дне-якоре период раскрыт, в остальных свёрнут. С
   * 16.09.2026 сворачивать можно и сегодняшний, и хранить отдельно
   * «раскрытые» и «свёрнутые» значило бы держать два множества и следить,
   * чтобы ключ не попал в оба. Одно множество-переключатель этого не
   * допускает по построению.
   *
   * ⚠️ Состояние живёт ЗДЕСЬ, а не внутри карточки. Карточка пересоздаётся при
   * каждом обновлении ленты (жест обновления, возврат из фона), и локальное
   * состояние схлопнуло бы всё, что человек только что раскрыл или свернул.
   * Ключ события устойчив между окнами у транзитов и лунных; у периодов
   * планера — нет (известный дефект, docs/HISTORY-feed.md), и тогда состояние
   * вернётся к умолчанию: это честнее, чем применить его к чужому периоду с
   * совпавшим ключом.
   */
  const [flippedPeriods, setFlippedPeriods] = useState(() => new Set());
  /**
   * Развёрнута ли шапка поверх ленты (решение владельца 16.09.2026).
   *
   * ⚠️ `true` при открытии — и это НЕ то же, что «шапка в потоке». Лента
   * открывается на сегодняшнем дне, то есть прокрученной; потоковая шапка в
   * этот момент уже за верхом экрана, и без оверлея человек видит ленту без
   * шапки вовсе. Ровно это и поймали на приёмке.
   */
  const [headerOpen, setHeaderOpen] = useState(true);
  const togglePeriod = useCallback((event) => {
    setFlippedPeriods((prev) => {
      const next = new Set(prev);
      if (next.has(event.key)) next.delete(event.key); else next.add(event.key);
      return next;
    });
  }, []);
  const [chartId, setChartId] = useState(null);
  const anchorRef = useRef(null);
  // Якорь подсветки для чипов домов (SPEC_ONBOARDING.md §11). Остальные два
  // шага переиспользуют `anchorRef` — секцию сегодняшнего дня.
  //
  // ⚠️ Своей обёртки вокруг списка дней ради якоря «поток» здесь НЕТ
  // намеренно. Лишний уровень DOM вокруг секций — ровно тот класс правки,
  // которым на этом экране уже ломали раскладку. Ради подсветки трогать
  // структуру принятого экрана дороже, чем подсветить сегодняшний день
  // дважды с разным текстом.
  const chipsRef = useRef(null);
  const userMovedRef = useRef(false);
  // Один узел на дату — используется и для якоря открытия (§10), и для тапа
  // по полоске дней (§7): второе не заводит свой отдельный набор рефов.
  const dayRefs = useRef(new Map());
  // День, на который лента открывается (§10). Держим в ref: обработчик
  // кнопки «Сегодня» создаётся раньше, чем считается anchorDate, и
  // пересоздавать его на каждый рендер ради одного значения незачем.
  const anchorDateRef = useRef(null);
  // Развёрнутая полоса «сейчас»: за её уходом с экрана следит хук ниже.
  const nowStripRef = useRef(null);

  /**
   * `silent` — обновление жестом, без смены состояния на 'loading'.
   * Полное «почему» — в шапке lib/usePullToRefresh.js; здесь то, что
   * ломается именно на этой вкладке:
   *
   * ⚠️ Ветка `status === 'loading'` возвращает скелет ВМЕСТО списка, то
   * есть размонтирует его. Высота скроллера схлопывается, браузер
   * прижимает прокрутку к нулю — и человек оказывается в начале окна,
   * месяцем раньше. Якорь на сегодня (§10) обратно НЕ вернёт: он
   * отменяется флагом userMovedRef, а тот взводится любым касанием — то
   * есть самим жестом — и никогда не сбрасывается.
   *
   * Ошибка при `silent` обязана улететь наверх: увести экран в 'error'
   * нельзя (за полноэкранным отказом спрячется уже загруженная лента),
   * проглотить молча — тем более. Её показывает полоска жеста.
   */
  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setStatus('loading');
      setError('');
    }
    try {
      // Карта целиком, а не один id: имя нужно шапке чата, и оно уже приехало
      // в этом же ответе — второй запрос за ним был бы лишним.
      const chart = await resolvePrimaryChart();
      const id = chart?.id || null;
      if (!id) {
        setStatus('no-chart');
        onChartResolved?.(null);
        return;
      }
      // Держим id в состоянии: он нужен панели события для разбора транзита
      // (POST /chart/{id}/transits/event/interpret). Второго запроса за ним не
      // делаем — он уже получен здесь.
      setChartId(id);
      // Наверх, в TabShell: кнопка чата открывает диалог по карте ТОЙ вкладки,
      // с которой её нажали, а не по основной.
      onChartResolved?.({ id, name: chart.name });
      const data = await fetchFeed(id, feedWindow());
      setFeed(data);
      setStatus('ready');
    } catch (err) {
      if (silent) throw err;
      // Текст уже человеческий: feedApi подменяет и «Chart not found»,
      // и сетевой сбой. Сюда попадает то, что можно показать как есть.
      setError(err?.message || 'Не удалось загрузить ленту.');
      setStatus('error');
    }
    // ⚠️ onChartResolved обязан быть стабильным у вызывающего (в TabShell он
    // useCallback с пустыми зависимостями): иначе смена его identity меняет
    // identity load, а на неё завязан useEffect ниже — лента перезагружалась
    // бы на каждом рендере родителя.
  }, [onChartResolved]);

  useEffect(() => { load(); }, [load]);

  /**
   * Перезагрузка после того, как на вкладке «Карта» построили новую карту
   * (SPEC_CHART_CREATE.md §6). Счётчик приходит из TabShell — экраны друг о
   * друге не знают, а связать их размонтированием нельзя: `load()` выше
   * зовётся только на монтировании, а вкладки смонтированы всегда.
   *
   * ⚠️ Обычный путь, НЕ `silent`, в отличие от жеста: карта сменилась
   * целиком, и сохранять прокрутку тут не только незачем, но и вредно —
   * позиция относилась к событиям другой карты. Скелет здесь честен.
   *
   * ⚠️ Первое значение счётчика пропускается: без этого эффект сработал бы
   * на монтировании и продублировал бы первую загрузку — тот самый лишний
   * запрос в залпе холодного старта, от которого лечили гейтом по сроку
   * токена.
   */
  const seenChartsVersion = useRef(chartsVersion);
  useEffect(() => {
    if (seenChartsVersion.current === chartsVersion) return;
    seenChartsVersion.current = chartsVersion;
    load();
  }, [chartsVersion, load]);

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

  // Жест обновления. Гейт по `active` обязателен: все три экрана
  // смонтированы одновременно и делят ОДИН скроллер (TabShell.jsx) — без
  // него потягивание на «Карте» или «Ещё» обновляло бы ленту.
  //
  // `days.length` в условии — не перестраховка: на состояниях без списка
  // (скелет, ошибка, «нет карты», пустое окно) полоска жеста не
  // отрисована вовсе, и жест сработал бы вслепую — данные обновились бы,
  // а человек не увидел бы ни ожидания, ни отказа. Там для этого уже есть
  // свои кнопки «Повторить»/«Обновить».
  const refresh = useCallback(() => load({ silent: true }), [load]);
  const pull = usePullToRefresh(
    scrollRef,
    refresh,
    active && status === 'ready' && days.length > 0,
  );

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

  // Подсказки — только когда лента и правда есть что показать: одного
  // status === 'ready' мало, при пустом окне подсвечивать нечего
  // (SPEC_ONBOARDING.md §9).
  const hints = useHints('feed', active && status === 'ready' && days.length > 0);

  // Компактная полоска включается, когда развёрнутая ушла за верх. Гейт по
  // `active` обязателен, как и у жеста обновления: все три экрана
  // смонтированы одновременно и делят один скроллер, и без него полоска
  // ленты висела бы поверх «Карты» и «Ещё».
  const compactNow = useCompactNow(
    scrollRef,
    nowStripRef,
    active && status === 'ready' && days.length > 0,
  );
  // Кнопка «Сегодня» в компактной полосе. Ведёт к тому же дню, на котором
  // лента открывается (§10): к сегодняшнему, а если событий сегодня нет — к
  // ближайшему следующему. Второго правила «что такое сегодня» здесь не
  // заводится — берётся тот же anchorDate, что и при открытии.
  const goToday = useCallback(() => {
    userMovedRef.current = true;
    dayRefs.current.get(anchorDateRef.current)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, []);

  useEffect(() => {
    onHintsToggle?.('feed', hints.open);
  }, [onHintsToggle, hints.open]);

  /**
   * Любая прокрутка сворачивает развёрнутую шапку — в ОБЕ стороны (решение
   * владельца 16.09.2026).
   *
   * ⚠️ Порог в 24 px обязателен. Тап по ленте на телефоне почти всегда даёт
   * микропрокрутку в несколько пикселей, и без порога шапка схлопывалась бы
   * от касания, которым человек её только что открыл.
   *
   * ⚠️ Сравнение идёт с положением НА МОМЕНТ открытия, а не с предыдущим
   * кадром: иначе медленная прокрутка на сотню пикселей по 3-5 px за событие
   * не пересекла бы порог ни разу.
   *
   * ⚠️ Возврат на вкладку снова разворачивает шапку — то же состояние, что
   * при открытии ленты. Это тот же эффект, поэтому второго правила «что
   * такое открытие» не заводится.
   */
  useEffect(() => {
    if (!active) return undefined;
    setHeaderOpen(true);
    // Новый вход на вкладку — умолчания вернулись: сегодняшний период снова
    // раскрыт, остальные свёрнуты. Внутри одного посещения состояние
    // сохраняется, в том числе через обновление ленты.
    setFlippedPeriods(new Set());
    const el = scrollRef?.current;
    if (!el) return undefined;
    const from = el.scrollTop;
    const onScroll = () => {
      if (Math.abs(el.scrollTop - from) > HEADER_COLLAPSE_PX) setHeaderOpen(false);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, [active, scrollRef]);

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
    return (
      <CenteredNotice
        title="Не удалось загрузить ленту"
        text={error}
        action="Повторить"
        onAction={load}
        secondary="Войти заново"
        onSecondary={logout}
      />
    );
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

  /**
   * Шапка ленты — одно содержимое на два места: в начале списка (при открытии
   * она развёрнута) и внутри липкой полосы, куда её разворачивает стрелка.
   *
   * ⚠️ Функция, а не переменная, и не второй экземпляр компонентов: в потоке
   * шапка несёт кнопку подсказки и якорь онбординга (`chipsRef`), а в оверлее
   * они не нужны — двойной якорь увёл бы подсветку подсказки на невидимую
   * копию. `inFlow` и отвечает ровно за это различие; всё остальное —
   * буквально один и тот же JSX, иначе «развёрнутая шапка» разъехалась бы с
   * той, что человек видит при открытии.
   */
  const headerContent = (inFlow) => (
    <>
      <FeedNowStrip
        events={allEvents}
        today={today}
        onHelp={inFlow ? hints.show : undefined}
        chipsRef={inFlow ? chipsRef : undefined}
        onOpen={setSelected}
      />
      <FeedDayStrip
        from={feed?.horizon?.from}
        to={feed?.horizon?.to}
        today={today}
        dotsByDay={dotsByDay}
        onSelectDay={(date) => { setHeaderOpen(false); scrollToDay(date); }}
      />
    </>
  );

  // Якорь открытия: сегодняшний день, а если событий сегодня нет — первый
  // день после сегодняшнего (§10). Ищется один раз на список, а не в цикле
  // отрисовки, чтобы ref достался ровно одному заголовку. Само правило — в
  // lib/feedAnchor.js: внутри рендера его нечем было проверить отдельно от
  // прокрутки, а на приёмке 16.09.2026 разбирать пришлось именно это.
  const anchorDate = pickAnchorDate(days, today);
  anchorDateRef.current = anchorDate;

  return (
    <div style={PAGE_PADDING}>
      <PullIndicator state={pull.state} ready={pull.ready} innerRef={pull.indicatorRef} />
      {/* Полоса «сейчас» — вне прокрутки потока по §3, но внутри общего
          скроллера: прибивать её к верху экрана спецификация не просит, а
          за состоянием «сейчас» при прокрутке следит компактная строка. */}
      {/* Полоска поверх потока — вне прокрутки (position: fixed), поэтому
          стоит рядом с полосой, а не внутри неё: она ничего не занимает в
          раскладке и её появление не двигает содержимое. */}
      <FeedNowCompact
        events={allEvents}
        today={today}
        visible={compactNow}
        onGoToday={goToday}
        onOpen={setSelected}
        header={headerContent(false)}
        /* ⚠️ Оверлей только когда потоковая шапка ушла за верх. Иначе, стоя в
           самом начале ленты, человек увидел бы ДВЕ шапки сразу: настоящую и
           её копию поверх. */
        expanded={headerOpen && compactNow}
        onToggleHeader={() => setHeaderOpen((v) => !v)}
      />
      <div ref={nowStripRef}>{headerContent(true)}</div>

      {days.map((day, dayIndex) => {
        // Порядок внутри дня — строго по времени; под свёртку уходит только
        // лунный фон, и только когда его два и больше. Правило целиком и
        // разбор дефекта приёмки — в lib/feedDayOrder.js.
        const { inFlow, folded: foldedLunar } = splitDayEvents(day);
        const foreground = inFlow.filter((e) => !isLunarBackground(e));
        // Раскрыт ровно ОДИН день, и это тот же день, на котором лента
        // открывается (§10). Обычно это сегодня; если событий сегодня нет —
        // ближайший следующий, иначе экран открылся бы на сжатом дне и
        // обещание «раскрыт сегодняшний» не выполнялось бы ни для кого, у
        // кого сегодня пусто (68 дней из 148 в боевой выдаче — без карточек).
        const expanded = day.date === anchorDate;
        // Блок пропорционален содержанию: у дня, где кроме лунного фона
        // ничего нет, заголовок не тянет за собой пустой отступ.
        const quiet = !expanded && foreground.length === 0;
        const surface = expanded ? 'var(--bg-card)' : 'var(--bg-dot)';

        const eventNode = (event, { compact, quiet: quietRow = false }) => {
          const major = isMajorEvent(event);
          // ⚠️ У ВСЕХ периодов в колонке слева ВРЕМЯ начала, того же кегля и
          // веса, что у транзитов (приёмка 16.09.2026). Дата там была у
          // месячного периода и дублировала заголовок дня, под которым он и
          // стоит: «14.09» в колонке под шапкой «14 сентября». Разный вид
          // колонки у соседних строк одного дня читался как разные сорта
          // данных, а сорт один — момент события.
          const isPlannerPeriod = event.kind === 'planner_period'
            || event.kind === 'planner_moon_house'
            || event.kind === 'planner_longterm';
          // Периоды планера: в несегодняшнем дне свёрнуты, тапом
          // раскрываются на месте (решение владельца 16.09.2026, исключение
          // из §5 — записано в DESIGN_SYSTEM).
          const periodCollapsed = isPlannerPeriod
            && (!expanded) !== flippedPeriods.has(event.key);
          return (
            <FeedTimelineNode
              key={event.key}
              time={timePart(event.at)}
              /*
               * ⚠️ Вес времени задаёт ДЕНЬ, и только он.
               *
               * `compact` для этого не годится, хотя и выглядит подходящим:
               * он означает «рисовать строкой, а не карточкой», а крупное
               * событие (feedRank.js) остаётся карточкой и в сжатом дне.
               * Из-за этого в одном и том же дне период Меркурия получал
               * жирное время, а проход Луны рядом — бледное: третья приёмка
               * 16.09.2026, «05:52 жирное, 22:02 бледное».
               */
              bold={expanded}
              color={dotColor(event)}
              solid={isPlannerPeriod}
              size={compact && !isPlannerPeriod ? 9 : dotSize(event)}
              gap={compact ? 6 : 12}
              dense={compact}
              quiet={quietRow}
              fill={surface}
            >
              {compact && !isPlannerPeriod
                ? <FeedEventRow event={event} onOpen={setSelected} quiet={quietRow} />
                : (
                  <FeedEventCard
                    event={event}
                    onOpen={setSelected}
                    major={major}
                    collapsed={periodCollapsed}
                    onToggle={isPlannerPeriod ? togglePeriod : undefined}
                  />
                )}
            </FeedTimelineNode>
          );
        };

        return (
          <section
            key={day.date}
            ref={(el) => {
              if (el) dayRefs.current.set(day.date, el); else dayRefs.current.delete(day.date);
              if (day.date === anchorDate) anchorRef.current = el;
            }}
            style={expanded ? {
              // Раскрытый день — единственная поднятая поверхность ленты:
              // по ней его и находят глазами, не вчитываясь в даты.
              marginTop: 26,
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-xl)',
              boxShadow: 'var(--shadow-card)',
              // ⚠️ Боковые поля СНЯТЫ (приёмка 16.09.2026): внутри карточки
              // дня стоят карточки периодов со своей рамкой, и два набора
              // полей подряд съедали ширину у расшифровки — «карточка в
              // карточке». Верх и низ остались: они отделяют заголовок дня и
              // последнюю строку от края поднятой поверхности.
              // 6px, а не 0: при нуле время слева упиралось в саму рамку
              // карточки дня — на снимке между ними оставалось 4 px, и это
              // читалось как склейка, а не как поле.
              padding: '14px 6px 8px',
            } : undefined}
          >
            <FeedDayHeader
              date={day.date}
              today={today}
              first={dayIndex === 0}
              quiet={quiet}
              boundary={!expanded}
            />
            {/* Сжатый день меняет ОБЪЁМ события, а не доступ к нему: строка
                открывает ту же панель, что и карточка. Крупное (feedRank.js)
                карточкой остаётся всегда — в том числе открытый разбор, ради
                которого на free ленту и открывают. */}
            {/* Одиночное лунное идёт здесь же, по своему времени (решение
                владельца 16.09.2026). Видом оно остаётся ФОНОМ: строкой, а не
                карточкой, и приглушённым вместе со своим днём — менялось
                только МЕСТО, не вид. */}
            {inFlow.map((event) => {
              const lunar = isLunarBackground(event);
              return eventNode(event, {
                compact: lunar || (!expanded && !isMajorEvent(event)),
                quiet: lunar && !expanded,
              });
            })}
            {foldedLunar.length > 0 && (
              <FeedTimelineNode time="" gap={16} fill={surface}>
                <FeedLunarFold events={foldedLunar} onOpen={setSelected} quiet={!expanded} />
              </FeedTimelineNode>
            )}
          </section>
        );
      })}

      <FeedHorizonCard horizon={feed?.horizon} />

      <FeedEventPanel event={selected} chartId={chartId} onClose={() => setSelected(null)} />

      {hints.open && (
        <HintOverlay
          steps={FEED_HINTS}
          anchors={{ timeline: anchorRef, houseChips: chipsRef, card: anchorRef }}
          onClose={hints.close}
        />
      )}
    </div>
  );
}
