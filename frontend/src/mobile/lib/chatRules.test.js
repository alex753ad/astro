import { describe, it, expect } from 'vitest';
import {
  CHAT_BROKEN_TEXT,
  CHAT_OUTCOMES,
  CHAT_STREAM_ERROR_CODES,
  CHAT_TIER_TEXT,
  STICK_THRESHOLD_PX,
  classifyChatError,
  hasScrolledAway,
  shouldReportInterrupted,
  shouldStickToBottom,
} from './chatRules';
import { parseChatLine } from './ragChatApi';

describe('classifyChatError — отказы до потока приходят статусом', () => {
  it('403 даёт свой текст, а не текст сервера', () => {
    // ⚠️ Главный кейс: у require_tier detail — ОБЪЕКТ, человеческого текста в
    // ответе нет вовсе. Показать его нечем, поэтому текст пишется на клиенте.
    const r = classifyChatError({ status: 403, detail: '' });
    expect(r.outcome).toBe(CHAT_OUTCOMES.TIER);
    expect(r.text).toBe(CHAT_TIER_TEXT);
    expect(r.showPricing).toBe(true);
    expect(r.canRetry).toBe(false);
  });

  it('403 не подставляет строку, даже если она откуда-то пришла', () => {
    // Защита от будущей правки бэкенда, которая начнёт слать строку: текст
    // тарифа согласован с владельцем, и подмена его серверным была бы молчаливой.
    const r = classifyChatError({ status: 403, detail: 'tier_required' });
    expect(r.text).toBe(CHAT_TIER_TEXT);
    expect(r.text).not.toContain('tier_required');
  });

  it('429 показывает текст сервера дословно — число в нём серверное', () => {
    const r = classifyChatError({ status: 429, detail: 'Слишком много запросов (20/час).' });
    expect(r.outcome).toBe(CHAT_OUTCOMES.RATE_LIMIT);
    expect(r.text).toBe('Слишком много запросов (20/час).');
    expect(r.showPricing).toBe(false);   // платить не за что, это не тариф
  });

  it('503 — дневной бюджет, тарифы не предлагаем', () => {
    const r = classifyChatError({ status: 503, detail: 'Дневной лимит AI-запросов исчерпан.' });
    expect(r.outcome).toBe(CHAT_OUTCOMES.BUDGET);
    expect(r.showPricing).toBe(false);
    expect(r.canRetry).toBe(false);
  });

  it('404 не показывает внутренний идентификатор из текста сервера', () => {
    // Сервер отвечает «Chart not found: 3f2a…-uuid» — тот же случай, что в
    // fetchFeed и fetchChart, и та же подмена.
    const r = classifyChatError({ status: 404, detail: 'Chart not found: 3f2a1b9c-uuid' });
    expect(r.outcome).toBe(CHAT_OUTCOMES.NO_CHART);
    expect(r.text).not.toContain('3f2a1b9c');
  });

  it('400 — пустой вопрос', () => {
    expect(classifyChatError({ status: 400 }).outcome).toBe(CHAT_OUTCOMES.BAD_QUESTION);
  });

  it('без статуса — обрыв, и только он даёт повтор', () => {
    const r = classifyChatError({});
    expect(r.outcome).toBe(CHAT_OUTCOMES.BROKEN);
    expect(r.text).toBe(CHAT_BROKEN_TEXT);
    expect(r.canRetry).toBe(true);
  });

  it('повтор предлагается ровно в одном исходе из шести', () => {
    // Инвариант, а не пересказ кода: повтор осмыслен только там, где он может
    // дать другой результат. Отказ по тарифу, квоте и бюджету повторится собой.
    const outcomes = [
      classifyChatError({ status: 403 }),
      classifyChatError({ status: 429 }),
      classifyChatError({ status: 503 }),
      classifyChatError({ status: 404 }),
      classifyChatError({ status: 400 }),
      classifyChatError({}),
    ];
    expect(outcomes.filter((o) => o.canRetry)).toHaveLength(1);
  });

  it('шесть исходов дают шесть разных текстов', () => {
    // Одна строка общей обработки ошибки этот тест роняет — тот же приём, что
    // поймал настоящий дефект в interpretRules.test.js.
    const texts = [403, 429, 503, 404, 400].map(
      (status) => classifyChatError({ status, detail: `текст ${status}` }).text,
    );
    texts.push(classifyChatError({}).text);
    expect(new Set(texts).size).toBe(6);
  });
});

describe('ошибки, приходящие кадром внутри потока', () => {
  it('все три кода дают повторяемый обрыв, а не отказ по тарифу', () => {
    for (const code of CHAT_STREAM_ERROR_CODES) {
      const r = classifyChatError({ detail: code });   // статуса нет — поток уже начался
      expect(r.outcome).toBe(CHAT_OUTCOMES.BROKEN);
      expect(r.canRetry).toBe(true);
    }
  });

  it('машинный код НИКОГДА не попадает в текст для человека', () => {
    // ⚠️ Ради этого написан отдельный parseChatLine. parseLine транзита
    // отдал бы `error` наружу как текст, и человек увидел бы «stream_failed».
    for (const code of CHAT_STREAM_ERROR_CODES) {
      expect(classifyChatError({ detail: code }).text).not.toContain(code);
    }
  });
});

describe('parseChatLine — кадр ошибки несёт И код, И текст', () => {
  it('забирает оба поля, а не одно', () => {
    const frame = 'data: {"error":"stream_failed","text":"Что-то пошло не так."}';
    expect(parseChatLine(frame)).toEqual({
      type: 'error',
      code: 'stream_failed',
      text: 'Что-то пошло не так.',
    });
  });

  it('обычный кусок текста', () => {
    expect(parseChatLine('data: {"text":"Ваш Марс"}')).toEqual({ type: 'text', text: 'Ваш Марс' });
  });

  it('[DONE] завершает поток', () => {
    expect(parseChatLine('data: [DONE]')).toEqual({ type: 'done' });
  });

  it('не-data строки игнорируются', () => {
    expect(parseChatLine(': keep-alive')).toBeNull();
    expect(parseChatLine('')).toBeNull();
  });

  it('⚠️ ответ про недоступность AI неотличим от обычного текста', () => {
    // Это не проверка правильности, а ЗАКРЕПЛЕНИЕ известного ограничения.
    // Ветка httpx.HTTPStatusError в rag_router.py шлёт «AI-сервис временно
    // недоступен» обычным кадром {"text": ...}, без поля error. Отличить его
    // от настоящего ответа Аристеи можно только сравнением строки — а
    // привязываться к формулировке сервера в этом проекте уже запрещено
    // (transitInterpretRules.js). Значит текст попадает в пузырёк как ответ.
    // Если это когда-нибудь начнут чинить — чинить на сервере, отдельным кодом.
    const frame = 'data: {"text":"Извините, AI-сервис временно недоступен."}';
    expect(parseChatLine(frame).type).toBe('text');
  });
});

describe('прокрутка — прилипаем к низу только если человек уже внизу', () => {
  it('у самого низа прилипаем', () => {
    expect(shouldStickToBottom({ distanceFromBottom: 0, userScrolledAway: false })).toBe(true);
  });

  it('отлистал вверх — не прилипаем', () => {
    expect(shouldStickToBottom({ distanceFromBottom: 900, userScrolledAway: false })).toBe(false);
  });

  it('флаг «ушёл сам» перебивает даже нулевое расстояние', () => {
    // Касание отменяет прилипание до конца ответа: иначе лента дёрнется
    // из-под пальца ровно в тот момент, когда человек её тронул.
    expect(shouldStickToBottom({ distanceFromBottom: 0, userScrolledAway: true })).toBe(false);
  });

  it('порог у обоих решений один и тот же', () => {
    // ⚠️ Инвариант: разойдись пороги — появилась бы зона, где мы и не
    // прилипаем, и не считаем, что человек ушёл. Список бы просто замер.
    const atThreshold = { distanceFromBottom: STICK_THRESHOLD_PX };
    expect(shouldStickToBottom({ ...atThreshold, userScrolledAway: false })).toBe(true);
    expect(hasScrolledAway(atThreshold)).toBe(false);

    const past = { distanceFromBottom: STICK_THRESHOLD_PX + 1 };
    expect(shouldStickToBottom({ ...past, userScrolledAway: false })).toBe(false);
    expect(hasScrolledAway(past)).toBe(true);
  });
});

describe('возврат из фона — сообщаем, но не перезапрашиваем', () => {
  it('вернулись, а ответ не дошёл — сообщаем', () => {
    expect(shouldReportInterrupted({ visible: true, streaming: true })).toBe(true);
  });

  it('ушли в фон — молчим', () => {
    expect(shouldReportInterrupted({ visible: false, streaming: true })).toBe(false);
  });

  it('ответ уже пришёл — не сообщаем ни о чём', () => {
    expect(shouldReportInterrupted({ visible: true, streaming: false })).toBe(false);
  });
});
