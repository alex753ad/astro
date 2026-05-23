/**
 * useExpertMode.js
 *
 * Управляет режимом эксперта (показ AspectTable).
 *
 * 1. Мгновенно читает из localStorage — нет мерцания при перезагрузке.
 * 2. Если передан userId — подтягивает значение из профиля при монтировании
 *    (GET /api/v1/profile/settings). Серверное значение побеждает локальное.
 * 3. Каждое переключение пишет в localStorage И фоново в профиль (PATCH).
 *
 * Использует ключ токена 'astro_access_token' — как в useAuth.js.
 */

import { useState, useEffect, useCallback } from 'react';

const LS_KEY    = 'astro_expert_mode';
const TOKEN_KEY = 'astro_access_token'; // совпадает с ACCESS_TOKEN_KEY в useAuth.js

export function useExpertMode(userId = null) {
  const [expertMode, setExpertMode] = useState(() => {
    try {
      return localStorage.getItem(LS_KEY) === 'true';
    } catch {
      return false;
    }
  });

  // При наличии авторизации — синхронизируем с сервером
  useEffect(() => {
    if (!userId) return;

    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return;

    fetch('/api/v1/profile/settings', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && typeof data.expert_mode === 'boolean') {
          setExpertMode(data.expert_mode);
          try {
            localStorage.setItem(LS_KEY, String(data.expert_mode));
          } catch {}
        }
      })
      .catch(() => {});
  }, [userId]);

  const toggleExpertMode = useCallback(() => {
    setExpertMode((prev) => {
      const next = !prev;

      try {
        localStorage.setItem(LS_KEY, String(next));
      } catch {}

      if (userId) {
        const token = localStorage.getItem(TOKEN_KEY);
        if (token) {
          fetch('/api/v1/profile/settings', {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ expert_mode: next }),
          }).catch(() => {});
        }
      }

      return next;
    });
  }, [userId]);

  return { expertMode, toggleExpertMode };
}
