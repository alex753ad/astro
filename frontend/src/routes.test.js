/**
 * routes.test.js — сторож единственного списка маршрутов.
 *
 * ⚠️ Этот тест — ВРЕМЕННАЯ мера, и снимать его можно только вместе с переводом
 * App.jsx на импорт из routes.js (правка роутера не согласована с владельцем
 * на 14.09.2026). Пока App.jsx держит собственные <Route>, списка формально
 * два, и без этой проверки они разойдутся молча — ровно так и произошло с
 * generate-sitemap.js: там был свой перечень из шести путей против двадцати
 * пяти в App.jsx, и /zodiac/* не попадали в карту сайта вообще.
 *
 * Чем это грозит теперь, когда из routes.js кормится ещё и nginx: маршрут,
 * добавленный в App.jsx и забытый здесь, получит не «страницу без
 * индексации», а ЖЁСТКИЙ 404 — location @spa отдаёт шелл только известным
 * адресам. То есть цена расхождения выросла с «не видно в Google» до
 * «страница не открывается».
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

import { ROUTES, ZODIAC_SLUGS, expandRoute, publicUrls } from './routes.js';

const here = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(here, 'App.jsx'), 'utf-8');

/** Пути из App.jsx: <Route path="..." />, кроме catch-all '*'. */
function pathsFromApp() {
  const found = [...appSource.matchAll(/<Route\s+path=(?:"([^"]+)"|\{'([^']+)'\})/g)]
    .map(m => m[1] ?? m[2])
    .filter(p => p !== '*');
  return new Set(found);
}

describe('единственный список маршрутов', () => {
  it('App.jsx и routes.js описывают одни и те же пути', () => {
    const fromApp = pathsFromApp();
    const fromTable = new Set(ROUTES.map(r => r.path));

    const missingInTable = [...fromApp].filter(p => !fromTable.has(p));
    const missingInApp = [...fromTable].filter(p => !fromApp.has(p));

    expect(
      missingInTable,
      'есть в App.jsx, нет в routes.js — такой адрес отдаст 404 на проде',
    ).toEqual([]);
    expect(
      missingInApp,
      'есть в routes.js, нет в App.jsx — nginx пустит на несуществующую страницу',
    ).toEqual([]);
  });

  it('в App.jsx разобрано непустое число маршрутов', () => {
    // Без этой проверки регулярка, переставшая что-либо находить (перенос
    // строки в JSX, другие кавычки), сделала бы тест выше зелёным на пустых
    // множествах — вакуумная проверка, которая ничего не проверяет.
    expect(pathsFromApp().size).toBeGreaterThan(20);
  });
});

describe('разворачивание маршрутов', () => {
  it('все двенадцать знаков зодиака дают отдельный адрес', () => {
    const zodiac = ROUTES.find(r => r.id === 'zodiac');
    const urls = expandRoute(zodiac).map(u => u.path);

    expect(urls).toHaveLength(12);
    expect(urls).toContain('/zodiac/leo');
    expect(urls.every(u => !u.includes(':'))).toBe(true);
  });

  it('слаги знаков совпадают с тем, что понимает ZodiacPage', () => {
    // ZodiacPage.jsx ищет знак по ключу из URL. Разойдутся — страница
    // отрисует «Знак не найден», причём с кодом 200 и в индексе.
    const page = readFileSync(resolve(here, 'pages/ZodiacPage.jsx'), 'utf-8');
    const signsBlock = page.slice(page.indexOf('const SIGNS'), page.indexOf('const FAQ'));
    for (const slug of ZODIAC_SLUGS) {
      expect(signsBlock, `ZodiacPage не знает знак «${slug}»`).toContain(`${slug}:`);
    }
  });
});

describe('метаданные публичных страниц', () => {
  const urls = publicUrls();

  it('у каждой публичной страницы есть свой title и description', () => {
    for (const { path, seo } of urls) {
      expect(seo?.title, `нет title у ${path}`).toBeTruthy();
      expect(seo?.description, `нет description у ${path}`).toBeTruthy();
    }
  });

  it('заголовки не повторяются', () => {
    // Одинаковый title на нескольких страницах — то состояние, из которого
    // задача и начиналась: все маршруты отдавали общий заголовок index.html.
    const titles = urls.map(u => u.seo.title);
    expect(new Set(titles).size).toBe(titles.length);
  });

  it('description укладывается в то, что показывает выдача', () => {
    for (const { path, seo } of urls) {
      expect(seo.description.length, `слишком коротко у ${path}`).toBeGreaterThan(50);
      expect(seo.description.length, `слишком длинно у ${path}`).toBeLessThan(300);
    }
  });
});
