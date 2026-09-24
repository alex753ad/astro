/**
 * interpretRules.test.js — четыре исхода потока и перезапрос из фона.
 *
 * Почему это вообще тест, а не «и так видно»: на вебе этот же класс дефекта
 * уже был. Отказ по лимиту приезжает первым событием ПОТОКА, а не
 * HTTP-статусом (`backend/main.py:1085-1108`), и любая общая обработка
 * ошибки — `catch → setError('Не удалось загрузить')` — превращает
 * «Оформите Вегу» в «Соединение прервалось». Экран при этом выглядит
 * исправным, поэтому глазами такой дефект не ловится: чтобы его увидеть,
 * нужен free с уже потраченным правом по этой карте.
 */
import { describe, expect, it } from 'vitest';
import {
  BROKEN_TEXT,
  OUTCOMES,
  TRANSPORT_LOST,
  classifyOutcome,
  shouldRefetchOnResume,
} from './interpretRules';

// Настоящие тексты сервера (`backend/auth/rate_limits.py:493-498, 516-522`).
const FREE_SPENT = 'Бесплатная интерпретация уже использована. Оформи Вегу, чтобы разбирать карты дальше.';
const TIER_LIMIT = 'Лимит 5 интерпретаций в месяц исчерпан для тарифа Вега. Оформи тариф повыше.';

describe('classifyOutcome — четыре исхода различимы', () => {
  it('поток дошёл до конца — успех', () => {
    const r = classifyOutcome({});
    expect(r.outcome).toBe(OUTCOMES.DONE);
    expect(r.showPricing).toBe(false);
  });

  it('free исчерпан — отказ с текстом сервера и предложением тарифов', () => {
    const r = classifyOutcome({ error: FREE_SPENT });
    expect(r.outcome).toBe(OUTCOMES.REFUSED);
    expect(r.text).toBe(FREE_SPENT);
    expect(r.showPricing).toBe(true);
  });

  it('лимит lite/pro — тот же исход, другой текст сервера', () => {
    const r = classifyOutcome({ error: TIER_LIMIT });
    expect(r.outcome).toBe(OUTCOMES.REFUSED);
    expect(r.text).toBe(TIER_LIMIT);
    expect(r.showPricing).toBe(true);
  });

  it('обрыв связи — свой текст и БЕЗ кнопки тарифов', () => {
    const r = classifyOutcome({ error: TRANSPORT_LOST });
    expect(r.outcome).toBe(OUTCOMES.BROKEN);
    expect(r.text).toBe(BROKEN_TEXT);
    // Главное в этом кейсе: у человека проблема со связью, а не с подпиской.
    expect(r.showPricing).toBe(false);
    expect(r.canRetry).toBe(true);
  });

  it('аноним — отдельный исход, а не пустой отказ', () => {
    const r = classifyOutcome({ status: 403 });
    expect(r.outcome).toBe(OUTCOMES.ANON);
    expect(r.text).not.toBe('');
    expect(r.showPricing).toBe(false);
  });

  it('все четыре исхода дают разный текст — ради этого всё и написано', () => {
    const texts = [
      classifyOutcome({ error: FREE_SPENT }).text,
      classifyOutcome({ error: TIER_LIMIT }).text,
      classifyOutcome({ error: TRANSPORT_LOST }).text,
      classifyOutcome({ status: 403 }).text,
    ];
    expect(new Set(texts).size).toBe(4);
  });
});

describe('classifyOutcome — текст сервера не трогаем', () => {
  it('не обрезается и не получает приставки', () => {
    const r = classifyOutcome({ error: FREE_SPENT });
    expect(r.text).toBe(FREE_SPENT);
    expect(r.text.startsWith('Не удалось')).toBe(false);
  });

  it('число и название тарифа доезжают до экрана как есть', () => {
    // Второй копии тарифной сетки в клиенте нет — числа только серверные.
    const r = classifyOutcome({ error: TIER_LIMIT });
    expect(r.text).toContain('5');
    expect(r.text).toContain('Вега');
  });

  it('403 С текстом — это отказ по существу, а не аноним', () => {
    // У анонима 403 приходит без текста; 403 с объяснением — обычный отказ.
    const r = classifyOutcome({ status: 403, error: FREE_SPENT });
    expect(r.outcome).toBe(OUTCOMES.REFUSED);
    expect(r.text).toBe(FREE_SPENT);
  });
});

describe('shouldRefetchOnResume — перезапрос при возврате из фона', () => {
  const base = { visible: true, open: true, started: true, finished: false };

  it('незавершённый поток перезапрашиваем — таймер в фоне не выполнялся', () => {
    expect(shouldRefetchOnResume(base)).toBe(true);
  });

  it('после успеха НЕ перезапрашиваем — текст уже на экране', () => {
    expect(shouldRefetchOnResume({ ...base, finished: true })).toBe(false);
  });

  it('после отказа НЕ перезапрашиваем — иначе экран моргает на каждом возврате', () => {
    // Отказ по лимиту никуда не денется, повтор даст ровно его же.
    expect(shouldRefetchOnResume({ ...base, finished: true })).toBe(false);
  });

  it('уход в фон ничего не запускает', () => {
    expect(shouldRefetchOnResume({ ...base, visible: false })).toBe(false);
  });

  it('закрытый экран разбора не перезапрашивает', () => {
    expect(shouldRefetchOnResume({ ...base, open: false })).toBe(false);
  });

  it('не запускали — не перезапрашиваем: автозапуска у разбора нет', () => {
    expect(shouldRefetchOnResume({ ...base, started: false })).toBe(false);
  });
});
