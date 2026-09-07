/**
 * session.test.js — обновление сессии: гонка контуров и реакция на отказ.
 *
 * Оба проверяемых дефекта найдены приёмкой регистрации на устройстве
 * 07.09.2026 и проявлялись одинаково: приложение застревало в состоянии
 * «вошёл» с мёртвым токеном — таб-бар на месте, а на каждом экране
 * «Не удалось загрузить…» и бесполезная кнопка «Повторить». Перезапуск не
 * помогал.
 *
 *   1. Контуров обновления было ДВА (этот модуль и свой в useAuth) с
 *      независимыми флагами «идёт обновление». Они могли отправить один и
 *      тот же refresh параллельно; сервер по reuse-detection отвечал 401
 *      второму, и проигравший стирал свежий токен победителя.
 *   2. Отказ сервера не приводил ни к чему: в mobile/ не было ни одного
 *      вызова logout().
 *
 * ⚠️ Третье требование, без которого лечение стало бы новым дефектом:
 * сетевой сбой НЕ должен выкидывать на экран входа. Человек в метро теряет
 * связь, а не сессию.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ACCESS_KEY = 'astro_access_token';

// Нативное хранилище refresh — подменяется целиком: настоящее тянет
// @capacitor/preferences, которого в тестовой среде нет.
const native = { token: null };
vi.mock('./authTransport', () => ({
  IS_MOBILE: true,
  AUTH_CREDENTIALS: 'omit',
  MOBILE_CLIENT_HEADER: 'X-Client-Platform',
  clientHeaders: () => ({ 'X-Client-Platform': 'mobile' }),
  authRequestBody: async () => JSON.stringify(
    native.token ? { refresh_token: native.token } : {},
  ),
  readRefreshToken: async () => native.token,
  rememberRefreshToken: async (data) => {
    if (data?.refresh_token) native.token = data.refresh_token;
  },
  forgetRefreshToken: async () => { native.token = null; },
}));

function installStorage(initial = {}) {
  const store = new Map(Object.entries(initial));
  vi.stubGlobal('localStorage', {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  });
  return store;
}

/** Свежий импорт: refreshInFlight — модульное состояние. */
async function freshClient() {
  vi.resetModules();
  return import('./client');
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

beforeEach(() => {
  native.token = 'refresh-1';
  installStorage({ [ACCESS_KEY]: 'access-old' });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('контур обновления один, а не два', () => {
  it('параллельные вызовы шлют ОДИН запрос и не затирают токен друг друга', async () => {
    // Ровно тот сценарий, что ломал сессию: два обновления стартуют
    // одновременно. Если каждый отправит свой запрос, сервер ротирует токен и
    // второму ответит 401 «уже использован» — а тот сотрёт свежий refresh.
    const { refreshSession } = await freshClient();

    let calls = 0;
    vi.stubGlobal('fetch', vi.fn(async () => {
      calls += 1;
      // Ответ второго вызова, если бы он случился, — отказ reuse-detection.
      if (calls > 1) return jsonResponse(401, { detail: 'Refresh token уже использован.' });
      return jsonResponse(200, { access_token: 'access-new', refresh_token: 'refresh-2' });
    }));

    const [a, b, c] = await Promise.all([
      refreshSession(), refreshSession(), refreshSession(),
    ]);

    expect(calls).toBe(1);
    expect(a.ok && b.ok && c.ok).toBe(true);
    expect(localStorage.getItem(ACCESS_KEY)).toBe('access-new');
    // Главное: свежий refresh на месте, его никто не стёр.
    expect(native.token).toBe('refresh-2');
  });

  it('после завершения обновления следующий вызов идёт заново', async () => {
    // Дедуп не должен превратиться в «обновляем один раз за жизнь процесса».
    const { refreshSession } = await freshClient();
    const fetchMock = vi.fn(async () => jsonResponse(200, {
      access_token: 'access-new', refresh_token: 'refresh-2',
    }));
    vi.stubGlobal('fetch', fetchMock);

    await refreshSession();
    await refreshSession();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe('различение причин отказа', () => {
  it('401 — сессия кончилась: токены стёрты, подписчики уведомлены', async () => {
    const { refreshSession, onSessionExpired } = await freshClient();
    const expired = vi.fn();
    onSessionExpired(expired);
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, { detail: 'Сессия отозвана.' })));

    const result = await refreshSession();

    expect(result).toEqual({ ok: false, reason: 'auth' });
    expect(expired).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(ACCESS_KEY)).toBeNull();
    expect(native.token).toBeNull();
  });

  it('сетевой сбой НЕ трогает токены и НЕ разлогинивает', async () => {
    // Самолётный режим. Раньше эта ветка молча возвращала null, а вызывающий
    // трактовал это как смерть сессии.
    const { refreshSession, onSessionExpired } = await freshClient();
    const expired = vi.fn();
    onSessionExpired(expired);
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));

    const result = await refreshSession();

    expect(result).toEqual({ ok: false, reason: 'network' });
    expect(expired).not.toHaveBeenCalled();
    expect(localStorage.getItem(ACCESS_KEY)).toBe('access-old');
    expect(native.token).toBe('refresh-1');
  });

  it('429 от лимитера — не разлогин: сервер жив, сессия цела', async () => {
    const { refreshSession, onSessionExpired } = await freshClient();
    const expired = vi.fn();
    onSessionExpired(expired);
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(429, { error: 'Rate limit exceeded' })));

    const result = await refreshSession();

    expect(result).toEqual({ ok: false, reason: 'server' });
    expect(expired).not.toHaveBeenCalled();
    expect(native.token).toBe('refresh-1');
  });

  it('5xx — тоже не разлогин', async () => {
    const { refreshSession, onSessionExpired } = await freshClient();
    const expired = vi.fn();
    onSessionExpired(expired);
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(503, {})));

    expect((await refreshSession()).reason).toBe('server');
    expect(expired).not.toHaveBeenCalled();
    expect(localStorage.getItem(ACCESS_KEY)).toBe('access-old');
  });
});

describe('authFetch — поведение экранов', () => {
  it('401 на запросе: обновился и повторил с новым токеном', async () => {
    const { authFetch } = await freshClient();
    const seen = [];
    vi.stubGlobal('fetch', vi.fn(async (url, opts) => {
      if (String(url).endsWith('/auth/refresh')) {
        return jsonResponse(200, { access_token: 'access-new', refresh_token: 'refresh-2' });
      }
      seen.push(opts.headers.Authorization);
      return seen.length === 1 ? jsonResponse(401, {}) : jsonResponse(200, { ok: true });
    }));

    const resp = await authFetch('https://api.example/profile');

    expect(resp.status).toBe(200);
    expect(seen).toEqual(['Bearer access-old', 'Bearer access-new']);
  });

  it('401 и мёртвый refresh: приложение разлогинивается', async () => {
    // Это и есть выход из тупика, в котором застревало приложение.
    const { authFetch, onSessionExpired } = await freshClient();
    const expired = vi.fn();
    onSessionExpired(expired);
    vi.stubGlobal('fetch', vi.fn(async (url) => (
      String(url).endsWith('/auth/refresh')
        ? jsonResponse(401, { detail: 'Refresh token уже использован.' })
        : jsonResponse(401, {})
    )));

    const resp = await authFetch('https://api.example/profile');

    expect(resp.status).toBe(401);
    expect(expired).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(ACCESS_KEY)).toBeNull();
  });

  it('401, но обновление не дошло по сети: сессия сохраняется', async () => {
    // Экран покажет ошибку с «Повторить», человек останется в аккаунте.
    const { authFetch, onSessionExpired } = await freshClient();
    const expired = vi.fn();
    onSessionExpired(expired);
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      if (String(url).endsWith('/auth/refresh')) throw new TypeError('Failed to fetch');
      return jsonResponse(401, {});
    }));

    const resp = await authFetch('https://api.example/profile');

    expect(resp.status).toBe(401);
    expect(expired).not.toHaveBeenCalled();
    expect(localStorage.getItem(ACCESS_KEY)).toBe('access-old');
    expect(native.token).toBe('refresh-1');
  });

  it('сетевой сбой самого запроса не трогает сессию', async () => {
    const { authFetch, onSessionExpired } = await freshClient();
    const expired = vi.fn();
    onSessionExpired(expired);
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));

    await expect(authFetch('https://api.example/profile')).rejects.toThrow();
    expect(expired).not.toHaveBeenCalled();
    expect(localStorage.getItem(ACCESS_KEY)).toBe('access-old');
  });

  it('без токена обновление не запускается', async () => {
    // Аноним получает 401 на защищённой ручке — это не повод дёргать refresh.
    installStorage({});
    const { authFetch } = await freshClient();
    const fetchMock = vi.fn(async () => jsonResponse(401, {}));
    vi.stubGlobal('fetch', fetchMock);

    await authFetch('https://api.example/profile');

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
