/**
 * chartApi.test.js — разбор ответа `POST /charts/{id}/share`.
 *
 * Транспорт подменяется целиком: настоящий `authFetchWithTimeout` тянет
 * `api/client.js`, а тот — `@capacitor/preferences`, которого в тестовой
 * среде нет (тот же приём и по той же причине, что в api/session.test.js).
 *
 * ⚠️ Проверяется разбор ответа, НЕ лист «Поделиться» — его вёрстку не
 * видел никто, она уходит на приёмку руками. Инвариант «предупреждение до
 * действия» лежит отдельно, в shareRules.test.js.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const calls = [];
let nextResponse = null;

vi.mock('./authFetchTimeout', () => ({
  REQUEST_TIMEOUT_MS: 15000,
  authFetchWithTimeout: (url, options) => {
    calls.push({ url, options });
    if (nextResponse instanceof Error) return Promise.reject(nextResponse);
    return Promise.resolve(nextResponse);
  },
}));

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (body === undefined) throw new Error('не JSON');
      return body;
    },
  };
}

const { createShareLink } = await import('./chartApi');

beforeEach(() => {
  calls.length = 0;
  nextResponse = null;
});

describe('createShareLink — успех', () => {
  it('возвращает обе ссылки в том виде, в каком их построил сервер', async () => {
    nextResponse = jsonResponse(200, {
      share_url: 'https://aristeatime.ru/share/TOK',
      card_url: 'https://aristeatime.ru/share/TOK/card.png',
      token: 'TOK',
    });

    const result = await createShareLink('chart-1');

    expect(result).toEqual({
      shareUrl: 'https://aristeatime.ru/share/TOK',
      cardUrl: 'https://aristeatime.ru/share/TOK/card.png',
    });
  });

  it('card_url НЕ пересобирается из API_BASE — иначе на https://localhost вышел бы неоткрываемый адрес', async () => {
    nextResponse = jsonResponse(200, {
      share_url: 'https://www.aristeatime.ru/share/TOK',
      card_url: 'https://www.aristeatime.ru/share/TOK/card.png',
    });

    const { cardUrl } = await createShareLink('chart-1');

    expect(cardUrl).toBe('https://www.aristeatime.ru/share/TOK/card.png');
    expect(cardUrl).not.toMatch(/localhost/);
  });

  it('идёт POST-ом на /charts/{id}/share — множественное число, отдельный роутер', async () => {
    nextResponse = jsonResponse(200, {
      share_url: 'https://aristeatime.ru/share/TOK',
      card_url: 'https://aristeatime.ru/share/TOK/card.png',
    });

    await createShareLink('abc-123');

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toMatch(/\/charts\/abc-123\/share$/);
    expect(calls[0].options.method).toBe('POST');
  });
});

describe('createShareLink — отказ', () => {
  it('текст сервера показывается дословно: у 403/429 там сказано, что делать', async () => {
    nextResponse = jsonResponse(403, { detail: 'Карта не найдена' });

    await expect(createShareLink('chart-1')).rejects.toThrow('Карта не найдена');
  });

  it('отказ без внятного тела — свой текст со статусом', async () => {
    nextResponse = jsonResponse(500, undefined);

    await expect(createShareLink('chart-1')).rejects.toThrow(/Не удалось создать ссылку\. \(500\)/);
  });

  it('200 с неполным телом — это отказ, а не ссылка «undefined» в буфере', async () => {
    nextResponse = jsonResponse(200, { token: 'TOK' });

    await expect(createShareLink('chart-1')).rejects.toThrow(/Сервер не вернул ссылку/);
  });

  it('200 с нечитаемым телом — тоже отказ', async () => {
    nextResponse = jsonResponse(200, undefined);

    await expect(createShareLink('chart-1')).rejects.toThrow(/Сервер не вернул ссылку/);
  });

  it('обрыв связи доезжает наверх как есть — экран отличает его от отказа сервера', async () => {
    nextResponse = new Error('Сервер не отвечает. Проверь связь и попробуй ещё раз.');

    await expect(createShareLink('chart-1')).rejects.toThrow('Сервер не отвечает');
  });
});
