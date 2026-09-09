import { describe, expect, it } from 'vitest';

import { parseSseLine, readSseLines, splitLines } from './sseLines';

/**
 * sseLines.test.js — два предохранителя, без которых текст портился молча.
 *
 * ⚠️ Главный кейс — `многобайтовый символ, разорванный между чтениями`. До
 * 09.09.2026 `TransitTimeline.jsx` декодировал каждое чтение как самостоятельное
 * (`dec.decode(value)` без `{ stream: true }`), и русская буква, попавшая на
 * границу сетевых пакетов, превращалась в «замену» U+FFFD. Дефект плавающий:
 * граница чтений зависит от размера пакетов, поэтому глазами он ловится
 * случайно и не воспроизводится по требованию — а тестом воспроизводится
 * ровно.
 *
 * Второй кейс — SSE-кадр, разорванный посередине. Разбор без буфера между
 * чтениями терял такой кадр целиком: кусок текста исчезал, а поток шёл
 * дальше как ни в чём не бывало.
 */

/** Поток из заранее нарезанных байтовых кусков. */
function streamOf(chunks) {
  let i = 0;
  return {
    getReader() {
      return {
        read: async () => (i < chunks.length
          ? { done: false, value: chunks[i++] }
          : { done: true, value: undefined }),
      };
    },
  };
}

async function collect(chunks) {
  const out = [];
  for await (const ev of readSseLines(streamOf(chunks))) out.push(ev);
  return out;
}

const enc = new TextEncoder();

describe('многобайтовый символ на границе чтений', () => {
  it('русская буква, разрезанная пополам, собирается целиком', async () => {
    // «Юпитер» в UTF-8: каждая кириллическая буква — два байта. Режем поток
    // ВНУТРИ буквы «п», как это делает сеть.
    const frame = enc.encode('data: {"text": "Юпитер"}\n');
    // Точку разреза ищем, а не задаём числом: индекс зависит от длины
    // префикса, и захардкоженный молча съехал бы при правке кадра,
    // оставив тест зелёным и бессмысленным.
    const cut = frame.findIndex((b) => (b & 0b1100_0000) === 0b1000_0000);
    expect(cut, 'в кадре нет многобайтового символа').toBeGreaterThan(0);

    const events = await collect([frame.slice(0, cut), frame.slice(cut)]);

    expect(events).toEqual([{ type: 'text', text: 'Юпитер' }]);
    // Именно это и ломалось: вместо буквы приезжала «замена».
    expect(events[0].text).not.toContain('�');
  });

  it('замены нет ни при какой точке разреза', async () => {
    const text = 'Транзит Сатурна к натальному Солнцу';
    const frame = enc.encode(`data: {"text": "${text}"}\n`);
    for (let cut = 1; cut < frame.length; cut++) {
      const events = await collect([frame.slice(0, cut), frame.slice(cut)]);
      const joined = events.filter((e) => e.type === 'text').map((e) => e.text).join('');
      expect(joined, `разрез на байте ${cut}`).toBe(text);
    }
  });

  it('хвост декодера добирается в конце потока', async () => {
    // Поток оборвался на незавершённой последовательности — «замены» в уже
    // отданном тексте быть не должно.
    const frame = enc.encode('data: {"text": "Луна"}\n');
    const events = await collect([frame]);
    expect(events[0].text).toBe('Луна');
  });
});

describe('кадр, разорванный между чтениями', () => {
  it('половина кадра в одном чтении, половина в следующем', async () => {
    const events = await collect([
      enc.encode('data: {"text": "пер'),
      enc.encode('вая часть"}\ndata: [DONE]\n'),
    ]);
    expect(events).toEqual([{ type: 'text', text: 'первая часть' }, { type: 'done' }]);
  });

  it('несколько кадров в одном чтении разбираются все', async () => {
    const events = await collect([
      enc.encode('data: {"text": "а"}\ndata: {"text": "б"}\n'),
    ]);
    expect(events.map((e) => e.text)).toEqual(['а', 'б']);
  });

  it('строка без завершающего перевода в конце потока не теряется', async () => {
    const events = await collect([enc.encode('data: {"text": "хвост"}')]);
    expect(events).toEqual([{ type: 'text', text: 'хвост' }]);
  });

  it('текст собирается в том же порядке, в каком пришёл', async () => {
    const events = await collect([
      enc.encode('data: {"text": "раз "}\n'),
      enc.encode('data: {"text": "два "}\ndata: {"tex'),
      enc.encode('t": "три"}\ndata: [DONE]\n'),
    ]);
    const joined = events.filter((e) => e.type === 'text').map((e) => e.text).join('');
    expect(joined).toBe('раз два три');
  });
});

describe('splitLines — остаток не выбрасывается', () => {
  it('незавершённая строка возвращается хвостом', () => {
    expect(splitLines('data: {"a":1}\ndata: {"b')).toEqual([['data: {"a":1}'], 'data: {"b']);
  });

  it('буфер без перевода строки целиком уходит в хвост', () => {
    expect(splitLines('data: {"a')).toEqual([[], 'data: {"a']);
  });
});

describe('parseSseLine', () => {
  it('текст, конец и ошибка различаются', () => {
    expect(parseSseLine('data: {"text": "т"}')).toEqual({ type: 'text', text: 'т' });
    expect(parseSseLine('data: [DONE]')).toEqual({ type: 'done' });
    expect(parseSseLine('data: {"error": "e"}')).toEqual({ type: 'error', error: 'e' });
  });

  it('служебные строки игнорируются', () => {
    expect(parseSseLine(': heartbeat')).toBeNull();
    expect(parseSseLine('event: message')).toBeNull();
    expect(parseSseLine('')).toBeNull();
    expect(parseSseLine('data: ')).toBeNull();
  });

  it('не-JSON доезжает текстом, а не исчезает', () => {
    expect(parseSseLine('data: просто строка')).toEqual({ type: 'text', text: 'просто строка' });
  });
});
