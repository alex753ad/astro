import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  CATALOG_TIERS, ITEMS, LIMITS, catalogItem, quotaEndedText, resetDateWords, tierCard, usageDatesFrom,
} from './tierCatalog';
import { TIER_WORDS } from './interpretationUpsell';

const src = readFileSync(fileURLToPath(new URL('../../../backend/auth/rate_limits.py', import.meta.url)), 'utf-8');
const start = src.indexOf('TIER_FLAGS: dict');
const block = (t) => {
  const from = src.indexOf(`"${t}": {`, start);
  const next = CATALOG_TIERS[CATALOG_TIERS.indexOf(t) + 1];
  return src.slice(from, next ? src.indexOf(`"${next}": {`, from) : src.indexOf('\n}\n', from));
};
const num = (t, key) => {
  const m = block(t).match(new RegExp(`"${key}":\\s*(\\d+|None)`));
  expect(m, `${t}.${key}`).not.toBeNull();
  return m[1] === 'None' ? null : Number(m[1]);
};

describe('каталог тарифов — те же числа, что TIER_FLAGS', () => {
  it('карты, разборы карты, лунный календарь, горизонт транзитов, объём разбора', () => {
    for (const t of CATALOG_TIERS) {
      expect(LIMITS[t].charts, `${t} карты`).toBe(num(t, 'profiles_limit'));
      expect(LIMITS[t].lunar, `${t} лунный`).toBe(num(t, 'lunar_months'));
      expect(LIMITS[t].horizon, `${t} горизонт`).toBe(num(t, 'transits_months'));
      expect(TIER_WORDS[t], `${t} слова`).toBe(num(t, 'interpretation_word_limit'));
      expect(LIMITS[t].gcal, `${t} Google Календарь`).toBe(num(t, 'gcal_charts'));
    }
    for (const t of ['lite', 'pro', 'premium']) {
      expect(LIMITS[t].readings, `${t} разборы карты`).toBe(num(t, 'interpretations_per_month'));
    }
  });

  it('разборы транзитов и чат: пробные у free, месячные у Веги, без лимита выше', () => {
    expect(LIMITS.free.transits).toBe(num('free', 'transits_ai_trial'));
    expect(LIMITS.free.chat).toBe(num('free', 'chat_trial'));
    expect(LIMITS.lite.transits).toBe(num('lite', 'transits_ai_per_month'));
    expect(LIMITS.lite.chat).toBe(num('lite', 'chat_per_month'));
    for (const t of ['pro', 'premium']) {
      expect(LIMITS[t].transits).toBeNull();
      expect(num(t, 'transits_ai_per_month')).toBeNull();
      expect(LIMITS[t].chat).toBeNull();
    }
  });
});

describe('словарь витрины', () => {
  const all = CATALOG_TIERS.flatMap((t) => {
    const c = tierCard(t, { full: true });
    const app = tierCard(t, { surface: 'app', full: true });
    return [c.from, ...c.lines.flatMap((l) => [l.text, l.about]), app.site];
  }).filter(Boolean).join('\n');

  it('без «интерпретации», «AI», «ИИ»', () => {
    expect(all).not.toMatch(/интерпретац/i);
    expect(all).not.toMatch(/\bAI\b/);
    expect(all).not.toMatch(/(^|[^А-Яа-яЁё])ИИ([^А-Яа-яЁё]|$)/);
  });

  it('один термин на понятие', () => {
    expect(all).not.toMatch(/разбор аспектов|расшифровк|Google Calendar/i);
  });
});

describe('карточка тарифа', () => {
  it('накопительная: у Лиры «Всё из Веги», и только новое', () => {
    const lyra = tierCard('pro');
    expect(lyra.from).toBe('Всё из Веги, плюс:');
    const texts = lyra.lines.map((l) => l.text).join('\n');
    expect(texts).toContain('Чат с Аристеей — без лимита');
    // Google Календарь: на Веге — одна карта, у Лиры — все, и это видно в её карточке.
    expect(texts).toContain('Экспорт событий в Google Календарь — для всех карт');
    expect(tierCard('lite').lines.map((l) => l.text)).toContain('Экспорт событий в Google Календарь — для одной карты');
  });

  it('то, что человек пытался открыть, — первой строкой и подсвечено', () => {
    for (const t of ['lite', 'pro']) {
      const [first] = tierCard(t, { focus: 'chat' }).lines;
      expect(first.key).toBe('chat');
      expect(first.hl).toBe(true);
      expect(tierCard(t, { focus: 'chat' }).lines.filter((l) => l.hl)).toHaveLength(1);
    }
    // Лира не меняет периоды Солнца–Марса, но строка всё равно первая
    expect(tierCard('pro', { focus: 'planner_period' }).lines[0].key).toBe('planner_period');
    expect(tierCard('lite', { focus: 'transit_limit' }).lines[0].key).toBe('transit');
  });

  it('в приложении веб-пункты — одной короткой строкой «На сайте», без значений', () => {
    const app = tierCard('lite', { surface: 'app' });
    expect(app.lines.map((l) => l.text).join(' ')).not.toMatch(/Google|PDF|Лунный календарь/);
    expect(app.site).toBe('На сайте: лунный календарь, экспорт событий в Google Календарь, PDF-отчёт по карте');
    // Горизонт транзитов действует и в ленте приложения — это не «на сайте».
    expect(app.lines.map((l) => l.key)).toContain('transit_horizon');
  });

  it('«Всё, что есть бесплатно, плюс:» у Веги', () => {
    expect(tierCard('lite').from).toBe('Всё, что есть бесплатно, плюс:');
  });

  it('окно предложения — подсвеченная строка и главные пункты, всего не больше четырёх', () => {
    for (const t of ['lite', 'pro']) {
      for (const focus of [undefined, 'chat', 'transit_limit', 'planner_longterm', 'interpretation']) {
        const c = tierCard(t, { focus, brief: true });
        expect(c.lines.length, `${t} × ${focus}`).toBeLessThanOrEqual(4);
        expect(c.lines.length).toBeGreaterThanOrEqual(3);
      }
    }
    const lyra = tierCard('pro', { focus: 'chat', brief: true }).lines.map((l) => l.key);
    expect(lyra[0]).toBe('chat');
    expect(lyra).toEqual(['chat', 'transit', 'planner_longterm', 'chart_reading']);
  });

  it('у каждого пункта из offerRule есть строка каталога', () => {
    for (const f of ['planner_period', 'planner_moon', 'planner_longterm', 'transit', 'transit_limit', 'chat', 'chat_limit', 'interpretation']) {
      expect(catalogItem(f), f).not.toBeNull();
    }
    expect(new Set(ITEMS.map((i) => i.key)).size).toBe(ITEMS.length);
  });
});

describe('«обновятся …» / «доступ до …» — даты только от бэкенда', () => {
  it('дата словами', () => {
    expect(resetDateWords('2026-10-01')).toBe('1 октября');
    expect(resetDateWords(null)).toBeNull();
  });

  it('без дат хвоста нет; новое окно — «обновятся», без продления — «доступ до»', () => {
    expect(quotaEndedText('chat_limit', 'month', null)).toBe('Сообщения закончились');
    expect(quotaEndedText('chat', 'month', { resetsOn: '2026-10-01' })).toBe('Сообщения закончились — обновятся 1 октября');
    expect(quotaEndedText('chat', 'month', { resetsOn: null, accessUntil: '2026-10-29' }))
      .toBe('Сообщения закончились — новые после продления, доступ до 29 октября');
    expect(quotaEndedText('chat', 'trial')).toBe('Пробные сообщения закончились');
    expect(quotaEndedText('transit', 'month', { resetsOn: '2026-11-01' })).toContain('обновятся 1 ноября');
  });

  it('даты читаются и из профиля, и из кадра чата', () => {
    expect(usageDatesFrom({ usage_resets_on: null, usage_access_until: '2026-10-29' }))
      .toEqual({ resetsOn: null, accessUntil: '2026-10-29' });
    expect(usageDatesFrom({ resets_on: '2026-10-29', access_until: '2026-11-28' }))
      .toEqual({ resetsOn: '2026-10-29', accessUntil: '2026-11-28' });
  });
});

describe('текст замка — из каталога через offerRule', () => {
  it('периоды Солнца–Марса — Вега, без Сатурна; долгосрочные — Лира', async () => {
    const { lockText } = await import('./tierCatalog');
    const period = lockText('planner_period', 'free');
    expect(period).toContain('на тарифе Вега');
    expect(period).not.toMatch(/Сатурн/);
    expect(lockText('planner_longterm', 'free')).toMatch(/Сатурн.*на тарифе Лира/);
    expect(lockText('planner_longterm', 'pro')).toBe('');
  });
});
