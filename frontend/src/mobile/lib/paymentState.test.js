import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MAX_POLLS, describePayment } from './paymentState';
import { PENDING_TTL_MS, clearPending, readPending, rememberPending } from './payApi';

describe('describePayment — каждое состояние отвечает про деньги', () => {
  it('ещё не ответил — ждём, и тариф включится сам', () => {
    const d = describePayment(null);
    expect(d.kind).toBe('wait');
    expect(d.done).toBe(false);
    expect(d.text).toMatch(/включится сам/);
  });

  it('успех — тариф и дата окончания', () => {
    const d = describePayment({ state: 'succeeded', tier: 'pro', active_until: '2026-10-24T10:00:00' });
    expect(d.kind).toBe('ok');
    expect(d.text).toBe('Тариф Лира включён до 24.10.2026.');
  });

  it('отказ — причина от банка и «деньги не списаны»', () => {
    const d = describePayment({ state: 'canceled', reason: 'На карте не хватило денег.' });
    expect(d.kind).toBe('fail');
    expect(d.text).toMatch(/не хватило денег/);
    expect(d.text).toMatch(/не списаны/);
  });

  it('деньги есть, начислить нельзя — не «ошибка», а «проверяем» и путь в поддержку', () => {
    const d = describePayment({ state: 'review' });
    expect(d.kind).toBe('later');
    expect(d.text).toMatch(/поддержку/);
  });

  it('без сети — не ошибка, проверим позже, деньги не пропадут', () => {
    const d = describePayment(null, { offline: true });
    expect(d.done).toBe(false);
    expect(d.text).toMatch(/не пропадут/);
  });

  it('долго нет ответа — перестаём ждать, но обещаем включение само', () => {
    const d = describePayment({ state: 'pending' }, { polls: MAX_POLLS });
    expect(d.done).toBe(true);
    expect(d.text).toMatch(/включится сам/);
  });

  it('нигде нет обращения на «вы»', () => {
    const all = [null, { state: 'succeeded', tier: 'lite' }, { state: 'canceled' }, { state: 'review' },
      { state: 'unknown' }].flatMap((s) => [describePayment(s), describePayment(s, { offline: true }),
      describePayment(s, { polls: MAX_POLLS })]);
    // Без \b: в JS он считает границы только по латинице, и проверка с ним
    // не поймала бы ни одного «вы» — зелёная впустую.
    const formal = /(^|[^а-яё])(вы|вас|вам|ваш[а-яё]*)(?=[^а-яё]|$)/i;
    expect('Вы справитесь').toMatch(formal);
    for (const d of all) expect(`${d.title} ${d.text}`).not.toMatch(formal);
  });
});

describe('ожидающий платёж на устройстве', () => {
  const store = new Map();
  beforeEach(() => {
    store.clear();
    globalThis.localStorage = {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    };
  });
  afterEach(() => clearPending());

  it('переживает перезапуск и забывается через сутки', () => {
    rememberPending('p1', 'lite', 1000);
    expect(readPending(2000)).toEqual({ id: 'p1', tier: 'lite', at: 1000 });
    expect(readPending(1000 + PENDING_TTL_MS)).toBeNull();
  });

  it('битая запись — как отсутствие', () => {
    store.set('aristea_pending_payment', '{oops');
    expect(readPending()).toBeNull();
  });
});
