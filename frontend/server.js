/**
 * server.js — Express + Vite SSR для публичных маршрутов.
 *
 * Публичные маршруты (SSR): /, /home, /zodiac/*, /lunar, /calendar/lunar/*
 * Всё остальное (/chart/*, /profile, /dashboard/*, /planner/*) — отдаём index.html (SPA).
 *
 * Запуск (dev):  node server.js
 * Запуск (prod): NODE_ENV=production node server.js
 *   → требует предварительного `npm run build` и `npm run build:ssr`
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isProd = process.env.NODE_ENV === 'production';
const PORT = process.env.PORT || 3000;

// Публичные маршруты, которые рендерятся на сервере
const SSR_ROUTES = [
  '/',
  '/home',
  '/lunar',
];
const SSR_PREFIXES = [
  '/zodiac/',
  '/calendar/lunar',
];

function isSSRRoute(url) {
  const pathname = url.split('?')[0];
  if (SSR_ROUTES.includes(pathname)) return true;
  return SSR_PREFIXES.some(p => pathname.startsWith(p));
}

async function createServer() {
  const app = express();

  let vite;
  let template;
  let render;

  if (!isProd) {
    // Dev: используем Vite middleware
    const { createServer: createViteServer } = await import('vite');
    vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'custom',
    });
    app.use(vite.middlewares);
  } else {
    // Prod: статика из dist/
    app.use(express.static(path.resolve(__dirname, 'dist/client'), { index: false }));
    template = fs.readFileSync(path.resolve(__dirname, 'dist/client/index.html'), 'utf-8');
    render = (await import('./dist/server/entry-server.js')).render;
  }

  // Проксируем /api/* на бэкенд (только в dev; в prod — nginx/Railway делает это)
  if (!isProd) {
    const { createProxyMiddleware } = await import('http-proxy-middleware').catch(() => ({ createProxyMiddleware: null }));
    if (createProxyMiddleware) {
      const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
      app.use('/api', createProxyMiddleware({ target: backendUrl, changeOrigin: true }));
    }
  }

  app.use('*', async (req, res) => {
    const url = req.originalUrl;

    try {
      let html;

      if (isSSRRoute(url)) {
        // SSR: рендерим React на сервере
        if (!isProd) {
          template = fs.readFileSync(path.resolve(__dirname, 'index.html'), 'utf-8');
          template = await vite.transformIndexHtml(url, template);
          render = (await vite.ssrLoadModule('/src/entry-server.jsx')).render;
        }

        const appHtml = await render(url);
        html = template.replace('<!--ssr-outlet-->', appHtml);
      } else {
        // SPA: отдаём index.html без рендеринга
        if (!isProd) {
          template = fs.readFileSync(path.resolve(__dirname, 'index.html'), 'utf-8');
          template = await vite.transformIndexHtml(url, template);
          html = template;
        } else {
          html = template;
        }
      }

      res.status(200).set({ 'Content-Type': 'text/html' }).end(html);
    } catch (e) {
      if (!isProd && vite) vite.ssrFixStacktrace(e);
      console.error(e.stack);
      res.status(500).end(e.message);
    }
  });

  app.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT} [${isProd ? 'production' : 'development'}]`);
  });
}

createServer();
