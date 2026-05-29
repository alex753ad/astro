/**
 * generate-sitemap.js — генерирует frontend/public/sitemap.xml
 * Запуск: node scripts/generate-sitemap.js
 * Вызывается автоматически при сборке: npm run build
 */

import { writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const BASE_URL = 'https://astreatime.ru';
const TODAY = new Date().toISOString().split('T')[0];

const ZODIAC_SIGNS = [
  'aries', 'taurus', 'gemini', 'cancer',
  'leo', 'virgo', 'libra', 'scorpio',
  'sagittarius', 'capricorn', 'aquarius', 'pisces',
];

const STATIC_ROUTES = [
  { path: '/',              changefreq: 'weekly',  priority: '1.0' },
  { path: '/calendar/lunar', changefreq: 'daily',   priority: '0.9' },
  { path: '/gift',          changefreq: 'monthly', priority: '0.7' },
  ...ZODIAC_SIGNS.map(sign => ({
    path: `/zodiac/${sign}`,
    changefreq: 'monthly',
    priority: '0.8',
  })),
];

function buildXml(routes) {
  const urls = routes
    .map(
      ({ path, changefreq, priority }) => `
  <url>
    <loc>${BASE_URL}${path}</loc>
    <lastmod>${TODAY}</lastmod>
    <changefreq>${changefreq}</changefreq>
    <priority>${priority}</priority>
  </url>`,
    )
    .join('');

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}
</urlset>`;
}

const xml = buildXml(STATIC_ROUTES);
const outPath = resolve(__dirname, 'public/sitemap.xml');
writeFileSync(outPath, xml, 'utf-8');
console.log(`✅ sitemap.xml generated: ${STATIC_ROUTES.length} URLs → ${outPath}`);
