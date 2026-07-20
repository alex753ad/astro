/**
 * useAuth — central authentication hook.
 *
 * Manages:
 * - JWT access + refresh tokens (localStorage)
 * - Current user state (email, tier, id)
 * - Login / register / OAuth / logout
 * - Automatic token refresh before expiry
 * - Tier-based feature flags
 */

import { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react';
import { ApiError, getSubscription, saveAnonymousChart } from '../api/client';

const API_BASE = 'https://astro-production-abcc.up.railway.app/api/v1/auth';

// ── Storage keys ──────────────────────────────────────────
const ACCESS_TOKEN_KEY  = 'astro_access_token';
const REFRESH_TOKEN_KEY = 'astro_refresh_token';
const USER_KEY          = 'astro_user';

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
    const accessToken  = localStorage.getItem(ACCESS_TOKEN_KEY);
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    const user         = JSON.parse(localStorage.getItem(USER_KEY) || 'null');
    return { accessToken, refreshToken, user };
  } catch {
    return { accessToken: null, refreshToken: null, user: null };
  }
}

function saveTokens({ accessToken, refreshToken, user }) {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearStorage() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function apiFetch(path, options = {}) {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
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
  const [refreshToken, setRefreshToken] = useState(stored.refreshToken);
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
    if (accessToken && refreshToken && user) {
      saveTokens({ accessToken, refreshToken, user });
    }
  }, [accessToken, refreshToken, user]);

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
    setRefreshToken(data.refresh_token);
    setUser(newUser);
    // Сохраняем сразу — не ждём useEffect
    saveTokens({ accessToken: data.access_token, refreshToken: data.refresh_token, user: newUser });
    scheduleRefresh(data.access_token, data.refresh_token);
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
  const doRefresh = useCallback(async (currentRefreshToken) => {
    try {
      const data = await apiFetch('/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: currentRefreshToken }),
      });
      applyTokenResponse(data);
    } catch {
      // Refresh failed — clear session
      logout();
    }
  }, [applyTokenResponse]); // eslint-disable-line react-hooks/exhaustive-deps

  const scheduleRefresh = useCallback((token, currentRefreshToken) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);

    const expiresAt = tokenExpiresAt(token);
    const delay     = expiresAt - Date.now() - REFRESH_BUFFER_MS;

    if (delay > 0) {
      refreshTimerRef.current = setTimeout(
        () => doRefresh(currentRefreshToken),
        delay,
      );
    }
  }, [doRefresh]);

  // Schedule refresh on mount if token already in storage
  useEffect(() => {
    if (accessToken && refreshToken) {
      const expiresAt = tokenExpiresAt(accessToken);
      if (Date.now() >= expiresAt) {
        doRefresh(refreshToken);
      } else {
        scheduleRefresh(accessToken, refreshToken);
        loadFeatures(accessToken);
      }
    }
    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
        body: JSON.stringify({ code, redirect_uri: redirectUri }),
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
      const rt = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (at) {
        fetch(`${API_BASE}/logout`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${at}`,
          },
          body: JSON.stringify({ refresh_token: rt || '' }),
          keepalive: true,
        }).catch(() => {});
      }
    } catch { /* noop */ }
    setAccessToken(null);
    setRefreshToken(null);
    setUser(null);
    clearStorage();
  }, []);

  const clearError = useCallback(() => setError(null), []);

  // ── Authenticated fetch wrapper ─────────────────────────
  // Use this in other API calls that need the Bearer token
  const authFetch = useCallback(async (url, options = {}) => {
    if (!accessToken) throw new Error('Not authenticated');
    const resp = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
        ...options.headers,
      },
    });
    if (resp.status === 401) {
      logout();
      throw new ApiError('Session expired', 401, {});
    }
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    if (!resp.ok) throw new ApiError(body.detail || resp.statusText, resp.status, body);
    return body;
  }, [accessToken, logout]);

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
