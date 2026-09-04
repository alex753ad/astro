/**
 * vite.config.mobile.js — сборка Capacitor-бандла в dist-mobile.
 *
 * Отдельный конфиг, а не флаг внутри vite.config.js: веб-сборка, SSR и
 * локальная разработка не должны меняться ни в одном сценарии, а любое
 * ветвление внутри общего конфига — это как раз то место, где однажды
 * протечёт мобильная настройка в прод фронтенда.
 *
 * Запуск: npm run build:mobile  (= vite build --config vite.config.mobile.js --mode mobile)
 *
 * `--mode mobile` здесь несёт основную нагрузку: Vite грузит .env.mobile
 * ТОЛЬКО в этом режиме, а там задан VITE_API_URL с абсолютным адресом
 * боевого API. Веб собирается в режиме production и .env.mobile не видит
 * вообще — гарантия по построению, а не по аккуратности.
 */

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { renameSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const OUT_DIR = 'dist-mobile';

/**
 * Rollup именует выходной HTML по имени входного, то есть на диск лёг бы
 * dist-mobile/index.mobile.html. Capacitor же копирует webDir как есть и
 * открывает в webview именно index.html — без переименования приложение
 * стартует с пустого экрана, и причина по логам не видна.
 */
function mobileHtmlAsIndex() {
  return {
    name: 'mobile-html-as-index',
    closeBundle() {
      const from = path.join(__dirname, OUT_DIR, 'index.mobile.html');
      const to = path.join(__dirname, OUT_DIR, 'index.html');
      if (existsSync(from)) renameSync(from, to);
    },
  };
}

export default defineConfig({
  plugins: [react(), mobileHtmlAsIndex()],

  // Пути к ассетам обязаны быть относительными: страница открывается не с
  // сервера, а из локальных файлов APK. С абсолютного /assets/index-*.js
  // webview не найдёт ничего, экран останется пустым.
  base: './',

  build: {
    outDir: OUT_DIR,
    emptyOutDir: true,
    rollupOptions: {
      input: path.join(__dirname, 'index.mobile.html'),
    },
  },
});
