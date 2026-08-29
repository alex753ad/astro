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

const STATIC_ROUTES = [
  { path: '/',              changefreq: 'weekly',  priority: '1.0' },
  { path: '/lunar',          changefreq: 'daily',   priority: '0.9' },
  { path: '/pricing',       changefreq: 'monthly', priority: '0.9' },
  { path: '/requisites',    changefreq: 'monthly', priority: '0.5' },
  { path: '/terms',         changefreq: 'monthly', priority: '0.5' },
  { path: '/privacy',       changefreq: 'monthly', priority: '0.5' },
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
