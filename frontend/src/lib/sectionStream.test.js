/**
 * sectionStream.test.js — проверка однопроходного разборщика секций на ТРЁХ
 * записанных последовательностях событий, по одной на каждый путь отдачи
 * `/chart/{id}/interpret` (INTERPRET_SSE_RECON.md §2, §7).
 *
 * ⚠️ Одной живой последовательности здесь принципиально мало. Путь 2
 * (Redis-кэш) проходит через любой разумный парсер — теги там уже отделены
 * от текста самим сервером. Ломаются пути 1 и 3, причём по-разному:
 * на живом теги разрезаны по токенам (старый flushBuffer терял открывающие),
 * на сохранённом весь документ приезжает одним событием (старый flushBuffer
 * ломал порядок). Тест на одном пути пропустил бы половину дефекта.
 *
 * Все три последовательности строятся из ОДНОГО документа, поэтому главная
 * проверка — не «событий столько-то», а «все три пути дают одно и то же».
 */
import { describe, it, expect } from 'vitest';
import { createSectionParser, stripSectionTags, SECTION_NAMES } from './sectionStream';

// ── Документ, из которого собираются все три пути ────────────────────────
// Форма — как у боевого замера: шесть секций, текст абзацами.
const DOC_SECTIONS = SECTION_NAMES.map((name, i) => ({
  name,
  text: `Текст секции ${i + 1}. ${Array(12).fill('слово').join(' ')}.`,
}));

/** Канонический документ — то, что лежит в БД и в Redis (с тегами). */
const DOC = DOC_SECTIONS.map(s => `<section name="${s.name}">\n${s.text}\n</section>\n`).join('');

// ── Путь 1: живая генерация ─────────────────────────────────────────────
// Теги разрезаны ровно так, как записано в боевом замере
// (CHART_API_RECON.md:366-377): '<section', ' name', '="', имя, '">\n' и
// '</', 'section', '>'. Текст — по словам, как приходит по токенам.
function livePath() {
  const events = [];
  for (const s of DOC_SECTIONS) {
    events.push('<section', ' name', '="', s.name, '">\n');
    const words = s.text.split(' ');
    // Пробел приписывается всем словам кроме последнего — иначе склейка
    // чанков дала бы документ, отличающийся от канонического, и сравнение
    // путей между собой проверяло бы фикстуру, а не парсер.
    words.forEach((w, i) => events.push(i === words.length - 1 ? w : w + ' '));
    events.push('\n', '</', 'section', '>', '\n');
  }
  return events;
}

// ── Путь 2: Redis-кэш через replay_as_stream ────────────────────────────
// Теги отдельными порциями (keep_intact), текст по 8 слов, пробел ко всем
// порциям кроме последней в сегменте — правила backend/async_utils.py.
function replayPath() {
  const events = [];
  for (const s of DOC_SECTIONS) {
    events.push(`<section name="${s.name}">\n`);
    const words = `${s.text}\n`.split(' ');
    for (let i = 0; i < words.length; i += 8) {
      let piece = words.slice(i, i + 8).join(' ');
      if (i + 8 < words.length) piece += ' ';
      events.push(piece);
    }
    events.push('</section>\n');
  }
  return events;
}

// ── Путь 3: сохранённый разбор из БД ────────────────────────────────────
// Весь документ одним событием.
function savedPath() {
  return [DOC];
}

/** Прогоняет последовательность событий через парсер. */
function run(chunks) {
  const parser = createSectionParser();
  const events = [];
  for (const c of chunks) events.push(...parser.push(c));
  events.push(...parser.end());
  return events;
}

/**
 * Склеивает соседние text-события в одно.
 *
 * Дробление текста нарезкой потока — это НЕ различие в разборе: при подаче
 * по одному символу парсер обязан отдавать текст по мере поступления, иначе
 * на живой генерации не будет анимации набора. Сравнивать нарезки надо после
 * склейки — тогда проверяется именно разбор (границы и порядок тегов,
 * принадлежность текста секциям), а не то, сколько кусков доехало.
 */
function normalize(events) {
  const out = [];
  for (const e of events) {
    const last = out[out.length - 1];
    if (e.type === 'text' && last && last.type === 'text') last.text += e.text;
    else out.push({ ...e });
  }
  return out;
}

/**
 * Сводит события в структуру так же, как это делает потребитель
 * (`Interpretation.jsx`): текст до первой секции попадает в отдельный
 * блок `_intro`, а не приписывается первой секции и не теряется.
 */
function collect(events) {
  const sections = [];
  let current = null;
  for (const e of events) {
    if (e.type === 'section_start') {
      sections.push({ name: e.name, text: '' });
      current = sections[sections.length - 1];
    } else if (e.type === 'section_end') {
      current = null;
    } else if (e.type === 'text') {
      if (!current) {
        if (sections.length === 0) sections.push({ name: '_intro', text: '' });
        current = sections[sections.length - 1];
        sections[sections.length - 1].text += e.text;
        current = null; // текст вне секции не открывает секцию
      } else {
        current.text += e.text;
      }
    }
  }
  return sections;
}

const PATHS = {
  'путь 1 — живая генерация (теги по токенам)': livePath,
  'путь 2 — Redis-кэш (replay_as_stream)': replayPath,
  'путь 3 — сохранённый разбор (одно событие)': savedPath,
};

describe('три пути отдачи разбираются одинаково', () => {
  it('все три последовательности склеиваются в один и тот же документ', () => {
    // Проверка самих фикстур: если пути расходятся уже здесь, любое
    // сравнение разбора между ними проверяло бы фикстуру, а не парсер.
    for (const [label, build] of Object.entries(PATHS)) {
      expect(build().join(''), label).toBe(DOC);
    }
  });

  for (const [label, build] of Object.entries(PATHS)) {
    describe(label, () => {
      const events = run(build());
      const sections = collect(events);

      it('шесть секций в порядке документа, имена целы', () => {
        expect(sections.map(s => s.name)).toEqual(SECTION_NAMES);
      });

      it('section_start приходит на каждую секцию', () => {
        // Ровно этого не делал прежний flushBuffer на живом пути: порог
        // удержания в 19 символов короче тега <section name="general">.
        expect(events.filter(e => e.type === 'section_start')).toHaveLength(6);
      });

      it('section_end приходит на каждую секцию', () => {
        expect(events.filter(e => e.type === 'section_end')).toHaveLength(6);
      });

      it('текст попадает в свою секцию, а не в соседнюю', () => {
        for (let i = 0; i < DOC_SECTIONS.length; i++) {
          expect(sections[i].text.trim()).toBe(DOC_SECTIONS[i].text);
        }
      });

      it('ни одного обрывка разметки не доехало до текста', () => {
        const all = events.filter(e => e.type === 'text').map(e => e.text).join('');
        expect(all).not.toMatch(/<\/?section|name="/);
      });

      it('порядок событий: старт всегда раньше текста своей секции', () => {
        const kinds = events.map(e => e.type);
        expect(kinds[0]).toBe('section_start');
        // Ключевой дефект пути 3 у старого парсера: шесть стартов подряд до
        // всякого текста. Между двумя стартами обязан быть текст.
        for (let i = 1; i < kinds.length; i++) {
          if (kinds[i] === 'section_start') expect(kinds[i - 1]).toBe('section_end');
        }
      });
    });
  }

  it('все три пути дают одну и ту же последовательность событий', () => {
    const [live, replay, saved] = Object.values(PATHS)
      .map(build => normalize(run(build())));
    expect(replay).toEqual(live);
    expect(saved).toEqual(live);
  });
});

describe('нарезка потока не влияет на результат', () => {
  const reference = normalize(run([DOC]));

  it('по одному символу — то же, что одним куском в 40 КБ', () => {
    expect(normalize(run([...DOC]))).toEqual(reference);
  });

  it('граница чанка между ">" и "\\n" не меняет разбор', () => {
    // Перевод строки после тега по грамматике принадлежит тегу. Если его
    // не удержать, он станет пустой строкой в начале секции.
    const chunks = [];
    let rest = DOC;
    while (rest.length) {
      const cut = rest.indexOf('>\n');
      if (cut === -1) { chunks.push(rest); break; }
      chunks.push(rest.slice(0, cut + 1));
      rest = rest.slice(cut + 1);
    }
    expect(normalize(run(chunks))).toEqual(reference);
  });

  it('случайные нарезки дают тот же результат', () => {
    let seed = 42;
    const rnd = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
    for (let attempt = 0; attempt < 40; attempt++) {
      const chunks = [];
      let pos = 0;
      while (pos < DOC.length) {
        const len = 1 + rnd(37);
        chunks.push(DOC.slice(pos, pos + len));
        pos += len;
      }
      expect(normalize(run(chunks))).toEqual(reference);
    }
  });
});

describe('удержание хвоста — без порога длины', () => {
  it('состояние <section name="general (23 символа) не утекает в текст', () => {
    // Ровно тот буфер, на котором ломался старый flushBuffer: длиннее 19
    // символов, поэтому удержание не срабатывало и тег уходил в текст.
    const parser = createSectionParser();
    const events = [
      ...parser.push('<section'),
      ...parser.push(' name'),
      ...parser.push('="'),
      ...parser.push('general'),   // здесь буфер = 22 символа, порог был бы превышен
    ];
    expect(events).toEqual([]); // ничего не отдано — тег ещё набирается
    expect(parser.push('">\n')).toEqual([{ type: 'section_start', name: 'general' }]);
  });

  it('самое длинное имя (relationships, тег 30 символов) собирается целиком', () => {
    const parser = createSectionParser();
    const chunks = [...'<section name="relationships">\n'];
    const events = chunks.flatMap(c => parser.push(c));
    expect(events).toEqual([{ type: 'section_start', name: 'relationships' }]);
  });

  it('хвост отпускается, как только перестал быть возможным тегом', () => {
    const parser = createSectionParser();
    expect(parser.push('<sec')).toEqual([]);        // ещё может стать тегом
    expect(parser.push('t')).toEqual([]);
    expect(parser.push('X')).toEqual([{ type: 'text', text: '<sectX' }]);
  });

  it('обычный "<" в прозе не теряется и не удерживается навсегда', () => {
    const parser = createSectionParser();
    expect(parser.push('если 1 < 2, то ')).toEqual([{ type: 'text', text: 'если 1 < 2, то ' }]);
  });

  it('"<" в самом конце потока отдаётся, а не проглатывается', () => {
    const parser = createSectionParser();
    parser.push('текст <');
    const tail = [...parser.push(''), ...parser.end()];
    expect(tail.map(e => e.text).join('')).toContain('<');
  });
});

describe('краевые случаи разметки', () => {
  it('текст до первой секции не теряется и не приписывается ей', () => {
    const events = run(['Преамбула вне тегов. <section name="general">\nТело.\n</section>\n']);
    expect(events[0]).toEqual({ type: 'text', text: 'Преамбула вне тегов. ' });
    expect(events[1]).toEqual({ type: 'section_start', name: 'general' });
    expect(collect(events)[0]).toEqual({ name: '_intro', text: 'Преамбула вне тегов. ' });
  });

  it('незакрытая секция на конце потока закрывается сама, текст цел', () => {
    // Обрезка по длине: модель не дописала </section>.
    const events = run(['<section name="career">\nОборванный текст']);
    expect(events).toEqual([
      { type: 'section_start', name: 'career' },
      { type: 'text', text: 'Оборванный текст' },
      { type: 'section_end' },
    ]);
  });

  it('неизвестное имя секции отдаётся как есть, а не отбрасывается', () => {
    const events = run(['<section name="karma">\nТело.\n</section>\n']);
    expect(events[0]).toEqual({ type: 'section_start', name: 'karma' });
  });

  it('перевод строки после тега съедается ровно один раз', () => {
    const events = run(['<section name="general">\n\nДва перевода.\n</section>\n']);
    const text = events.filter(e => e.type === 'text').map(e => e.text).join('');
    expect(text).toBe('\nДва перевода.\n');
  });

  it('тег без имени (грамматика сервера его допускает) не ломает разбор', () => {
    const events = run(['<section>\nТело.\n</section>\n']);
    expect(events[0]).toEqual({ type: 'section_start', name: '' });
    expect(events.filter(e => e.type === 'section_end')).toHaveLength(1);
  });

  it('вложенный старт закрывает предыдущую секцию, поток остаётся сбалансированным', () => {
    const events = run(['<section name="general">\nА.<section name="career">\nБ.\n</section>\n']);
    expect(events.map(e => e.type)).toEqual([
      'section_start', 'text', 'section_end', 'section_start', 'text', 'section_end',
    ]);
  });

  it('закрывающий тег без открытой секции не порождает лишнего события', () => {
    const events = run(['Просто текст.\n</section>\n']);
    expect(events.filter(e => e.type === 'section_end')).toHaveLength(0);
    expect(events.filter(e => e.type === 'text').map(e => e.text).join('')).toBe('Просто текст.\n');
  });

  it('пустой поток не порождает событий', () => {
    expect(run([])).toEqual([]);
  });
});

/**
 * Подстраховка построчного рендера (`Interpretation.jsx`, `renderMarkdown`).
 * После удаления второго пути отрисовки заголовков (словарь
 * SECTION_TITLES_RU, 07.09.2026) именно эта проверка не даёт просочившейся
 * разметке нарисоваться человеку как проза.
 */
describe('stripSectionTags — разметка не рисуется человеку как проза', () => {
  /** Как решает вызывающая сторона (renderMarkdown): строка не рисуется
   * вовсе, если после чистки от неё ничего не осталось. */
  const isDropped = (raw) => {
    const line = stripSectionTags(raw);
    return line !== raw && !line.trim();
  };

  it('строка-тег с любым из шести имён не рисуется', () => {
    for (const name of SECTION_NAMES) {
      expect(isDropped(`<section name="${name}">`), name).toBe(true);
    }
  });

  it('закрывающий тег, тег без имени и неизвестное имя — тоже не рисуются', () => {
    expect(isDropped('</section>')).toBe(true);
    expect(isDropped('<section>')).toBe(true);
    expect(isDropped('<section name="karma">')).toBe(true);
  });

  it('пробелы по краям строки не мешают', () => {
    expect(isDropped('  <section name="general">  ')).toBe(true);
    expect(isDropped('\t</section>')).toBe(true);
  });

  it('тег ПОСРЕДИ прозы снимается, а сама проза остаётся', () => {
    // Прежний код заменял такую строку заголовком целиком и терял текст
    // вокруг тега. Выбрасывать строку нельзя — снимаем только разметку.
    expect(stripSectionTags('до <section name="general"> после'))
      .toBe('до  после');
    expect(isDropped('до <section name="general"> после')).toBe(false);
  });

  it('несколько тегов в одной строке снимаются все', () => {
    expect(stripSectionTags('</section><section name="career">')).toBe('');
  });

  it('обычная проза не меняется, включая угловые скобки', () => {
    for (const s of ['Ты человек, в котором уживаются две тяги.', 'если 1 < 2, то всё хорошо', '']) {
      expect(stripSectionTags(s)).toBe(s);
      expect(isDropped(s)).toBe(false);
    }
  });

  it('пустая строка остаётся пустой и рисуется как разрыв, а не выбрасывается', () => {
    // isDropped === false, значит renderMarkdown дойдёт до ветки <br>.
    expect(isDropped('')).toBe(false);
    expect(isDropped('   ')).toBe(false);
  });
});
