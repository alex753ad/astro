/**
 * generate-nginx-routes.mjs — превращает src/routes.js в map для nginx.
 *
 * Запускается из `npm run build`. Результат — frontend/nginx-routes.conf,
 * его забирает 04-frontend-deploy.sh в /etc/nginx/conf.d/10-astro-routes.conf.
 *
 * ─── Зачем ───────────────────────────────────────────────────────────────────
 *
 * До 14.09.2026 nginx отвечал `try_files $uri $uri/ /index.html`, то есть
 * отдавал 200 и шелл на ЛЮБОЙ адрес, включая заведомо несуществующий. Для
 * поисковика это «страница есть» — классический софт-404.
 *
 * Чтобы отдавать честный 404, nginx должен знать список настоящих маршрутов.
 * Держать его там руками нельзя: это был бы второй источник истины о
 * маршрутах, и первая же новая страница в App.jsx, забытая в конфиге, отдала
 * бы жёсткий 404 на живом адресе. Поэтому список не пишется, а ГЕНЕРИРУЕТСЯ
 * из src/routes.js — того же файла, из которого кормятся роутер, sitemap и
 * пререндер.
 *
 * ─── Почему в conf.d, а не в snippets ────────────────────────────────────────
 *
 * Директива `map` объявляется только на уровне http. Файлы из
 * /etc/nginx/snippets/ подключаются внутрь server{} — там map не примут.
 * /etc/nginx/conf.d/*.conf nginx включает на уровне http сам, и делает это
 * ДО sites-enabled, так что переменная уже определена к моменту разбора сайта.
 *
 * ⚠️ Имя файла начинается с 10-, чтобы он читался после 00-astro-hardening.conf.
 * Взаимного порядка эти два файла не требуют, но алфавитная сортировка
 * conf.d — единственное, чем он вообще управляется, и пусть он будет явным.
 *
 * ─── Почему файл не лежит в репозитории ──────────────────────────────────────
 *
 * Он генерируемый, а каталог app/ на сервере — рабочая копия git. Файл,
 * который сборка переписывает внутри отслеживаемого каталога, ломает
 * следующий `git pull` и роняет деплой: это раздел «Файлы, которые портятся
 * сами» в CLAUDE.md, и там это уже случалось трижды. Поэтому вывод идёт в
 * frontend/nginx-routes.conf, а он в .gitignore.
 */

import { writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

import { ROUTES, expandRoute } from '../src/routes.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

/** Экранирует то, что в регулярном выражении nginx имеет особый смысл. */
function escapeRe(literal) {
  return literal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Путь маршрута → регулярное выражение, заякоренное с обоих концов.
 *
 * Параметры с перечисленными значениями (сегодня это :sign) разворачиваются в
 * группу с альтернативами, а не в [^/]+. Разница видна на /zodiac/абракадабра:
 * с [^/]+ он вернул бы 200 со страницей «Знак не найден», то есть софт-404,
 * ровно тот, который эта задача и убирает.
 */
function toRegex(route) {
  const parts = route.path.split('/').filter(Boolean).map(segment => {
    if (!segment.startsWith(':')) return escapeRe(segment);

    const name = segment.slice(1);
    const allowed = route.params && route.params[name];
    return allowed ? `(?:${allowed.map(escapeRe).join('|')})` : '[^/]+';
  });

  return parts.length ? `^/${parts.join('/')}/?$` : '^/$';
}

const entries = ROUTES.map(route => ({
  re: toRegex(route),
  // Сколько адресов стоит за записью — только для комментария в файле.
  count: expandRoute(route).length,
  path: route.path,
  kind: route.kind,
}));

const width = Math.max(...entries.map(e => e.re.length));

const body = entries
  .map(e => `    ~${e.re.padEnd(width)}  1;   # ${e.path}${e.count > 1 ? ` (${e.count} шт.)` : ''}`)
  .join('\n');

const out = `# СГЕНЕРИРОВАННЫЙ ФАЙЛ. Не править руками — перезаписывается сборкой.
# Источник: frontend/src/routes.js, генератор: frontend/scripts/generate-nginx-routes.mjs
# Собран: ${new Date().toISOString()}
#
# Переменная $is_app_route = 1 у известного маршрута приложения и 0 у всего
# остального. Её читает location @spa в astreatime.conf: незнакомый адрес
# получает честный 404 вместо шелла с кодом 200.
#
# Публичные маршруты тоже перечислены здесь, хотя обычно до @spa не доходят —
# пререндер кладёт их настоящими файлами, и try_files находит их раньше. Запись
# нужна как страховка: если пререндер когда-нибудь не отработает, страница
# должна отдаться шеллом, а не исчезнуть с сайта.

map $uri $is_app_route {
    default  0;

${body}
}
`;

const outPath = resolve(__dirname, '..', 'nginx-routes.conf');
writeFileSync(outPath, out, 'utf-8');
console.log(`✅ nginx-routes.conf: ${entries.length} маршрутов → ${outPath}`);
