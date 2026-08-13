/**
 * useAuth — central authentication hook.
 *
 * Manages:
 * - Access-токен (localStorage, 15 минут) + текущий пользователь
 * - Login / register / OAuth / logout
 * - Automatic token refresh before expiry
 * - Tier-based feature flags
 *
 * Refresh-токен здесь не хранится и не виден вовсе: сервер кладёт его в
 * HttpOnly-куку astro_refresh (Path=/api/v1/auth, SameSite=Strict). Раньше он
 * лежал в localStorage и жил 7 дней — то есть один XSS или одна испорченная
 * npm-зависимость давали неделю доступа к чужому аккаунту.
 */

import { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react';
import { ApiError, getSubscription, saveAnonymousChart } from '../api/client';
import { API_BASE as CONFIG_API_BASE } from '../config';
import { getRefCode } from '../utils/refCode';

const API_BASE = `${CONFIG_API_BASE}/auth`;

// ── Storage keys ──────────────────────────────────────────
const ACCESS_TOKEN_KEY  = 'astro_access_token';
const USER_KEY          = 'astro_user';
// Ключ прошлой схемы. Читать его больше нельзя (сервер такой токен всё равно
// отзовёт при первой ротации), но подчистить у вернувшихся пользователей стоит.
const LEGACY_REFRESH_KEY = 'astro_refresh_token';

// Refresh 2 minutes before access token expires (token lifetime = 15 min)
const REFRESH_BUFFER_MS = 2 * 60 * 1000;

// ── Context ───────────────────────────────────────────────
const AuthContext = createContext(null);

// ── Internal helpers ──────────────────────────────────────

function parseJwtPayload(token) {
  try {
    return JSON.parse(atob(token.split('.')[1]));
  } catch {
    return null;
  }
}

function tokenExpiresAt(token) {
  const payload = parseJwtPayload(token);
  return payload?.exp ? payload.exp * 1000 : 0;
}

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
    headers: { 'Content-Type': 'application/json', ...options.headers },
    // Кука с refresh нужна на /refresh и /logout; по умолчанию fetch её не шлёт,
    // если API живёт на другом origin (dev-сервер, отдельный поддомен).
    credentials: 'include',
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
  charts_per_month: null,
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
    };
    setAccessToken(data.access_token);
    setUser(newUser);
    // Сохраняем сразу — не ждём useEffect
    saveTokens({ accessToken: data.access_token, user: newUser });
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
  // Токен не передаём: сервер берёт его из HttpOnly-куки, которую браузер
  // приложит сам (credentials: 'include' в apiFetch).
  // Дедуп: несколько запросов, упавших в 401 одновременно (или таймер +
  // ручной вызов), не должны бить /refresh параллельно — ротация делает
  // использованный refresh недействительным, второй запрос разлогинил бы юзера.
  const refreshInFlightRef = useRef(null);

  const attemptRefresh = useCallback(() => {
    if (refreshInFlightRef.current) return refreshInFlightRef.current;
    refreshInFlightRef.current = (async () => {
      try {
        const data = await apiFetch('/refresh', {
          method: 'POST',
          body: JSON.stringify({}),
        });
        await applyTokenResponse(data);
        return data.access_token;
      } catch {
        return null;
      } finally {
        refreshInFlightRef.current = null;
      }
    })();
    return refreshInFlightRef.current;
  }, [applyTokenResponse]);

  const doRefresh = useCallback(async () => {
    const token = await attemptRefresh();
    if (!token) logout();
  }, [attemptRefresh]); // eslint-disable-line react-hooks/exhaustive-deps

  const scheduleRefresh = useCallback((token) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);

    const expiresAt = tokenExpiresAt(token);
    const delay     = expiresAt - Date.now() - REFRESH_BUFFER_MS;

    if (delay > 0) {
      refreshTimerRef.current = setTimeout(doRefresh, delay);
    }
  }, [doRefresh]);

  // Schedule refresh on mount if token already in storage
  useEffect(() => {
    if (accessToken) {
      const expiresAt = tokenExpiresAt(accessToken);
      if (Date.now() >= expiresAt) {
        doRefresh();
      } else {
        scheduleRefresh(accessToken);
        loadFeatures(accessToken);
      }
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
    function checkOnReturn() {
      if (document.visibilityState !== 'visible') return;
      if (!accessToken) return;
      const expiresAt = tokenExpiresAt(accessToken);
      if (Date.now() >= expiresAt - REFRESH_BUFFER_MS) {
        doRefresh();
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
    try {
      const at = localStorage.getItem(ACCESS_TOKEN_KEY);
      if (at) {
        fetch(`${API_BASE}/logout`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${at}`,
          },
          // Refresh сервер возьмёт из куки и там же её погасит — телу передавать
          // нечего. credentials обязателен, иначе кука не уедет.
          credentials: 'include',
          body: JSON.stringify({}),
          keepalive: true,
        }).catch(() => {});
      }
    } catch { /* noop */ }
    setAccessToken(null);
    setUser(null);
    clearStorage();
  }, []);

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
      // попытка обновиться и повторить запрос, прежде чем разлогинивать.
      const fresh = await attemptRefresh();
      if (!fresh) {
        logout();
        throw new ApiError('Session expired', 401, {});
      }
      resp = await send(fresh);
    }
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    if (!resp.ok) throw new ApiError(body.detail || resp.statusText, resp.status, body);
    return body;
  }, [accessToken, attemptRefresh, logout]);

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
