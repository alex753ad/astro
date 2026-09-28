import { describe, expect, it } from 'vitest';
import { featureOfEvent, returnAfterPay } from './afterPay';

describe('куда вернуться после оплаты', () => {
  const period = { path: '/app/feed', kind: 'event', key: 'planner:mars:1', feature: 'planner_period' };
  const longterm = { path: '/app/feed', kind: 'event', key: 'lt:saturn', feature: 'planner_longterm' };
  const chat = { path: '/app/chart', kind: 'chat', feature: 'chat' };

  it('Вега открывает период — вернуться и открыть', () => {
    expect(returnAfterPay(period, 'lite')).toEqual({ path: '/app/feed', open: { kind: 'event', key: 'planner:mars:1' } });
  });

  it('Вега не открывает долгосрочный — вернуться, но не открывать', () => {
    expect(returnAfterPay(longterm, 'lite')).toEqual({ path: '/app/feed', open: null });
    expect(returnAfterPay(longterm, 'pro').open).toEqual({ kind: 'event', key: 'lt:saturn' });
  });

  it('чат: после пробных Вега открывает (30 в месяц), после лимита Веги — только Лира', () => {
    expect(returnAfterPay(chat, 'lite')).toEqual({ path: '/app/chart', open: { kind: 'chat' } });
    const limit = { ...chat, feature: 'chat_limit' };
    expect(returnAfterPay(limit, 'lite').open).toBeNull();
    expect(returnAfterPay(limit, 'pro').open).toEqual({ kind: 'chat' });
  });

  it('транзит: Вега открывает разбор, лимит — только Лира', () => {
    const t = { path: '/app/feed', kind: 'event', key: 't1', feature: 'transit' };
    expect(returnAfterPay(t, 'lite').open).toEqual({ kind: 'event', key: 't1' });
    expect(returnAfterPay({ ...t, feature: 'transit_limit' }, 'lite').open).toBeNull();
  });

  it('оплата не из элемента (карточка тарифа) — никуда не уводить', () => {
    expect(returnAfterPay(null, 'pro')).toEqual({ path: null, open: null });
    expect(returnAfterPay({ path: '/app/more' }, 'pro')).toEqual({ path: '/app/more', open: null });
  });

  it('виды событий ленты', () => {
    expect(featureOfEvent({ kind: 'planner_moon_house' })).toBe('planner_moon');
    expect(featureOfEvent({ kind: 'planner_period' })).toBe('planner_period');
    expect(featureOfEvent({ kind: 'moon_phase' })).toBeNull();
  });
});

// Рендер-тестов нет — связь с экраном по исходнику.
describe('кнопка «Открыть доступ» в ленте', async () => {
  const { readFileSync } = await import('node:fs');
  const { fileURLToPath } = await import('node:url');
  const src = readFileSync(fileURLToPath(new URL('../screens/FeedScreen.jsx', import.meta.url)), 'utf-8');
  it('лента передаёт обработчик — кнопка не выключена', () => {
    expect(src).toMatch(/<FeedEventPanel .*onUpgrade=\{upgrade\}/);
  });
});
