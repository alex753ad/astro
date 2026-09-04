/**
 * check-mobile-auth.mjs — живая проверка мобильного транспорта токенов на бою.
 *
 * Повторяет ровно ту последовательность HTTP-запросов, которую делает
 * приложение: логин с заголовком X-Client-Platform, хранение refresh «на
 * устройстве» (здесь — в памяти процесса), обновление access после истечения,
 * выход с отзывом refresh на сервере.
 *
 * Зачем отдельно от pytest: тесты ходят в TestClient, где нет ни nginx, ни
 * CORS, ни реального TLS, ни настоящего истечения токена. Зелёные тесты
 * доказывают логику, а не то, что она работает на боевом домене.
 *
 * Учётные данные — из .env в корне репозитория, в репозиторий не попадают:
 *
 *     TEST_ACCOUNT_EMAIL=...
 *     TEST_ACCOUNT_PASSWORD=...
 *
 * Запуск:
 *     node scripts/check-mobile-auth.mjs            # ждёт истечения access (15 мин)
 *     node scripts/check-mobile-auth.mjs --no-wait  # без ожидания, короткий прогон
 *
 * Ожидание включено по умолчанию намеренно: смысл всей задачи в том, что через
 * час пользователя не выбросит, а без истёкшего access проверяется только
 * счастливый путь.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const API = process.env.API_BASE || 'https://www.aristeatime.ru/api/v1';
const MOBILE = { 'X-Client-Platform': 'mobile' };
const WAIT = !process.argv.includes('--no-wait');

// ── .env ──────────────────────────────────────────────────────────────────────
function readEnv() {
  const out = {};
  try {
    for (const line of readFileSync(path.join(ROOT, '.env'), 'utf-8').split('\n')) {
      const s = line.trim();
      if (!s || s.startsWith('#') || !s.includes('=')) continue;
      const i = s.indexOf('=');
      out[s.slice(0, i).trim()] = s.slice(i + 1).trim().replace(/^["']|["']$/g, '');
    }
  } catch { /* .env может не быть — проверим ниже */ }
  return out;
}

const env = readEnv();
const EMAIL = process.env.TEST_ACCOUNT_EMAIL || env.TEST_ACCOUNT_EMAIL;
const PASSWORD = process.env.TEST_ACCOUNT_PASSWORD || env.TEST_ACCOUNT_PASSWORD;

if (!EMAIL || !PASSWORD) {
  console.error(
    'Нужны TEST_ACCOUNT_EMAIL и TEST_ACCOUNT_PASSWORD в .env (или в окружении).\n' +
    'Заведите служебный аккаунт обычной регистрацией на ' + API.replace('/api/v1', '') + '.',
  );
  process.exit(2);
}

// ── Мини-фреймворк ────────────────────────────────────────────────────────────
let failed = 0;

function check(name, ok, detail = '') {
  console.log(`${ok ? '✓' : '✗'} ${name}${detail ? ' — ' + detail : ''}`);
  if (!ok) failed += 1;
}

function jwtExp(token) {
  const [, payload] = token.split('.');
  const json = JSON.parse(Buffer.from(payload, 'base64url').toString('utf-8'));
  return json.exp * 1000;
}

async function post(path_, { body = {}, headers = {}, bearer = null } = {}) {
  const resp = await fetch(`${API}${path_}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
      ...headers,
    },
    body: JSON.stringify(body),
  });
  const text = await resp.text();
  let json = null;
  try { json = JSON.parse(text); } catch { /* не JSON */ }
  return { status: resp.status, json, text, headers: resp.headers };
}

async function get(path_, bearer) {
  const resp = await fetch(`${API}${path_}`, {
    headers: { ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}), ...MOBILE },
  });
  return { status: resp.status };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── Проверки ──────────────────────────────────────────────────────────────────
async function main() {
  console.log(`API: ${API}`);
  console.log(`Аккаунт: ${EMAIL.replace(/(.{2}).*(@.*)/, '$1***$2')}\n`);

  // 1. Веб-путь не изменился: без заголовка refresh в теле не приходит.
  const web = await post('/auth/login', { body: { email: EMAIL, password: PASSWORD } });
  check('логин БЕЗ заголовка: 200', web.status === 200, `status=${web.status}`);
  check('логин БЕЗ заголовка: refresh в теле НЕ приходит', !web.json?.refresh_token);
  check(
    'логин БЕЗ заголовка: кука astro_refresh ставится',
    (web.headers.get('set-cookie') || '').includes('astro_refresh'),
  );

  // 2. Мобильный путь: refresh приходит в теле.
  const login = await post('/auth/login', {
    body: { email: EMAIL, password: PASSWORD },
    headers: MOBILE,
  });
  check('логин С заголовком: 200', login.status === 200, `status=${login.status}`);
  const access = login.json?.access_token;
  let refresh = login.json?.refresh_token;
  check('логин С заголовком: refresh пришёл в теле', Boolean(refresh));
  if (!refresh) {
    console.error('\nБез refresh дальше проверять нечего.');
    process.exit(1);
  }

  // 3. Access работает.
  check('access работает на /auth/me', (await get('/auth/me', access)).status === 200);

  // 4. Истечение access — то, ради чего всё затевалось.
  const expAt = jwtExp(access);
  const lifetimeMin = Math.round((expAt - Date.now()) / 60000);
  console.log(`\nAccess истекает через ~${lifetimeMin} мин.`);

  if (WAIT) {
    const waitMs = expAt - Date.now() + 5000; // +5 с, чтобы точно перевалить exp
    console.log(`Жду истечения (${Math.ceil(waitMs / 1000)} с). Прервать — Ctrl+C, или запустите с --no-wait.`);
    const started = Date.now();
    while (Date.now() - started < waitMs) {
      await sleep(30000);
      const left = Math.ceil((waitMs - (Date.now() - started)) / 1000);
      if (left > 0) process.stdout.write(`  осталось ${left} с\n`);
    }
    const dead = await get('/auth/me', access);
    check('протухший access отвергается (401)', dead.status === 401, `status=${dead.status}`);
  } else {
    console.log('Ожидание пропущено (--no-wait): истечение access НЕ проверено.\n');
  }

  // 5. Обновление по сохранённому refresh — без куки, как на устройстве.
  const refreshed = await post('/auth/refresh', {
    body: { refresh_token: refresh },
    headers: MOBILE,
  });
  check('обновление токена: 200', refreshed.status === 200, `status=${refreshed.status}`);
  const access2 = refreshed.json?.access_token;
  const refresh2 = refreshed.json?.refresh_token;
  check('обновление токена: новый access выдан', Boolean(access2));
  check('обновление токена: новый refresh выдан', Boolean(refresh2));
  check('обновление токена: refresh ротирован', refresh2 && refresh2 !== refresh);
  check('новый access работает', (await get('/auth/me', access2)).status === 200);

  // 6. Ротация: старый refresh обязан быть мёртв.
  const reused = await post('/auth/refresh', {
    body: { refresh_token: refresh },
    headers: MOBILE,
  });
  check('использованный refresh отвергается (401)', reused.status === 401, `status=${reused.status}`);

  refresh = refresh2;

  // 7. Выход обязан гасить refresh на сервере, а не только локально.
  const out = await post('/auth/logout', {
    body: { refresh_token: refresh },
    headers: MOBILE,
    bearer: access2,
  });
  check('logout: 200', out.status === 200, `status=${out.status}`);

  const afterLogout = await post('/auth/refresh', {
    body: { refresh_token: refresh },
    headers: MOBILE,
  });
  check(
    'после logout refresh мёртв (401)',
    afterLogout.status === 401,
    `status=${afterLogout.status}`,
  );

  console.log(`\n${failed ? `ПРОВАЛЕНО: ${failed}` : 'Все проверки пройдены'}`);
  process.exit(failed ? 1 : 0);
}

main().catch((err) => {
  console.error('\nСбой прогона:', err);
  process.exit(1);
});
