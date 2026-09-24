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
import { fetchDayForecast } from '../lib/forecastApi';

/** label — «вчера» | «сегодня» | «завтра». */
export default function FeedDayForecastCard({ chartId, date, label, open, onToggle }) {
  const [state, setState] = useState({ status: 'loading', data: null });
  const runRef = useRef(0);

  const load = useCallback(async () => {
    if (!chartId || !date) return;
    const run = ++runRef.current;
    setState({ status: 'loading', data: null });
    try {
      const data = await fetchDayForecast(chartId, date);
      if (runRef.current === run) setState({ status: 'ready', data });
    } catch {
      if (runRef.current === run) setState({ status: 'error', data: null });
    }
  }, [chartId, date]);

  useEffect(() => { load(); }, [load]);

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
            Прогноз не загрузился.
          </p>
          <button type="button" className="mobile-link" style={{ alignSelf: 'flex-start' }} onClick={load}>
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
