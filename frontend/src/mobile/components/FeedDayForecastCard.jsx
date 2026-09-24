/**
 * FeedDayForecastCard.jsx — прогноз на день в начале этого дня ленты.
 *
 * Дни с карточкой: вчера, сегодня и — с 19:00 — завтра (feedAnchor.js,
 * forecastDates; решения владельца 23 и 24.09.2026). Текст один и тот же для
 * дня во всех трёх ролях — сервер пишет его без «сегодня/завтра/вчера», а
 * роль называет только подпись карточки.
 *
 * Свёрнута — первый абзац, по нажатию — целиком. Открытие/закрытие держит
 * FeedScreen: туда же приходит нажатие на утреннее и вечернее уведомления,
 * которые обязаны развернуть карточку своего дня, а не просто открыть ленту.
 *
 * Текст генерируется при первом открытии дня и кэшируется на сервере —
 * первый запрос может идти несколько секунд, отсюда отдельное состояние
 * «готовится». Запасной текст сервера (модель недоступна) выглядит так же,
 * как основной: человеку незачем знать, какой из двух путей сработал.
 *
 * Тело — антиквой, как тело любой интерпретации (§3 DESIGN_SYSTEM.md).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { cachedDayForecast, fetchDayForecast } from '../lib/forecastApi';
import { errorText, isConnectivity } from '../lib/netError';
import useReconnect from '../lib/useReconnect';

/** label — «вчера» | «сегодня» | «завтра». */
export default function FeedDayForecastCard({ chartId, date, label, open, onToggle }) {
  const [state, setState] = useState({ status: 'loading', data: null });
  const runRef = useRef(0);

  /*
   * Без сети (24.09.2026): сохранённый текст ЭТОЙ даты показывается сразу.
   * Ключ кэша — дата карточки, так что вчерашний под «сегодня» не встанет.
   * Текст модели за дату не меняется, и сеть за ним не нужна; запасной
   * (`source: 'fallback'`) сервер не кэширует — его перезапрашиваем.
   */
  const load = useCallback(async ({ background = false } = {}) => {
    if (!chartId || !date) return;
    const run = ++runRef.current;
    const hit = background ? null : await cachedDayForecast(chartId, date);
    if (runRef.current !== run) return;
    if (hit) {
      setState({ status: 'ready', data: hit.data });
      if (hit.data?.source !== 'fallback') return;
    } else if (!background) {
      setState({ status: 'loading', data: null });
    }
    try {
      const data = await fetchDayForecast(chartId, date);
      if (runRef.current === run) setState({ status: 'ready', data });
    } catch (err) {
      if (runRef.current === run && !hit) {
        setState((s) => (background && s.status === 'ready' ? s : { status: 'error', data: null, error: err }));
      }
    }
  }, [chartId, date]);

  useEffect(() => { load(); }, [load]);
  useReconnect(state.status === 'error' && isConnectivity(state.error), () => load({ background: true }));

  const paragraphs = state.data?.paragraphs || [];
  const shown = open ? paragraphs : paragraphs.slice(0, 1);

  return (
    <div
      style={{
        margin: '4px 10px 12px',
        padding: '14px 16px',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border)',
        background: 'var(--bg-card)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.09em', color: 'var(--text-secondary)' }}>
        {`ПРОГНОЗ НА ${String(label || '').toUpperCase()}`}
      </div>

      {state.status === 'loading' && (
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
          Прогноз готовится — это займёт несколько секунд.
        </p>
      )}

      {state.status === 'error' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            {errorText(state.error, 'Прогноз не загрузился. Нажми «Повторить».')}
          </p>
          <button type="button" className="mobile-link" style={{ alignSelf: 'flex-start' }} onClick={() => load()}>
            Повторить
          </button>
        </div>
      )}

      {state.status === 'ready' && (
        <>
          {shown.map((p, i) => (
            <p
              key={i}
              style={{
                margin: 0, fontFamily: 'var(--font-display)', fontSize: 15, lineHeight: 1.65,
                color: 'var(--text-primary)',
              }}
            >
              {p}
            </p>
          ))}
          {paragraphs.length > 1 && (
            <button
              type="button"
              className="mobile-link"
              style={{ alignSelf: 'flex-start' }}
              onClick={onToggle}
              aria-expanded={open}
            >
              {open ? 'Свернуть' : 'Читать дальше'}
            </button>
          )}
        </>
      )}
    </div>
  );
}
