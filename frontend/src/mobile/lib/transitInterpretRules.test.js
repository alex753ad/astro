/**
 * transitInterpretRules.test.js — пять исходов разбора транзита.
 *
 * ⚠️ Главный инвариант тот же, что у натального разбора: исходы обязаны
 * РАЗЛИЧАТЬСЯ на экране. Одна строка общей обработки ошибки превращает
 * «Оформите Лиру» в «проверьте связь» — потерянная продажа при внешне
 * исправном экране, и глазами это не ловится: чтобы увидеть, нужен free,
 * ткнувший в незначимый транзит.
 *
 * ⚠️ Классификация здесь по HTTP-СТАТУСУ, а не по событию потока. Ручка
 * `POST /chart/{id}/transits/event/interpret` читается обычным `fetch`, у
 * которого код и тело доступны; ветка «отказ первым событием потока», нужная
 * натальному разбору из-за `EventSource`, тут мёртвая. Скопировать сюда
 * `classifyOutcome` было бы хуже, чем написать своё: оно молча не сработало
 * бы.
 */
import { describe, expect, it } from 'vitest';

import {
  TRANSIT_ANON_TEXT,
  TRANSIT_BROKEN_TEXT,
  TRANSIT_OUTCOMES,
  classifyTransitError,
  transitUpsellFor,
} from './transitInterpretRules';

// Настоящие тексты сервера: main.py (значимость) и rate_limits.py (квота).
const NOT_SIGNIFICANT =
  'На бесплатном тарифе открыт разбор 2 самых значимых транзитов. '
  + 'Оформи Лиру, чтобы разбирать все транзиты.';
const RATE_LIMIT =
  'Использовано 3 расшифровок транзитов в этом месяце на тарифе Вега. '
  + 'Перейди на Лиру для безлимита.';

describe('пять исходов различимы', () => {
  it('free на незначимом транзите — текст сервера и кнопка тарифов', () => {
    const r = classifyTransitError({ status: 403, detail: NOT_SIGNIFICANT, authenticated: true });
    expect(r.outcome).toBe(TRANSIT_OUTCOMES.NOT_SIGNIFICANT);
    expect(r.text).toBe(NOT_SIGNIFICANT);
    expect(r.showPricing).toBe(true);
    expect(r.canRetry).toBe(false);
  });

  it('аноним — отдельный исход, без предложения купить', () => {
    const r = classifyTransitError({ status: 403, detail: '', authenticated: false });
    expect(r.outcome).toBe(TRANSIT_OUTCOMES.ANON);
    expect(r.text).toBe(TRANSIT_ANON_TEXT);
    expect(r.showPricing).toBe(false);
  });

  it('квота Веги исчерпана — текст сервера с числом', () => {
    const r = classifyTransitError({ status: 429, detail: RATE_LIMIT, authenticated: true });
    expect(r.outcome).toBe(TRANSIT_OUTCOMES.RATE_LIMIT);
    expect(r.text).toBe(RATE_LIMIT);
    expect(r.text).toContain('3');
    expect(r.showPricing).toBe(true);
    // Повтор бессмыслен: лимит повторится тем же отказом.
    expect(r.canRetry).toBe(false);
  });

  it('обрыв — свой текст, повтор предлагается, тарифов НЕТ', () => {
    const r = classifyTransitError({ authenticated: true });
    expect(r.outcome).toBe(TRANSIT_OUTCOMES.BROKEN);
    expect(r.text).toBe(TRANSIT_BROKEN_TEXT);
    expect(r.canRetry).toBe(true);
    // У человека проблема со связью, а не с подпиской.
    expect(r.showPricing).toBe(false);
  });

  it('успех — исход есть и он пятый', () => {
    // Успех не проходит через классификатор: он вызывается только на неуспехе.
    // Пятый исход экрана — отсутствие failure вообще.
    expect(TRANSIT_OUTCOMES.DONE).toBe('done');
  });

  it('ПЯТЬ ИСХОДОВ — ПЯТЬ РАЗНЫХ ТЕКСТОВ', () => {
    const texts = [
      classifyTransitError({ status: 403, detail: NOT_SIGNIFICANT, authenticated: true }).text,
      classifyTransitError({ status: 403, detail: '', authenticated: false }).text,
      classifyTransitError({ status: 429, detail: RATE_LIMIT, authenticated: true }).text,
      classifyTransitError({ authenticated: true }).text,
      '',   // успех: текста отказа нет вовсе
    ];
    expect(new Set(texts).size).toBe(5);
  });
});

describe('два 403 различаются НЕ по тексту', () => {
  it('один и тот же текст даёт разные исходы по признаку сессии', () => {
    // Сравнение содержимого привязало бы клиент к формулировке, которую
    // правят в маркетинговых целях, и сломало бы его молча.
    const same = 'один и тот же текст';
    expect(classifyTransitError({ status: 403, detail: same, authenticated: true }).outcome)
      .toBe(TRANSIT_OUTCOMES.NOT_SIGNIFICANT);
    expect(classifyTransitError({ status: 403, detail: same, authenticated: false }).outcome)
      .toBe(TRANSIT_OUTCOMES.ANON);
  });
});

describe('текст сервера не трогаем', () => {
  it('не обрезается и не получает приставки', () => {
    const r = classifyTransitError({ status: 403, detail: NOT_SIGNIFICANT, authenticated: true });
    expect(r.text).toBe(NOT_SIGNIFICANT);
    expect(r.text.startsWith('Не удалось')).toBe(false);
  });

  it('пустое тело не оставляет человека без объяснения', () => {
    // 403/429 без detail — не должно давать пустую строку на экране.
    expect(classifyTransitError({ status: 403, authenticated: true }).text).not.toBe('');
    expect(classifyTransitError({ status: 429, authenticated: true }).text).not.toBe('');
  });

  it('5xx — это транспорт, а не отказ по тарифу', () => {
    const r = classifyTransitError({ status: 500, detail: 'boom', authenticated: true });
    expect(r.outcome).toBe(TRANSIT_OUTCOMES.BROKEN);
    expect(r.showPricing).toBe(false);
  });
});

describe('приписка под готовым разбором', () => {
  const base = { known: true, finished: true, failed: false };

  it('free зовут в Вегу, lite в Лиру', () => {
    expect(transitUpsellFor({ ...base, tier: 'free' }).kind).toBe('free');
    expect(transitUpsellFor({ ...base, tier: 'lite' }).kind).toBe('lite');
  });

  it('pro и premium не получают ничего', () => {
    expect(transitUpsellFor({ ...base, tier: 'pro' })).toBeNull();
    expect(transitUpsellFor({ ...base, tier: 'premium' })).toBeNull();
  });

  it('неизвестный тариф — приписки нет вовсе', () => {
    // «Тариф ещё не приехал» и «тариф бесплатный» — разные вещи; на этой
    // разнице платящий получал чужое предложение (разбор — tierSource.js).
    expect(transitUpsellFor({ ...base, tier: null, known: false })).toBeNull();
    expect(transitUpsellFor({ ...base, tier: 'free', known: false })).toBeNull();
  });

  it('на незавершённом и на упавшем разборе приписки нет', () => {
    expect(transitUpsellFor({ ...base, tier: 'free', finished: false })).toBeNull();
    expect(transitUpsellFor({ ...base, tier: 'free', failed: true })).toBeNull();
  });
});
