/**
 * useGoogleCalendar.js
 * OAuth 2.0 (implicit flow) + создание событий в Google Calendar.
 *
 * Использование:
 *   const { exportToCalendar, status } = useGoogleCalendar();
 *   await exportToCalendar(events);  // events — массив из data.events
 *
 * Требует: VITE_GOOGLE_CLIENT_ID в .env
 * Scope: https://www.googleapis.com/auth/calendar.events
 */

import { useRef, useState } from 'react';

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const SCOPE     = 'https://www.googleapis.com/auth/calendar.events';

// Описания типов событий для Calendar
const EVENT_CONFIG = {
  new_moon:  { emoji: '🌑', summary: prefix => `🌑 Новолуние — ${prefix}`, color: 3 /* grape */ },
  full_moon: { emoji: '🌕', summary: prefix => `🌕 Полнолуние — ${prefix}`, color: 5 /* banana */ },
  ingress:   { emoji: '➡️', summary: prefix => `➡️ ${prefix}`,              color: 1 /* lavender */ },
  aspect:    { emoji: '⚡',  summary: prefix => `⚡ ${prefix}`,              color: 6 /* tangerine */ },
};

export function useGoogleCalendar() {
  const [status, setStatus] = useState('idle'); // idle | loading | success | error
  const tokenRef = useRef(null);

  /**
   * Получить access token через popup (implicit grant).
   * Если токен уже есть — вернуть его.
   */
  function getToken() {
    return new Promise((resolve, reject) => {
      if (tokenRef.current) return resolve(tokenRef.current);

      const params = new URLSearchParams({
        client_id:     CLIENT_ID,
        redirect_uri:  window.location.origin,
        response_type: 'token',
        scope:         SCOPE,
        prompt:        'select_account',
      });

      const popup = window.open(
        `https://accounts.google.com/o/oauth2/v2/auth?${params}`,
        'gcal_oauth',
        'width=500,height=620,left=200,top=100'
      );

      const timer = setInterval(() => {
        try {
          const url = popup?.location?.href || '';
          if (url.includes('access_token')) {
            clearInterval(timer);
            popup.close();
            const hash   = new URLSearchParams(url.split('#')[1]);
            const token  = hash.get('access_token');
            const expiry = Date.now() + Number(hash.get('expires_in') || 3600) * 1000;
            tokenRef.current = { token, expiry };
            resolve(tokenRef.current);
          }
          if (popup?.closed && !url.includes('access_token')) {
            clearInterval(timer);
            reject(new Error('Авторизация отменена'));
          }
        } catch (_) { /* cross-origin, ждём */ }
      }, 300);
    });
  }

  /**
   * Создать одно событие в Google Calendar.
   * event: { date, type, description, sign? }
   */
  async function createEvent(accessToken, event) {
    const cfg     = EVENT_CONFIG[event.type] || EVENT_CONFIG.aspect;
    const label   = event.description || event.sign || '';
    const dateStr = event.date?.slice(0, 10); // 'YYYY-MM-DD'
    if (!dateStr) return;

    const body = {
      summary:     cfg.summary(label),
      description: event.description || '',
      start:       { date: dateStr },
      end:         { date: dateStr },
      colorId:     String(cfg.color),
      reminders:   { useDefault: false },
    };

    const res = await fetch(
      'https://www.googleapis.com/calendar/v3/calendars/primary/events',
      {
        method:  'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      }
    );

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      // 401 — токен протух, сбрасываем
      if (res.status === 401) tokenRef.current = null;
      throw new Error(err?.error?.message || `HTTP ${res.status}`);
    }
    return res.json();
  }

  /**
   * Главный экспорт: авторизация → создание всех событий.
   * events — data.events из AstroCalendar
   * month  — строка "YYYY-MM" для лога
   * authToken — JWT пользователя из useAuth
   */
  async function exportToCalendar(events, month, authToken) {
    if (!events?.length) return;
    setStatus('loading');

    const eventTypes = [...new Set(events.map(e => e.type).filter(Boolean))];

    try {
      const { token } = await getToken();
      for (const ev of events) {
        await createEvent(token, ev);
      }
      setStatus('success');
      setTimeout(() => setStatus('idle'), 3000);

      // Логируем успех на бэкенд
      _sendLog({ month, eventCount: events.length, eventTypes, status: 'success', authToken });

    } catch (e) {
      console.error('[gcal]', e);
      setStatus('error');
      setTimeout(() => setStatus('idle'), 4000);

      // Логируем ошибку на бэкенд
      _sendLog({ month, eventCount: events.length, eventTypes, status: 'error', errorMsg: e.message, authToken });

      throw e;
    }
  }

  /** fire-and-forget лог на бэкенд */
  function _sendLog({ month, eventCount, eventTypes, status, errorMsg = null, authToken }) {
    if (!authToken) return;
    fetch('/api/v1/calendar/export-log', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`,
      },
      body: JSON.stringify({
        month,
        event_count: eventCount,
        event_types: eventTypes,
        status,
        error_msg: errorMsg,
      }),
    }).catch(err => console.warn('[gcal log]', err));
  }

  return { exportToCalendar, status };
}
