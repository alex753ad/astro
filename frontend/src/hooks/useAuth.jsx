/**
 * useAuth — central authentication hook.
 *
 * Manages:
 * - Access-токен (localStorage, 15 минут) + текущий пользователь
 * - Login / register / OAuth / logout
 * - Automatic token refresh before expiry
 * - Tier-based feature flags
 *
 * Refresh-токен в вебе здесь не хранится и не виден вовсе: сервер кладёт его в
 * HttpOnly-куку astro_refresh (Path=/api/v1/auth, SameSite=Strict). Раньше он
 * лежал в localStorage и жил 7 дней — то есть один XSS или одна испорченная
 * npm-зависимость давали неделю доступа к чужому аккаунту.
 *
 * В мобильной сборке куки нет (webview ходит кросс-сайтово, SameSite=Strict её
 * не отдаёт), поэтому refresh едет в теле ответа и хранится в нативном
 * хранилище устройства — весь этот путь в api/authTransport.js, в localStorage
 * он не попадает и там.
 */

import { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react';
import {
  ApiError,
  getSubscription,
  onSessionExpired,
  refreshSession,
  saveAnonymousChart,
} from '../api/client';
import {
  AUTH_CREDENTIALS,
  authRequestBody,
  clientHeaders,
  forgetRefreshToken,
  rememberRefreshToken,
} from '../api/authTransport';
import { API_BASE as CONFIG_API_BASE } from '../config';
import { diag } from '../lib/authDiag';
import { isTokenExpired, tokenExpiresAt } from '../lib/jwt';
import { REFRESH_BUFFER_MS, nextRefresh, retryDelay } from '../lib/refreshSchedule';
import { getRefCode } from '../utils/refCode';

const API_BASE = `${CONFIG_API_BASE}/auth`;

// ── Storage keys ──────────────────────────────────────────
const ACCESS_TOKEN_KEY  = 'astro_access_token';
const USER_KEY          = 'astro_user';
// Ключ прошлой схемы. Читать его больше нельзя (сервер такой токен всё равно
// отзовёт при первой ротации), но подчистить у вернувшихся пользователей стоит.
const LEGACY_REFRESH_KEY = 'astro_refresh_token';

// ── Context ───────────────────────────────────────────────
const AuthContext = createContext(null);

// ── Internal helpers ──────────────────────────────────────

function loadStored() {
  try {
    const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
    const user        = JSON.parse(localStorage.getItem(USER_KEY) || 'null');
    return { accessToken, user };
  } catch {
    return { accessToken: null, user: null };
  }
}

function saveTokens({ accessToken, user }) {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  localStorage.removeItem(LEGACY_REFRESH_KEY);
}

function clearStorage() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(LEGACY_REFRESH_KEY);
  // Кэш последней открытой карты (App.jsx Header) — без этого следующий
  // пользователь, вошедший на том же устройстве, на миг увидел бы чужой
  // chartId в навигации до того, как отработает серверная проверка.
  localStorage.removeItem('astro_last_chart_id');
  localStorage.removeItem('astro_last_chart_name');
}

async function apiFetch(path, options = {}) {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...clientHeaders(), ...options.headers },
    // Кука с refresh нужна на /refresh и /logout; по умолчанию fetch её не шлёт,
    // если API живёт на другом origin (dev-сервер, отдельный поддомен).
    // В мобильной сборке куки нет — там 'omit' и токен в теле, см. authTransport.js.
    credentials: AUTH_CREDENTIALS,
    ...options,
  });
  const body = await resp.json().catch(() => ({ detail: resp.statusText }));
  if (!resp.ok) {
    let msg = body.detail || resp.statusText;
    if (Array.isArray(msg)) msg = msg.map(e => e.msg?.replace(/^Value error, /, '') ?? e.msg ?? JSON.stringify(e)).join('; ');
    throw new ApiError(msg, resp.status, body);
  }
  return body;
}

// ── Default feature flags (до загрузки с сервера) ────────
const DEFAULT_FEATURES = {
  tier: 'free',
  transits: false,
  transits_ai: false,
  unlimited_interpretations: false,
  pdf_reports: false,
  synastry: false,
  interpretation_word_limit: 500,
  interpretations_per_month: 0,
  lunar_months: 1,
  planner_months: 0,
};

// ═══════════════════════════════════════════════════════════
// PROVIDER
// ═══════════════════════════════════════════════════════════

export function AuthProvider({ children }) {
  const auth = useAuthInternal();
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

// ═══════════════════════════════════════════════════════════
// HOOK
// ═══════════════════════════════════════════════════════════

function useAuthInternal() {
  const stored = loadStored();

  const [accessToken,  setAccessToken]  = useState(stored.accessToken);
  const [user,         setUser]         = useState(stored.user);
  const [features,     setFeatures]     = useState(stored.user ? DEFAULT_FEATURES : DEFAULT_FEATURES);
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState(null);

  const refreshTimerRef = useRef(null);
  // Сколько неудачных обновлений подряд — от этого зависит пауза перед
  // следующей попыткой. Обнуляется успехом и разлогином.
  const retriesRef = useRef(0);
  // doRefresh планирует ПОВТОР САМОГО СЕБЯ, а сослаться на себя внутри
  // useCallback нельзя. Ссылка через ref — не хитрость, а единственный
  // способ не разорвать цепочку на первой же неудаче.
  const doRefreshRef = useRef(null);

  const isAuthenticated = Boolean(accessToken && user);

  // Загрузить feature flags с сервера
  const loadFeatures = useCallback(async (token) => {
    if (!token) return;
    try {
      const data = await getSubscription(token);
      if (data?.features) setFeatures(data.features);
    } catch { /* тихо — используем DEFAULT_FEATURES */ }
  }, []);

  // ── Persist to localStorage on every change ──
  useEffect(() => {
    if (accessToken && user) {
      saveTokens({ accessToken, user });
    }
  }, [accessToken, user]);

  // ── Apply token data from API response ──────────────────
  const applyTokenResponse = useCallback(async (data) => {
    const newUser = {
      id:       data.user_id,
      email:    data.email,
      name:     data.name ?? null,
      tier:     data.tier,
      is_admin: data.is_admin ?? false,
      is_partner: data.is_partner ?? false,
    };
    setAccessToken(data.access_token);
    setUser(newUser);
    // Сохраняем сразу — не ждём useEffect
    saveTokens({ accessToken: data.access_token, user: newUser });
    // Мобильный клиент: refresh пришёл в теле и живёт в нативном хранилище.
    // Сервер ротирует его на каждом обновлении, поэтому сохранять надо здесь —
    // в единственной точке, через которую проходят и логин, и refresh, и OAuth.
    // В вебе это no-op: там data.refresh_token пуст, токен в куке.
    await rememberRefreshToken(data);
    scheduleRefresh(data.access_token);
    loadFeatures(data.access_token);

    // Bind anonymous chart after login/registration.
    // Возвращаем id привязанной карты через newUser.boundChartId, чтобы
    // AuthModal мог сразу перевести пользователя в его планер.
    const savedChart = localStorage.getItem('anonymous_chart');
    if (savedChart) {
      try {
        const { data: chartData, expiresAt } = JSON.parse(savedChart);
        if (Date.now() < expiresAt) {
          const saved = await saveAnonymousChart(chartData);
          localStorage.removeItem('anonymous_chart');
          if (saved?.id) newUser.boundChartId = saved.id;
        } else {
          localStorage.removeItem('anonymous_chart');
        }
      } catch {
        localStorage.removeItem('anonymous_chart');
      }
    }

    return newUser;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Automatic token refresh ─────────────────────────────
  // В вебе токен не передаём: сервер берёт его из HttpOnly-куки, которую
  // браузер приложит сам (credentials: 'include' в apiFetch). В мобильной
  // сборке куки нет, и токен уезжает в теле — authRequestBody() ниже.
  // Дедуп: несколько запросов, упавших в 401 одновременно (или таймер +
  // ручной вызов), не должны бить /refresh параллельно — ротация делает
  // использованный refresh недействительным, второй запрос разлогинил бы юзера.
  // ⚠️ Своего контура обновления здесь больше НЕТ — он единственный и живёт в
  // api/client.js (refreshSession). Раньше их было два, с независимыми
  // «идёт обновление»-флагами: они могли отправить один и тот же refresh
  // параллельно, сервер по reuse-detection отвечал 401 второму, и тот стирал
  // свежий токен, только что записанный первым. Приложение оставалось с
  // формально живым access и без refresh — то есть навсегда в состоянии
  // «вошёл», где не проходит ни один запрос. Разбор — в шапке того раздела
  // client.js.
  //
  // Возвращает результат целиком, а не токен: вызывающим важна ПРИЧИНА
  // неуспеха — от неё зависит, повторять ли попытку.
  const attemptRefresh = useCallback(async () => {
    const result = await refreshSession();
    if (result.ok) await applyTokenResponse(result.data);
    return result;
  }, [applyTokenResponse]);

  // ⚠️ Разлогин ТОЛЬКО по явному отказу аутентификации, и решение об этом
  // принимает не эта функция: refreshSession сама уведомляет подписчиков
  // (см. эффект с onSessionExpired ниже), а здесь остаётся молчание.
  // Потеря связи (самолётный режим, обрыв) и 429/5xx не должны выкидывать
  // человека на экран входа — там верное поведение «покажи ошибку и дай
  // повторить», а не «потеряй сессию».
  //
  // ⚠️ Неуспех ОБЯЗАН запланировать повтор. До 07.09.2026 эта функция
  // результат не читала вовсе, а следующий таймер ставило только успешное
  // обновление — то есть первая же временная ошибка (обрыв связи на секунду,
  // 429 от лимитера, заснувший на минуту webview) выключала автоматическое
  // обновление до перезапуска приложения. Молча: ни экрана, ни записи в
  // консоль, ни второй попытки. Сессия после этого доживала ровно до конца
  // текущего access-токена.
  const doRefresh = useCallback(async () => {
    diag('doRefresh:start');
    const result = await attemptRefresh();
    diag('doRefresh:end', result.ok ? 'ok' : `fail:${result.reason}`);

    // Успех сам поставит следующий таймер (applyTokenResponse → scheduleRefresh).
    // Отказ аутентификации повторять бессмысленно: сессии больше нет, разлогин
    // уже произошёл внутри refreshSession.
    if (result.ok || result.reason === 'auth') {
      retriesRef.current = 0;
      return;
    }

    const delay = retryDelay(retriesRef.current);
    diag('doRefresh:retry-scheduled', `через ${delay}мс, попытка ${retriesRef.current + 1}`);
    retriesRef.current += 1;
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => doRefreshRef.current?.(), delay);
  }, [attemptRefresh]);

  useEffect(() => { doRefreshRef.current = doRefresh; }, [doRefresh]);

  // ⚠️ Протухший токен обновляется НЕМЕДЛЕННО, а не игнорируется. Раньше здесь
  // стояло `if (delay > 0)` без else: при отрицательной задержке не ставилось
  // ничего и никто об этом не узнавал — «обновить прямо сейчас» превращалось
  // в «не делать ничего никогда». Само расписание — в lib/refreshSchedule.js,
  // там же тесты: внутри хука проверить его нечем, DOM-окружения для тестов в
  // проекте нет.
  const scheduleRefresh = useCallback((token) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);

    const next = nextRefresh(token);
    diag('schedule', next.kind === 'later' ? `later ${next.delay}мс` : next.kind);
    if (next.kind === 'never') return;
    if (next.kind === 'now') {
      doRefresh();
      return;
    }
    refreshTimerRef.current = setTimeout(() => {
      // Отметка стоит ВНУТРИ колбэка, а не рядом с setTimeout: вопрос замера
      // именно в том, выстреливает ли просроченный таймер после разморозки
      // webview, — а это видно только отсюда.
      diag('timer:fired');
      doRefresh();
    }, next.delay);
  }, [doRefresh]);

  // Schedule refresh on mount if token already in storage
  useEffect(() => {
    if (accessToken) {
      // Решение «сейчас / потом / никогда» принимает scheduleRefresh — одно
      // место на весь хук. Флаги тарифа тянем только живым токеном: с
      // протухшим запрос всё равно вернёт 401, а после успешного обновления
      // их подтянет applyTokenResponse.
      scheduleRefresh(accessToken);
      if (!isTokenExpired(accessToken)) loadFeatures(accessToken);
    }
    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Свёрнутая вкладка/приложение замораживает setTimeout — таймер из
  // scheduleRefresh может не выстрелить вовремя. При возврате в видимое
  // состояние проверяем срок токена по факту и обновляем, только если он
  // истёк или почти истёк — не дёргаем refresh на каждый фокус.
  useEffect(() => {
    function checkOnReturn(ev) {
      // Имя события в отметке обязательно: три слушателя ведут в одну
      // функцию, и вопрос замера — доставляет ли webview хоть одно из них
      // после разморозки. Отметка стоит ДО всех условий, иначе «событие не
      // пришло» и «пришло, но обновление не потребовалось» неотличимы.
      diag('resume', `${ev?.type ?? 'unknown'} visibility=${document.visibilityState}`);
      if (document.visibilityState !== 'visible') return;
      if (!accessToken) return;
      const expiresAt = tokenExpiresAt(accessToken);
      const left = Math.round((expiresAt - Date.now()) / 1000);
      if (Date.now() >= expiresAt - REFRESH_BUFFER_MS) {
        diag('resume:refresh', `до истечения ${left}с`);
        doRefresh();
      } else {
        diag('resume:skip', `до истечения ${left}с`);
      }
    }
    document.addEventListener('visibilitychange', checkOnReturn);
    window.addEventListener('focus', checkOnReturn);
    window.addEventListener('pageshow', checkOnReturn);
    return () => {
      document.removeEventListener('visibilitychange', checkOnReturn);
      window.removeEventListener('focus', checkOnReturn);
      window.removeEventListener('pageshow', checkOnReturn);
    };
  }, [accessToken, doRefresh]);


  // ── Auth actions ────────────────────────────────────────

  const register = useCallback(async (email, password) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch('/register', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      return applyTokenResponse(data);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [applyTokenResponse]);

  const login = useCallback(async (email, password) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch('/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      return applyTokenResponse(data);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [applyTokenResponse]);

  // ── Регистрация по OTP (шаг 1 и шаг 2) ──────────────────
  //
  // ⚠️ Обе ходят через apiFetch, а НЕ голым fetch, как это делает
  // AuthModal.jsx на вебе. apiFetch подмешивает clientHeaders(), то есть
  // X-Client-Platform: mobile — от этого заголовка зависит, придёт ли
  // refresh_token в теле ответа (_build_token_response, backend/auth/router.py).
  // Без него всё выглядит исправно: аккаунт создан, в приложение пустило, —
  // а через час истекает access, обновить его нечем (куку webview не
  // получает), и приложение молча разлогинивается. Разбор —
  // REGISTER_API_RECON.md §3.1-3.2.
  //
  // Здесь же apiFetch срезает у 422 префикс «Value error, » и склеивает
  // список ошибок pydantic в одну строку — поэтому экрану достаётся
  // готовый человеческий текст.
  //
  // setError/setLoading общего состояния хука эти две НЕ трогают, в отличие
  // от login/register: у двухшагового экрана свои состояния на каждый шаг
  // (ошибка ввода кода не должна выглядеть как ошибка формы и наоборот).
  const sendRegisterCode = useCallback(({ email, password, name, consent }) => (
    apiFetch('/register/email/send-code', {
      method: 'POST',
      // ref_code не отправляется вовсе (решение владельца 07.09.2026):
      // реферальные ссылки приходят на веб, в приложении его взять неоткуда.
      body: JSON.stringify({
        email,
        password,
        name: name || undefined,
        consent,
      }),
    })
  ), []);

  // Возвращает то же, что login: applyTokenResponse сохраняет access и
  // профиль, а на устройстве ещё и refresh в нативное хранилище. Раскладывать
  // токены руками нельзя — rememberRefreshToken живёт внутри неё.
  const verifyRegisterCode = useCallback(async ({ email, code }) => {
    const data = await apiFetch('/register/email/verify', {
      method: 'POST',
      body: JSON.stringify({ email, code }),
    });
    return applyTokenResponse(data);
  }, [applyTokenResponse]);

  const loginWithGoogle = useCallback(async (code, redirectUri) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch('/google', {
        method: 'POST',
        body: JSON.stringify({ code, redirect_uri: redirectUri, ref_code: getRefCode() || undefined }),
      });
      return applyTokenResponse(data);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [applyTokenResponse]);

  const logout = useCallback(() => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    // Отзываем токены на сервере (fire-and-forget, сессию чистим в любом случае).
    //
    // Порядок важен для мобильной сборки: тело запроса собирается из нативного
    // хранилища, поэтому чистить его можно только ПОСЛЕ того, как запрос
    // отправлен. Иначе выход перестанет отзывать refresh на сервере, и
    // «вышел из аккаунта» будет означать лишь очистку памяти устройства —
    // украденный до выхода токен продолжит работать неделю.
    try {
      const at = localStorage.getItem(ACCESS_TOKEN_KEY);
      if (at) {
        authRequestBody()
          .then((body) => fetch(`${API_BASE}/logout`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${at}`,
              ...clientHeaders(),
            },
            // В вебе refresh сервер возьмёт из куки и там же её погасит — телу
            // передавать нечего, но credentials обязателен, иначе кука не уедет.
            // На устройстве куки нет: токен уходит в теле.
            credentials: AUTH_CREDENTIALS,
            body,
            keepalive: true,
          }))
          .catch(() => {})
          .finally(() => { forgetRefreshToken().catch(() => {}); });
      } else {
        forgetRefreshToken().catch(() => {});
      }
    } catch { /* noop */ }
    setAccessToken(null);
    setUser(null);
    clearStorage();
  }, []);

  // ⚠️ ЕДИНСТВЕННАЯ точка, где приложение решает, что сессии больше нет.
  //
  // Сигнал приходит из refreshSession (api/client.js) и только по ЯВНОМУ
  // отказу сервера в аутентификации — не по сетевому сбою. Подписка нужна
  // потому, что запросы экранов идут через authFetch ТОГО ЖЕ МОДУЛЯ, минуя
  // этот хук: до 07.09.2026 отказ сервера там не приводил вообще ни к чему,
  // и приложение застревало в состоянии «вошёл» с мёртвым токеном — таб-бар
  // на месте, а на каждом экране «Не удалось загрузить…» и бесполезная
  // кнопка «Повторить». В mobile/ не было ни одного вызова logout(), и выйти
  // из этого состояния человек не мог даже перезапуском приложения.
  //
  // Стоит ПОСЛЕ объявления logout намеренно: `const` в TDZ, и подписка,
  // размещённая выше по файлу, падала бы с ReferenceError на первом рендере.
  useEffect(() => onSessionExpired(logout), [logout]);

  const clearError = useCallback(() => setError(null), []);

  // ── Authenticated fetch wrapper ─────────────────────────
  // Use this in other API calls that need the Bearer token
  const authFetch = useCallback(async (url, options = {}) => {
    if (!accessToken) throw new Error('Not authenticated');
    const send = (token) => fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...options.headers,
      },
    });

    let resp = await send(accessToken);
    if (resp.status === 401) {
      // Access-токен истёк (напр. приложение долго было свёрнуто) — одна
      // попытка обновиться и повторить запрос.
      //
      // ⚠️ logout() здесь больше НЕ вызывается: разлогин — одна точка, и она
      // подписана на refreshSession (см. onSessionExpired выше). Раньше
      // решение принималось и здесь тоже, причём по признаку «обновиться не
      // вышло», без различения причины — то есть обрыв связи выкидывал на
      // экран входа наравне с настоящим отказом сервера.
      const fresh = await attemptRefresh();
      if (!fresh.ok) throw new ApiError('Session expired', 401, {});
      resp = await send(fresh.data.access_token);
    }
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    if (!resp.ok) throw new ApiError(body.detail || resp.statusText, resp.status, body);
    return body;
  }, [accessToken, attemptRefresh]);

  // Точечное обновление полей пользователя (напр. имени) без повторного
  // логина — persist в localStorage делает уже существующий useEffect выше
  // (он реагирует на любое изменение user).
  const updateUser = useCallback((patch) => {
    setUser(prev => (prev ? { ...prev, ...patch } : prev));
  }, []);

  return {
    // State
    user,
    accessToken,
    isAuthenticated,
    loading,
    error,
    features,

    // Actions
    register,
    login,
    sendRegisterCode,
    verifyRegisterCode,
    loginWithGoogle,
    applyTokenResponse,
    logout,
    clearError,
    updateUser,

    // Utilities
    authFetch,
  };
}

// ═══════════════════════════════════════════════════════════
// PUBLIC HOOK
// ═══════════════════════════════════════════════════════════

/**
 * useAuth — consume the auth context.
 *
 * Must be used inside <AuthProvider>.
 *
 * @example
 * const { user, login, logout, isAuthenticated, features } = useAuth();
 */
export default function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within <AuthProvider>');
  }
  return ctx;
}
