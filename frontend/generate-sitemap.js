/**
 * generate-sitemap.js — генерирует frontend/public/sitemap.xml
 * Запуск: node generate-sitemap.js
 * Вызывается автоматически при сборке: npm run build
 *
 * Список адресов НЕ хранится здесь. Он один на весь проект — src/routes.js,
 * оттуда же кормятся пререндер, роутер и map для nginx. Собственный перечень
 * в этом файле был до 14.09.2026 и успел разойтись с App.jsx: шесть путей
 * против двадцати пяти, без /zodiac/* вовсе.
 *
 * ─── Про lastmod ─────────────────────────────────────────────────────────────
 *
 * Берётся дата последнего КОММИТА, тронувшего исходник страницы, а не mtime
 * файла. Причина: на сервере сборка идёт из рабочей копии git, и mtime там —
 * это время, когда `git pull` записал файл на диск. У файла, который в этом
 * pull не менялся, останется дата первого клона; у изменившегося встанет
 * «сейчас». То есть mtime описывает историю ДЕПЛОЯ, а не правок страницы.
 *
 * ⚠️ Если git недоступен или по файлу нет истории, lastmod для этого адреса
 * НЕ выводится вовсе. Решение владельца 14.09.2026: неверная дата хуже
 * отсутствующей — Google сверяет её с тем, что реально меняется на странице,
 * и systematically неверная дата обесценивает сигнал целиком. Прежняя версия
 * ставила всем адресам дату сборки, то есть сообщала об изменении всех
 * страниц разом при каждой пересборке фронтенда.
 */

import { writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { execFileSync } from 'child_process';

import { CANONICAL_ORIGIN, publicUrls } from './src/routes.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Какой исходник отвечает за какой маршрут. Нужен только ради lastmod.
 * Ключ — `id` из routes.js.
 */
const SOURCE_BY_ID = {
  landing:    'src/pages/LandingPage.jsx',
  zodiac:     'src/pages/ZodiacPage.jsx',
  pricing:    'src/pages/PricingPage.jsx',
  orion:      'src/pages/OrionPage.jsx',
  terms:      'src/pages/TermsPage.jsx',
  privacy:    'src/pages/PrivacyPage.jsx',
  requisites: 'src/pages/RequisitesPage.jsx',
};

/** Приоритет и частота обхода. Отсутствие записи = значения по умолчанию. */
const HINTS = {
  landing:    { changefreq: 'weekly',  priority: '1.0' },
  pricing:    { changefreq: 'monthly', priority: '0.9' },
  orion:      { changefreq: 'monthly', priority: '0.8' },
  zodiac:     { changefreq: 'monthly', priority: '0.7' },
  terms:      { changefreq: 'yearly',  priority: '0.3' },
  privacy:    { changefreq: 'yearly',  priority: '0.3' },
  requisites: { changefreq: 'yearly',  priority: '0.3' },
};

const lastmodCache = new Map();

function lastCommitDate(relPath) {
  if (lastmodCache.has(relPath)) return lastmodCache.get(relPath);

  let value = null;
  try {
    const out = execFileSync(
      'git',
      ['log', '-1', '--format=%cs', '--', relPath],
      { cwd: __dirname, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] },
    ).trim();
    // %cs — дата коммита в формате YYYY-MM-DD. Пустой вывод значит, что файл
    // в истории не встречается (новый и ещё не закоммичен) — это не ошибка.
    if (/^\d{4}-\d{2}-\d{2}$/.test(out)) value = out;
  } catch {
    // git недоступен или каталог не репозиторий — молча без lastmod.
  }

  lastmodCache.set(relPath, value);
  return value;
}

function buildXml(entries) {
  const urls = entries
    .map(({ path, id }) => {
      const hint = HINTS[id] || { changefreq: 'monthly', priority: '0.5' };
      const source = SOURCE_BY_ID[id];
      const lastmod = source ? lastCommitDate(source) : null;

      return [
        '  <url>',
        `    <loc>${CANONICAL_ORIGIN}${path}</loc>`,
        ...(lastmod ? [`    <lastmod>${lastmod}</lastmod>`] : []),
        `    <changefreq>${hint.changefreq}</changefreq>`,
        `    <priority>${hint.priority}</priority>`,
        '  </url>',
      ].join('\n');
    })
    .join('\n');

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>
`;
}

const entries = publicUrls();
const outPath = resolve(__dirname, 'public/sitemap.xml');
writeFileSync(outPath, buildXml(entries), 'utf-8');

const withDate = entries.filter(e => SOURCE_BY_ID[e.id] && lastCommitDate(SOURCE_BY_ID[e.id])).length;
console.log(
  `✅ sitemap.xml: ${entries.length} URL (${withDate} с lastmod) → ${outPath}`,
);
