import { describe, expect, it, vi } from 'vitest';

import { createSubscriptionSource } from './subscriptionSource';

/**
 * subscriptionSource.test.js — общая машинерия живого тарифа.
 *
 * ⚠️ Ради чего она существует. `user.tier` из `useAuth` обновляется только
 * вместе с токеном, то есть до 15 минут показывает старое значение. В
 * приложении из-за этого платящему предлагали купить то, что у него есть; на
 * вебе через `userTier` устаревает ещё и ВИТРИНА транзитов — человек,
 * оплативший Лиру, до четверти часа видел горизонт бесплатного тарифа.
 *
 * ⚠️ Второе, что здесь стережётся, — отсутствие залпа. В приложении три
 * экрана монтируются разом, и залп уже был причиной гейта по сроку токена
 * (CLAUDE.md). Поэтому проверяется, что N потребителей дают ОДИН запрос.
 *
 * Привязки к платформам (`mobile/lib/tierSource.js`, `lib/webTier.js`)
 * отличаются одной строкой — как именно спрашивать сервер; всё остальное
 * здесь и проверяется здесь.
 */

const READY = { tier: 'pro', features: { rag_chat: true } };

describe('дедупликация и кэш', () => {
  it('три одновременных потребителя дают ОДИН запрос', async () => {
    const fetcher = vi.fn().mockResolvedValue(READY);
    const s = createSubscriptionSource(fetcher);

    await Promise.all([s.getSubscription(), s.getSubscription(), s.getSubscription()]);

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('повторное обращение запроса не делает', async () => {
    const fetcher = vi.fn().mockResolvedValue(READY);
    const s = createSubscriptionSource(fetcher);

    await s.getSubscription();
    await s.getSubscription();

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('force игнорирует кэш — жест обновления обязан приносить новое', async () => {
    const fetcher = vi.fn().mockResolvedValue(READY);
    const s = createSubscriptionSource(fetcher);

    await s.getSubscription();
    await s.getSubscription({ force: true });

    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('свежий тариф вытесняет прежний', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce({ tier: 'free' })
      .mockResolvedValueOnce({ tier: 'pro' });
    const s = createSubscriptionSource(fetcher);

    await s.getSubscription();
    expect(s.peekSubscription().tier).toBe('free');

    await s.getSubscription({ force: true });
    expect(s.peekSubscription().tier).toBe('pro');
  });
});

describe('неуспех не оставляет источник сломанным', () => {
  it('ошибка пробрасывается, но следующий запрос возможен', async () => {
    const fetcher = vi.fn()
      .mockRejectedValueOnce(new Error('сеть'))
      .mockResolvedValueOnce(READY);
    const s = createSubscriptionSource(fetcher);

    await expect(s.getSubscription()).rejects.toThrow('сеть');
    // Незавершённый промис не должен залипнуть: иначе один сбой сети выключил
    // бы живой тариф до перезапуска — тот же класс, что refreshInFlight.
    await expect(s.getSubscription()).resolves.toEqual(READY);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('после ошибки кэш пуст — старого значения не выдумываем', async () => {
    const s = createSubscriptionSource(vi.fn().mockRejectedValue(new Error('x')));
    await s.getSubscription().catch(() => {});
    expect(s.peekSubscription()).toBeNull();
  });

  it('синхронное исключение фетчера тоже становится отказом, а не падением', async () => {
    const s = createSubscriptionSource(() => { throw new Error('сразу'); });
    await expect(s.getSubscription()).rejects.toThrow('сразу');
  });
});

describe('подписка', () => {
  it('готовый ответ отдаётся сразу при подписке', async () => {
    const s = createSubscriptionSource(vi.fn().mockResolvedValue(READY));
    await s.getSubscription();

    const seen = [];
    const off = s.onSubscription((d) => seen.push(d?.tier));

    expect(seen).toEqual(['pro']);
    off();
  });

  it('отписавшийся обновлений не получает', async () => {
    const s = createSubscriptionSource(vi.fn().mockResolvedValue(READY));
    const seen = [];
    const off = s.onSubscription((d) => seen.push(d?.tier));
    off();

    await s.getSubscription();

    expect(seen).toEqual([]);
  });
});

describe('сброс при выходе', () => {
  it('стирает тариф — иначе следующий вошедший увидит чужой', async () => {
    const s = createSubscriptionSource(vi.fn().mockResolvedValue(READY));
    await s.getSubscription();
    expect(s.peekSubscription().tier).toBe('pro');

    s.resetSubscription();

    expect(s.peekSubscription()).toBeNull();
  });

  it('после сброса запрос идёт заново', async () => {
    const fetcher = vi.fn().mockResolvedValue(READY);
    const s = createSubscriptionSource(fetcher);

    await s.getSubscription();
    s.resetSubscription();
    await s.getSubscription();

    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});

describe('два экземпляра не делят состояние', () => {
  it('веб и приложение не мешают друг другу', async () => {
    // Привязки создают по своему экземпляру: у них разные способы запроса, и
    // общий кэш означал бы, что ответ одного транспорта выдаётся за ответ
    // другого.
    const a = createSubscriptionSource(vi.fn().mockResolvedValue({ tier: 'free' }));
    const b = createSubscriptionSource(vi.fn().mockResolvedValue({ tier: 'pro' }));

    await a.getSubscription();

    expect(a.peekSubscription().tier).toBe('free');
    expect(b.peekSubscription()).toBeNull();
  });
});
