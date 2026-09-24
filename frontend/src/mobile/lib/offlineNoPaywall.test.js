/**
 * offlineNoPaywall.test.js — платный без сети не видит пейволла.
 *
 * Решение владельца 24.09.2026: без сети тариф для доступа неизвестен
 * (`known: false`), и «неизвестен» не включает ни пейволла, ни размытия, ни
 * приписок «оформи тариф». Сохранённое показывается так, как было получено.
 *
 * Проверяется каждое место, где тариф решает, что показать: кнопка чата,
 * панель события планера, приписка под разбором, карточка горизонта ленты.
 * Размытие (BlurredHint) решает не тариф, а серверный `event.locked` —
 * у платного в сохранённой ленте его нет, и ниже это тоже закреплено.
 */
import { describe, expect, it } from 'vitest';
import { chatAccessFrom } from './useChatAccess';
import { lockedPlannerText, upgradeOpensIt } from './plannerAccess';
import { upsellForTier } from './interpretRules';
import { trimFeed } from './offlineCache';

describe('тариф неизвестен (нет сети) — пейволла нет нигде', () => {
  it('кнопка чата: не замок, а «неизвестно» — кнопки нет', () => {
    expect(chatAccessFrom(null)).toBeNull();
    // и для сравнения: известный free — замок, известная Лира — чат
    expect(chatAccessFrom({ tier: 'free', features: { rag_chat: false } })).toBe(false);
    expect(chatAccessFrom({ tier: 'pro', features: { rag_chat: true } })).toBe(true);
  });

  it('панель события планера: ни «Открыть доступ», ни текста апселла', () => {
    for (const kind of ['planner_moon_house', 'planner_period', 'planner_longterm']) {
      const ev = { kind, locked: true };
      expect(upgradeOpensIt(ev, null, false)).toBe(false);
      expect(lockedPlannerText(ev, null, false)).toBe('');
    }
  });

  it('разбор: приписки нет', () => {
    expect(upsellForTier({ tier: null, known: false, finished: true, failed: false })).toBeNull();
  });

  it('сохранённая лента: карточки «Открывается на …» нет', () => {
    const feed = {
      horizon: { from: '2026-09-01', to: '2027-03-01', next_tier: { to: '2027-09-01', name: 'Орион' } },
      events: [{ kind: 'planner_period', at: '2026-09-24T10:00:00+03:00', ends_at: null, locked: false }],
    };
    const cached = trimFeed(feed, '2026-09-24');
    expect(cached.horizon.next_tier).toBeUndefined();
    // события сохраняются как пришли: у платного `locked: false` — без размытия
    expect(cached.events[0].locked).toBe(false);
  });
});
