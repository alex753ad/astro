/**
 * localNotificationPlan.test.js — замок на границу «клиент склеивает список,
 * но не сочиняет текст» (решение владельца 10.09.2026, docs/HISTORY-push.md).
 *
 * ⚠️ Проверки вида «ни один элемент плана не нарушает правило» разряжаются
 * молча: на пустом плане они зелёные, потому что проверять стало нечего.
 * Ровно так уже разряжался `TestNoDatesInNotificationText` на бэкенде, и
 * лечение здесь то же — рядом с каждой такой проверкой стоит assert, что в
 * выборку попал нужный ВИД элемента (день с несколькими событиями; день с
 * одним). Без него тест ниже проходил бы на `buildPlan([])`.
 */
import { describe, expect, it } from 'vitest';
import {
  QUIET_MARGIN_MINUTES,
  allowedAt,
  applyQuietMargin,
  buildPlan,
  hhmmInZone,
  isAllowedMoment,
  notificationId,
} from './localNotificationPlan';

const NOW = Date.parse('2026-09-13T05:00:00+03:00');

const DAY1 = '2026-09-14T08:00:00+03:00';
const DAY2 = '2026-09-15T08:00:00+03:00';

/** Форма ответа `GET /api/v1/push/upcoming` (backend/push/cron.py, collect_upcoming). */
const EVENTS = [
  { key: 'transit:saturn:square:sun:2026-09-14', kind: 'transit', at: DAY1,
    title: '♄ Сатурн в квадрате к Солнцу', body: 'Проверка на прочность там, где вы давно знаете слабое место.', url: '/planner' },
  { key: 'moon:moon:full_moon:2026-09-14', kind: 'moon', at: DAY1,
    title: '🌕 Полнолуние завтра', body: 'Хорошее время заметить, что вы на самом деле чувствуете.', url: '/lunar' },
  { key: 'daily:2026-09-15', kind: 'daily', at: DAY2,
    title: '✦ Прогноз дня', body: 'Загляните, что происходит сегодня.', url: '/feed' },
];

describe('target — куда вести по нажатию', () => {
  it('ежедневный прогноз несёт target до уведомления, остальные — null', () => {
    const events = [
      ...EVENTS.slice(0, 2),
      { ...EVENTS[2], target: 'feed_today' },
    ];
    const plan = buildPlan(events, NOW);
    const daily = plan.find((p) => p.keys.includes('daily:2026-09-15'));
    const other = plan.find((p) => !p.keys.includes('daily:2026-09-15'));
    expect(daily.target).toBe('feed_today');
    expect(other.target).toBeNull();
  });

  it('в склейке target не теряется, даже если ежедневный не первый', () => {
    const plan = buildPlan([
      EVENTS[0],
      { ...EVENTS[2], at: DAY1, target: 'feed_today' },
    ], NOW);
    expect(plan).toHaveLength(1);
    expect(plan[0].target).toBe('feed_today');
  });
});

describe('склейка событий одного дня', () => {
  it('день с несколькими событиями даёт ОДНО уведомление, день с одним — одно', () => {
    const plan = buildPlan(EVENTS, NOW);
    expect(plan).toHaveLength(2);
    expect(plan[0].at).toBe(DAY1);
    expect(plan[0].keys).toHaveLength(2);
    expect(plan[1].keys).toHaveLength(1);
  });

  it('в склейке нет ни одного слова, которого не прислал сервер', () => {
    const plan = buildPlan(EVENTS, NOW);

    // ⚠️ Без этой проверки весь тест ниже разряжается: на плане без склеенных
    // дней «ни один текст не содержит своих слов» верно бессодержательно.
    const glued = plan.filter((p) => p.keys.length > 1);
    expect(glued.length, 'в выборке нет ни одного склеенного дня').toBeGreaterThan(0);

    const serverStrings = new Set(EVENTS.flatMap((e) => [e.title, e.body]));
    for (const item of glued) {
      // Разбираем текст обратно на куски по разделителям, которые добавляет
      // клиент. Каждый кусок обязан быть серверной строкой дословно.
      const pieces = [item.title, ...item.body.split('\n').flatMap((l) => l.split(' · '))];
      for (const piece of pieces) {
        expect(serverStrings.has(piece), `клиент сочинил текст: ${piece}`).toBe(true);
      }
    }
  });

  it('одиночное событие идёт текстом сервера дословно, без разделителей', () => {
    const plan = buildPlan(EVENTS, NOW);
    const single = plan.filter((p) => p.keys.length === 1);
    expect(single.length, 'в выборке нет ни одного дня с одним событием').toBeGreaterThan(0);
    expect(single[0].title).toBe(EVENTS[2].title);
    expect(single[0].body).toBe(EVENTS[2].body);
  });

  it('порядок внутри дня серверный: заголовок берётся у первого события', () => {
    const plan = buildPlan(EVENTS, NOW);
    expect(plan[0].title).toBe(EVENTS[0].title);
    expect(plan[0].body.startsWith(EVENTS[0].body)).toBe(true);
    expect(plan[0].body).toContain(EVENTS[1].title);
  });
});

describe('дедуп и отсев', () => {
  it('повтор того же key в выдаче не даёт второго уведомления', () => {
    const plan = buildPlan([...EVENTS, EVENTS[2]], NOW);
    expect(plan).toHaveLength(2);
    expect(plan[1].keys).toEqual([EVENTS[2].key]);
  });

  it('прошедшее время не планируется', () => {
    const past = { ...EVENTS[2], key: 'daily:2026-09-12', at: '2026-09-12T08:00:00+03:00' };
    const plan = buildPlan([past, ...EVENTS], NOW);
    expect(plan.flatMap((p) => p.keys)).not.toContain(past.key);
  });

  it('битые записи пропускаются, остальные планируются', () => {
    const plan = buildPlan([{ key: 'x' }, { at: DAY1 }, null, ...EVENTS], NOW);
    expect(plan).toHaveLength(2);
  });

  it('пустая выдача даёт пустой план, а не падение', () => {
    expect(buildPlan([], NOW)).toEqual([]);
    expect(buildPlan(undefined, NOW)).toEqual([]);
  });
});

describe('id уведомления', () => {
  it('устойчив между вызовами — на этом держится замена вместо дубля', () => {
    expect(notificationId('transit:a:b')).toBe(notificationId('transit:a:b'));
  });

  it('целый, положительный и влезает в Java int', () => {
    for (const e of EVENTS) {
      const id = notificationId(e.key);
      expect(Number.isInteger(id)).toBe(true);
      expect(id).toBeGreaterThanOrEqual(0);
      expect(id).toBeLessThan(0x7fffffff);
    }
  });

  it('разные ключи дают разные id', () => {
    const ids = new Set(EVENTS.map((e) => notificationId(e.key)));
    expect(ids.size).toBe(EVENTS.length);
  });
});

/**
 * Запас у верхней границы окна (решение владельца 13.09.2026, 45 минут).
 *
 * ⚠️ Проверки вида «ни одно время в плане не нарушает окно» разряжаются молча:
 * на выборке, где в запас никто не попал, они зелёные, потому что проверять
 * нечего. Поэтому рядом с каждой стоит assert, что нужный ВИД элемента в
 * выборку попал — событие в запасе, событие вне окна, событие без следующего
 * слота. Та же болезнь и то же лечение, что у `TestNoDatesInNotificationText`
 * на бэкенде.
 */
const TZ = 'Europe/Moscow';

/** Слоты приходят с сервера: по одному на день, все на нижней границе окна. */
const SLOTS = [
  '2026-09-14T08:00:00+03:00',
  '2026-09-15T08:00:00+03:00',
  '2026-09-16T08:00:00+03:00',
];

const WIN = { dailyTime: '08:00', quietFrom: '22:00', timeZone: TZ, slots: SLOTS };

const evt = (key, at) => ({ key, kind: 'transit', at, title: 'т', body: 'б', url: '/feed' });

describe('границы окна с запасом', () => {
  it('нижняя граница без запаса: ровно daily_time уже можно', () => {
    expect(isAllowedMoment(new Date('2026-09-14T08:00:00+03:00'), WIN)).toBe(true);
    expect(isAllowedMoment(new Date('2026-09-14T07:59:00+03:00'), WIN)).toBe(false);
  });

  it('верхняя граница с запасом: 21:14 можно, 21:15 уже нет', () => {
    expect(isAllowedMoment(new Date('2026-09-14T21:14:00+03:00'), WIN)).toBe(true);
    expect(isAllowedMoment(new Date('2026-09-14T21:15:00+03:00'), WIN)).toBe(false);
  });

  it('запас равен объявленной константе, а не случайному числу', () => {
    expect(QUIET_MARGIN_MINUTES).toBe(45);
    const end = 22 * 60;
    const lastAllowed = end - QUIET_MARGIN_MINUTES - 1; // 21:14
    expect(isAllowedMoment(new Date('2026-09-14T21:14:00+03:00'), WIN)).toBe(true);
    expect(lastAllowed).toBe(21 * 60 + 14);
  });

  it('окно считается в поясе КАРТЫ, а не устройства', () => {
    // 19:30 UTC — это 22:30 в Москве, то есть уже тихие часы.
    const moment = new Date('2026-09-14T19:30:00Z');
    expect(isAllowedMoment(moment, WIN)).toBe(false);
    expect(isAllowedMoment(moment, { ...WIN, timeZone: 'UTC' })).toBe(true);
    expect(hhmmInZone(moment, TZ)).toEqual([22, 30]);
  });

  it('бессмысленная пара границ: верхней границы нет, а не пустое окно', () => {
    const broken = { ...WIN, dailyTime: '08:00', quietFrom: '06:00' };
    expect(isAllowedMoment(new Date('2026-09-14T23:45:00+03:00'), broken)).toBe(true);
  });

  it('окно короче запаса — запас не применяется вовсе', () => {
    // 21:30–22:00: полчаса, меньше 45 минут запаса. Иначе в запас попали бы
    // ВСЕ слоты разом и уведомления исчезли бы совсем.
    const narrow = { ...WIN, dailyTime: '21:30', quietFrom: '22:00' };
    expect(isAllowedMoment(new Date('2026-09-14T21:35:00+03:00'), narrow)).toBe(true);
  });
});

describe('перенос на следующий присланный слот', () => {
  it('событие в запасе переезжает на следующий слот, а не отбрасывается', () => {
    const late = evt('k1', '2026-09-14T21:50:00+03:00');
    const { events, moved, late: lost } = applyQuietMargin([late], WIN);

    expect(moved, 'в выборке нет ни одного события, попавшего в запас').toBe(1);
    expect(lost).toBe(0);
    expect(events).toHaveLength(1);
    expect(events[0].at).toBe(SLOTS[1]); // 15.09, 08:00 — следующий после 14.09 21:50
  });

  it('время берётся из выдачи ДОСЛОВНО, ни одно не собрано клиентом', () => {
    const mixed = [
      evt('k1', '2026-09-14T21:50:00+03:00'), // в запасе — переедет
      evt('k2', SLOTS[0]),                    // на слоте — останется
    ];
    const { events, moved } = applyQuietMargin(mixed, WIN);

    expect(moved, 'в выборке нет ни одного переноса').toBeGreaterThan(0);
    const original = new Set([...SLOTS, ...mixed.map((e) => e.at)]);
    for (const e of events) {
      expect(original.has(e.at), `клиент собрал своё время: ${e.at}`).toBe(true);
    }
  });

  it('переехавшее склеивается с тем, что уже стоит на слоте, а не дублирует минуту', () => {
    const both = [
      evt('k1', '2026-09-14T21:50:00+03:00'),
      evt('k2', SLOTS[1]),
    ];
    const { events } = applyQuietMargin(both, WIN);
    const plan = buildPlan(events, Date.parse('2026-09-13T05:00:00+03:00'));

    // Одно уведомление, а не два в одну минуту — ради этого запас и применяется
    // к СОБЫТИЯМ до склейки, а не к готовому плану.
    expect(plan).toHaveLength(1);
    // Порядок внутри дня остаётся серверным: переехавшее событие пришло в
    // выдаче раньше, значит и в склейке идёт раньше. Переставить его в конец
    // было бы собственным суждением клиента о важности — тем самым вторым
    // критерием отбора, которого в клиенте быть не должно.
    expect(plan[0].keys).toEqual(['k1', 'k2']);
  });

  it('следующего слота нет — событие остаётся на месте и помечено, а не теряется', () => {
    const last = evt('k1', '2026-09-16T21:50:00+03:00'); // после последнего слота
    const { events, moved, late } = applyQuietMargin([last], WIN);

    expect(late, 'в выборке нет ни одного события без следующего слота').toBe(1);
    expect(moved).toBe(0);
    expect(events[0].at).toBe(last.at);
  });

  it('без границ окна не двигаем ничего — догадываться нельзя', () => {
    const late = evt('k1', '2026-09-14T21:50:00+03:00');
    expect(applyQuietMargin([late], null).events[0].at).toBe(late.at);
    expect(allowedAt(late.at, null)).toBe(late.at);
  });

  it('боевые слоты стоят на нижней границе и не двигаются никогда', () => {
    const onSlots = SLOTS.map((at, i) => evt(`k${i}`, at));
    const { moved, late } = applyQuietMargin(onSlots, WIN);
    expect(moved).toBe(0);
    expect(late).toBe(0);
  });
});
