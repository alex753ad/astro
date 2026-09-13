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
import { buildPlan, notificationId } from './localNotificationPlan';

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
