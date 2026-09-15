/**
 * prerender.mjs — превращает публичные маршруты SPA в настоящие HTML-файлы.
 *
 * Запускается последним шагом `npm run build`, после vite и assert-bundle.
 *
 * ─── Зачем ───────────────────────────────────────────────────────────────────
 *
 * До 14.09.2026 сервер отдавал на ЛЮБОЙ адрес один и тот же файл в 1896 байт:
 * <div id="root"></div> и ссылку на бандл. Проверено curl'ом по живому домену —
 * осмысленного текста в ответе ноль, у всех маршрутов побайтно одинаково.
 * Google такие страницы ставит в очередь на рендеринг, и для нового домена без
 * входящих ссылок очередь может не дойти никогда: ИИ-обзор Google отвечал про
 * сайт «не имеет активного публичного наполнения, которое индексировалось бы».
 *
 * ─── Почему на сервере, а не в CI ────────────────────────────────────────────
 *
 * Пререндер обязан идти там же, где `vite build`, и это не предпочтение.
 * В готовый HTML запекается <script src="/assets/index-<хеш>.js">, а хеш
 * меняется от каждой правки фронтенда. HTML, снятый с другой сборки, сошлётся
 * на несуществующий файл: страница отдастся, бандл не загрузится, приложение
 * не смонтируется вовсе. Сборка фронтенда живёт на VPS (04-frontend-deploy.sh
 * делает npm ci && npm run build прямо там), значит и браузер нужен там.
 * Перенести пререндер в CI можно только вместе со сборкой — это другая задача.
 *
 * ─── Как ─────────────────────────────────────────────────────────────────────
 *
 *   1. dist/index.html копируется в dist/app.html — это ЧИСТЫЙ шелл.
 *      Им nginx отвечает на маршруты приложения (см. ⚠️ ниже).
 *   2. поднимается статический сервер на dist;
 *   3. каждый публичный адрес открывается в headless-хроме, дождавшись
 *      содержимого в #root и окончания вступительной анимации;
 *   4. в <head> проставляются title, description, canonical и og:* из
 *      src/routes.js — единственного места, где они объявлены;
 *   5. HTML пишется в dist/<путь>/index.html.
 *
 * ⚠️ Зачем отдельный app.html, если есть index.html. После пререндера
 * dist/index.html — это ЛЕНДИНГ со своим canonical на «/». Если отдавать его
 * же как шелл для /profile или /chart/123, то каждая такая страница до
 * выполнения JS будет содержимым лендинга и — хуже — его canonical, то есть
 * будет сообщать поисковику «на самом деле я главная». app.html пустой и
 * ничего про себя не утверждает.
 *
 * ⚠️ Скрипт обязан РОНЯТЬ сборку при любом отказе. Молчаливый пропуск здесь
 * дал бы ровно тот сценарий, ради которого написан assert-bundle: зелёная
 * сборка, уехавший на прод dist, тихо не работающая фича.
 */

import { createServer } from 'http';
import { readFile, writeFile, mkdir, copyFile, access } from 'fs/promises';
import { existsSync } from 'fs';
import { resolve, dirname, extname, join } from 'path';
import { fileURLToPath } from 'url';

import puppeteer from 'puppeteer-core';

import { CANONICAL_ORIGIN, publicUrls } from '../src/routes.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DIST = resolve(__dirname, '..', 'dist');
const PORT = 4183;

/**
 * Сколько ждать после прокрутки, прежде чем снимать.
 *
 * Страница завёрнута в <motion.div initial={{opacity: 0}}> (App.jsx, 180 мс),
 * а секции лендинга появляются по whileInView с длительностью 0.4–0.5 с.
 * Снимок раньше времени запечёт style="opacity: 0" — текст уедет в индекс
 * невидимым. 900 мс перекрывает самую долгую из этих анимаций вдвое.
 */
const SETTLE_MS = 900;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.svg':  'image/svg+xml',
  '.webp': 'image/webp',
  '.woff2':'font/woff2',
  '.ico':  'image/x-icon',
  '.txt':  'text/plain; charset=utf-8',
  '.xml':  'text/xml',
};

/**
 * Где искать браузер. PUPPETEER_EXECUTABLE_PATH важнее всего остального:
 * им 04-frontend-deploy.sh передаёт путь, найденный на сервере.
 * Список ниже — только удобство для локального прогона.
 */
function findBrowser() {
  const fromEnv = process.env.PUPPETEER_EXECUTABLE_PATH;
  if (fromEnv) {
    if (!existsSync(fromEnv)) {
      throw new Error(`PUPPETEER_EXECUTABLE_PATH указывает на несуществующий файл: ${fromEnv}`);
    }
    return fromEnv;
  }

  const candidates = [
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
    '/snap/bin/chromium',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ];
  const found = candidates.find(p => existsSync(p));
  if (!found) {
    throw new Error(
      'Chromium не найден. Установите его (apt-get install -y chromium) или задайте\n' +
      'PUPPETEER_EXECUTABLE_PATH. Пререндер без браузера невозможен, сборка остановлена.',
    );
  }
  return found;
}

/**
 * Статический сервер поверх dist.
 *
 * Всё, что похоже на файл и существует, отдаётся как файл; остальное — чистый
 * шелл. Отдаём именно шелл, а не уже записанный результат пререндера: иначе
 * порядок обхода маршрутов начал бы влиять на содержимое снимков.
 *
 * Запросы к /api/ отбиваются сразу: бэкенда на машине сборки нет, и без этого
 * страница ждала бы таймаута сети на каждом прогоне.
 */
function startServer(shellHtml) {
  const server = createServer(async (req, res) => {
    const urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);

    if (urlPath.startsWith('/api/')) {
      res.writeHead(503).end('prerender: backend not available');
      return;
    }

    if (extname(urlPath)) {
      const filePath = join(DIST, urlPath);
      try {
        await access(filePath);
        const body = await readFile(filePath);
        res.writeHead(200, { 'content-type': MIME[extname(urlPath)] || 'application/octet-stream' });
        res.end(body);
        return;
      } catch {
        res.writeHead(404).end('not found');
        return;
      }
    }

    res.writeHead(200, { 'content-type': MIME['.html'] });
    res.end(shellHtml);
  });

  return new Promise((ok, fail) => {
    server.once('error', fail);
    server.listen(PORT, '127.0.0.1', () => ok(server));
  });
}

/**
 * Проставляет метаданные в уже отрисованной странице.
 *
 * Выполняется В БРАУЗЕРЕ, на живом DOM, а не регуляркой по строке: head после
 * рендера содержит теги, которые React и шрифты добавили сами, и попытка
 * переписать его текстом — заведомо хрупкая.
 */
function applyMeta({ title, description, canonical, robots }) {
  const head = document.head;

  const setByAttr = (attr, key, value) => {
    let el = head.querySelector(`meta[${attr}="${key}"]`);
    if (!el) {
      el = document.createElement('meta');
      el.setAttribute(attr, key);
      head.appendChild(el);
    }
    el.setAttribute('content', value);
  };

  document.title = title;
  setByAttr('name', 'description', description);
  setByAttr('property', 'og:title', title);
  setByAttr('property', 'og:description', description);
  setByAttr('property', 'og:url', canonical);
  if (robots) setByAttr('name', 'robots', robots);

  let link = head.querySelector('link[rel="canonical"]');
  if (!link) {
    link = document.createElement('link');
    link.setAttribute('rel', 'canonical');
    head.appendChild(link);
  }
  link.setAttribute('href', canonical);
}

/**
 * Прокручивает страницу до низа и обратно наверх.
 *
 * ⚠️ Без этого шага пререндер лендинга даёт документ, где видна только первая
 * ширма. Секции ниже завёрнуты в motion-блоки с whileInView и вариантом
 * hidden: { opacity: 0 } (LandingPage.jsx) — они появляются, когда попадают в
 * окно просмотра, и до прокрутки остаются прозрачными. Это НЕ лечится
 * эмуляцией prefers-reduced-motion: сокращённый вариант убирает сдвиг по y, а
 * нулевую непрозрачность оставляет — то есть текст всё равно был бы невидим.
 *
 * Прокрутка честнее высокого окна просмотра: она не меняет раскладку, а
 * viewport на 20 000 пикселей изменил бы всё, что считается от высоты экрана.
 * viewport: { once: true } у этих блоков означает, что назад они не спрячутся.
 */
async function revealByScrolling() {
  const step = Math.round(window.innerHeight * 0.8);
  for (let y = 0; y < document.body.scrollHeight; y += step) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 120));
  }
  window.scrollTo(0, document.body.scrollHeight);
  await new Promise(r => setTimeout(r, 200));
  window.scrollTo(0, 0);
}

/**
 * Ищет текст, который остался прозрачным. Проверка факта, а не времени:
 * «подождали достаточно» доказывается состоянием документа, а не константой.
 */
function findHiddenText() {
  const out = [];
  for (const el of document.querySelectorAll('#root *')) {
    const text = (el.innerText || '').trim();
    if (text.length < 40) continue;
    // Берём только тех, у кого нулевая непрозрачность своя, а не унаследована
    // от родителя: иначе один прозрачный блок дал бы десяток жалоб подряд.
    if (parseFloat(getComputedStyle(el).opacity) > 0.01) continue;
    const parent = el.parentElement;
    if (parent && parseFloat(getComputedStyle(parent).opacity) <= 0.01) continue;
    out.push(`<${el.tagName.toLowerCase()}> ${text.slice(0, 60).replace(/\s+/g, ' ')}…`);
  }
  return out;
}

/**
 * Текст экрана «страница не найдена». Снимается ПЕРВЫМ и служит эталоном.
 *
 * ⚠️ Зачем: маршрут, который есть в routes.js, но отсутствует в роутере
 * App.jsx, отрисует catch-all NotFoundPage — и без этой сверки уедет на прод
 * как нормальная страница. Проверено обратным прогоном 14.09.2026: битый
 * маршрут дал 378 символов текста, прошёл порог в 80, получил свой title и
 * canonical и записался в dist. То есть в выдачу ушла бы страница «не
 * найдено» под видом тарифов — хуже, чем пустая.
 *
 * Сверяем ТЕКСТ, а не формулировку в коде: привязываться к самой фразе нельзя,
 * её правят. Совпадение с эталоном означает «роутер не знает этого адреса»
 * независимо от того, что там написано.
 */
async function capture(page, path, meta) {
  const res = await page.goto(`http://127.0.0.1:${PORT}${path}`, {
    waitUntil: 'networkidle2',
    timeout: 30_000,
  });
  if (!res || !res.ok()) {
    throw new Error(`${path}: сервер ответил ${res ? res.status() : 'ничем'}`);
  }

  await page.waitForFunction(
    () => {
      const root = document.getElementById('root');
      return root && root.children.length > 0 && root.innerText.trim().length > 0;
    },
    { timeout: 30_000 },
  );

  await page.evaluate(revealByScrolling);
  await new Promise(r => setTimeout(r, SETTLE_MS));
  await page.evaluate(applyMeta, meta);

  const html = await page.content();

  // Проверка факта, а не кода возврата: страница обязана нести текст.
  const text = await page.evaluate(() => document.getElementById('root').innerText.trim());
  if (text.length < 80) {
    throw new Error(`${path}: в #root всего ${text.length} символов текста — похоже, не отрисовалось`);
  }

  const hidden = await page.evaluate(findHiddenText);
  if (hidden.length) {
    throw new Error(
      `${path}: текст остался прозрачным (${hidden.length} шт.), снимок сделан до конца анимации.\n` +
      hidden.map(h => `      · ${h}`).join('\n'),
    );
  }

  return { html, textLength: text.length, text };
}

async function write(path, html) {
  // '/' → dist/index.html, '/pricing' → dist/pricing/index.html
  const target = path === '/'
    ? join(DIST, 'index.html')
    : join(DIST, path, 'index.html');
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html, 'utf-8');
  return target;
}

async function main() {
  if (!existsSync(join(DIST, 'index.html'))) {
    throw new Error('dist/index.html не найден — пререндер запускается ПОСЛЕ vite build');
  }

  // Чистый шелл сохраняем до того, как index.html будет перезаписан лендингом.
  const shellHtml = await readFile(join(DIST, 'index.html'), 'utf-8');
  await copyFile(join(DIST, 'index.html'), join(DIST, 'app.html'));

  const browserPath = findBrowser();
  const server = await startServer(shellHtml);
  // ⚠️ В stderr при запуске сыпется штатный шум snap-сборки chromium: жалобы
  // AppArmor и DBus (`ListActivatableNames`, `UPower`), строки вида
  // `mojo ... rejected by interface`. ЭТО ОЖИДАЕМО И ГАСИТЬ ЭТО НЕ НУЖНО.
  // Проверено на сервере 14.09.2026: HTML при этом идёт в stdout и корректен.
  //
  // Признак отказа здесь — код возврата и пустой результат, а НЕ непустой
  // stderr. Ни этот скрипт, ни 04-frontend-deploy.sh stderr не перехватывают
  // и по нему решений не принимают; puppeteer вычитывает из него строку
  // `DevTools listening on ws://…` и остальные строки пропускает. Если
  // кто-нибудь решит «навести порядок» и добавит проверку на пустой stderr —
  // деплой начнёт падать каждый раз, на здоровой сборке.
  //
  // ⚠️ `--no-sandbox` — НЕ небрежность и не «отключили защиту, чтобы
  // заработало». Snap-сборка chromium без него в headless не стартует вовсе:
  // её собственная песочница конфликтует с confinement'ом snap. Флаг
  // безопасен здесь по контексту: браузер открывает ровно один адрес —
  // http://127.0.0.1 с нашей же сборкой, без пользовательского ввода и без
  // внешней сети. Убирать нельзя, пререндер просто перестанет запускаться.
  //
  // ⚠️ `timeout: 120_000` — НЕ перестраховка, и срезать обратно к умолчанию
  // нельзя. Умолчание puppeteer — 30 секунд, и их не хватает на ХОЛОДНЫЙ
  // старт: snap-сборка chromium при первом запуске распаковывает и
  // монтирует свой squashfs, а на загруженной машине это занимает заметно
  // больше. Отказ 14.09.2026 выглядел так:
  //     Timed out after 30000 ms while waiting for the WS endpoint URL
  //     to appear in stdout!
  // Браузер при этом исправен — он просто не успел напечатать строку.
  //
  // ⚠️ Отказ этого класса выглядит как сломанный фронтенд, а не как
  // нехватка времени: падает шаг `npm run build`, в CI это красный
  // `test-frontend`, а `deploy` следом молча пропускается по `needs`.
  // Доказательство, что дело во времени, а не в коде: 14.09.2026 на ОДНОМ
  // И ТОМ ЖЕ коммите push-прогон прошёл, а шедший одновременно с ним
  // workflow_dispatch упал — два прогона делили раннер.
  //
  // Повтор ровно один и без паузы: если браузера нет или он неисправен,
  // вторая попытка провалится так же быстро, и сборка честно упадёт — а
  // цикл с паузами превратил бы понятный отказ в семиминутное ожидание.
  //
  // ⚠️ ЗДЕСЬ НЕ НУЖНО ДОБАВЛЯТЬ УБОРКУ ЗА БРАУЗЕРОМ. Выглядит так, будто при
  // таймауте запуска chromium остаётся жить: объекта браузера нам не вернули,
  // ссылки на процесс нет, а puppeteer внутри делает `void
  // browserCloseCallback()` — то есть запускает уборку и НЕ дожидается её
  // (BrowserLauncher.js:163). Вывод «значит, процессы копятся на сервере»
  // напрашивается сам и он НЕВЕРЕН.
  //
  // Проверено по исходникам и исполнением 15.09.2026 (puppeteer-core 23.11.1):
  // @puppeteer/browsers подписывается на события ПРОЦЕССА при каждом spawn —
  // `subscribeToProcessEvent('exit', …)`, а также на SIGINT/SIGTERM/SIGHUP
  // (launch.js:160-168). Обработчик зовёт `kill()`, и тот СИНХРОННЫЙ:
  // `execSync('taskkill /pid … /T /F')` на Windows и `process.kill(-pid,
  // 'SIGKILL')` по группе процессов на Linux (launch.js:247-283). Node зовёт
  // 'exit' синхронно в том числе из process.exit() — значит `process.exit(1)`
  // ниже не бросает браузер, а гарантированно его добивает.
  //
  // Обратный прогон (таймаут запуска подменён на 1 мс, обе попытки падают):
  // код возврата 1, процессов chromium не осталось ни одного, зависания нет.
  //
  // ⚠️ И наоборот: попытка «починить» это ломает сборку. Замена process.exit(1)
  // на process.exitCode = 1 (чтобы «дать уборке доработать») ОТКЛЮЧАЕТ именно
  // тот путь, которым браузер убивается, и node виснет навсегда: два
  // ChildProcess с открытыми пайпами держат цикл событий, сборка не падает, а
  // просто не заканчивается. Померено тем же обратным прогоном. Так что
  // process.exit(1) в конце файла — не небрежность, а условие корректности.
  const launchBrowser = () => puppeteer.launch({
    executablePath: browserPath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
    timeout: 120_000,
  });

  let browser;
  try {
    browser = await launchBrowser();
  } catch (err) {
    console.warn(`⚠️  chromium не стартовал с первой попытки (${err.message}); повторяю один раз`);
    browser = await launchBrowser();
  }

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });

    // Страница 404 снимается ПЕРВОЙ — её текст нужен как эталон для сверки
    // ниже. Адрес заведомо несуществующий: React-роутер отдаёт на него
    // NotFoundPage по маршруту '*'. Её же nginx отдаёт через error_page,
    // поэтому canonical ей не нужен, а noindex — нужен.
    const { html: notFound, text: notFoundText } = await capture(page, '/__prerender_404__', {
      title: 'Страница не найдена — Aristea Timeline',
      description: 'Такого адреса на сайте нет.',
      canonical: `${CANONICAL_ORIGIN}/`,
      robots: 'noindex, follow',
    });

    const targets = publicUrls();
    // Пустая выдача — тоже отказ, и молчаливый: цикл ниже просто не выполнился
    // бы, скрипт отчитался бы «0 страниц» с кодом 0, а на прод уехал бы сайт из
    // одних шеллов. Тот же мотив, что у проверки «разобрано больше двадцати
    // путей» в routes.test.js.
    if (targets.length === 0) {
      throw new Error('publicUrls() не вернул ни одного адреса — пререндерить нечего');
    }

    for (const { path, seo } of targets) {
      const canonical = `${CANONICAL_ORIGIN}${path === '/' ? '/' : path}`;
      const { html, textLength, text } = await capture(page, path, {
        title: seo.title,
        description: seo.description,
        canonical,
      });

      if (text === notFoundText) {
        throw new Error(
          `${path}: роутер отдал экран «страница не найдена».\n` +
          '      Маршрут есть в routes.js, но его нет в App.jsx — без этой проверки\n' +
          '      он уехал бы на прод как нормальная страница, со своим title и canonical.',
        );
      }

      const target = await write(path, html);
      console.log(`  ${path.padEnd(26)} ${String(textLength).padStart(6)} симв. → ${target.replace(DIST, 'dist')}`);
    }

    // canonical на главную с 404-страницы — ложь; убираем то, что проставили
    // ради переиспользования общей функции.
    await writeFile(
      join(DIST, '404.html'),
      notFound.replace(/<link rel="canonical"[^>]*>/, ''),
      'utf-8',
    );
    console.log(`  404                                  → dist/404.html`);
    console.log(`✅ пререндер: ${targets.length} страниц + 404`);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch(err => {
  console.error(`\n❌ пререндер не удался: ${err.message}\n`);
  process.exit(1);
});
