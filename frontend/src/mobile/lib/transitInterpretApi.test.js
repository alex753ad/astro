/**
 * transitInterpretApi.test.js — разбор потока и тело запроса.
 *
 * ⚠️ Главное здесь — кадр, разорванный между чтениями. Вебовский
 * `TransitTimeline.jsx` режет каждое чтение по `\n` НА МЕСТЕ, без буфера, и
 * такой кадр теряет молча. Это тот же класс дефекта, что уже ловили с
 * `flushBuffer` в натальном разборе, — поэтому строки оттуда не копировались,
 * и поэтому же он проверяется тестом, а не «и так видно».
 *
 * ⚠️ Второе — `peak_date` берётся из `meta` и НЕ выводится из `at`. На боевых
 * данных 09.09.2026 у 15 событий из 278 они расходятся на сутки; дата входит
 * в ключ кэша разбора, и промах означает лишнюю генерацию и лишнюю единицу из
 * трёх на Веге при внешне исправном экране.
 */
import { describe, expect, it } from 'vitest';

import {
  buildTransitBody,
  canInterpretTransit,
  drainLines,
  parseLine,
} from './transitInterpretApi';

const EVENT = {
  kind: 'transit',
  at: '2026-09-17T00:32:00+03:00',
  meta: {
    transit_planet: 'Saturn',
    natal_planet: 'Sun',
    aspect_type: 'square',
    peak_date: '2026-09-16',
  },
};

describe('тело запроса', () => {
  it('четыре обязательных поля из meta', () => {
    expect(buildTransitBody(EVENT)).toEqual({
      transit_planet: 'Saturn',
      natal_planet: 'Sun',
      aspect_type: 'square',
      peak_date: '2026-09-16',
    });
  });

  it('peak_date берётся из meta, а НЕ из at', () => {
    // Ровно тот случай, ради которого поле заведено: событие около полуночи,
    // at ушёл на следующие сутки. Клиент, посчитавший at[:10], промахнулся бы
    // мимо готового кэша.
    expect(EVENT.at.slice(0, 10)).toBe('2026-09-17');
    expect(buildTransitBody(EVENT).peak_date).toBe('2026-09-16');
  });

  it('без peak_date запрос не отправляем — ручка ответит 422', () => {
    const broken = { ...EVENT, meta: { ...EVENT.meta, peak_date: undefined } };
    expect(canInterpretTransit(broken)).toBe(false);
    expect(canInterpretTransit(EVENT)).toBe(true);
  });

  it('событие без meta не ломает сборку тела', () => {
    expect(canInterpretTransit({ kind: 'transit' })).toBe(false);
  });
});

describe('буфер между чтениями', () => {
  it('незавершённая строка остаётся в остатке, а не теряется', () => {
    const [lines, tail] = drainLines('data: {"text": "раз"}\ndata: {"te');
    expect(lines).toEqual(['data: {"text": "раз"}']);
    expect(tail).toBe('data: {"te');
  });

  it('кадр, разорванный между чтениями, собирается целиком', () => {
    // Именно это теряет вебовский разборщик: половина кадра в одном чтении,
    // половина в следующем.
    let buffer = '';
    const got = [];
    for (const chunk of ['data: {"text": "пер', 'вая часть"}\n', 'data: [DONE]\n']) {
      buffer += chunk;
      const [lines, tail] = drainLines(buffer);
      buffer = tail;
      for (const line of lines) {
        const p = parseLine(line);
        if (p?.type === 'text') got.push(p.text);
      }
    }
    expect(got).toEqual(['первая часть']);
  });

  it('несколько кадров в одном чтении разбираются все', () => {
    const [lines] = drainLines('data: {"text": "а"}\ndata: {"text": "б"}\n');
    expect(lines.map((l) => parseLine(l)?.text)).toEqual(['а', 'б']);
  });
});

describe('разбор строки', () => {
  it('текст', () => {
    expect(parseLine('data: {"text": "привет"}')).toEqual({ type: 'text', text: 'привет' });
  });

  it('конец потока', () => {
    expect(parseLine('data: [DONE]')).toEqual({ type: 'done' });
  });

  it('ошибка внутри потока — исключение генерации, расход не списан', () => {
    expect(parseLine('data: {"error": "сломалось"}')).toEqual({ type: 'error', error: 'сломалось' });
  });

  it('не-data строки игнорируются', () => {
    expect(parseLine('')).toBeNull();
    expect(parseLine(': keep-alive')).toBeNull();
    expect(parseLine('event: message')).toBeNull();
  });

  it('пустая data не даёт пустого текста', () => {
    expect(parseLine('data: ')).toBeNull();
  });

  it('не-JSON доезжает текстом, а не исчезает', () => {
    // На этой ручке не встречается, но проглатывать молча нельзя.
    expect(parseLine('data: просто строка')).toEqual({ type: 'text', text: 'просто строка' });
  });
});
