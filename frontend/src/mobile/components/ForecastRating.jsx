/**
 * ForecastRating.jsx — 👍/👎 под прогнозом дня и под прогнозом фазы Луны.
 *
 * Одно нажатие, без комментария. Повторное нажатие на другую кнопку меняет
 * оценку, снять её нельзя (решение владельца 24.09.2026): нажатие на уже
 * выбранную ничего не делает. Сервер — POST /forecast/feedback; доля 👎 за
 * неделю уходит в утреннюю самопроверку (backend/selfcheck.py).
 *
 * Не показывается, если в ответе нет `prompt_version`: так выглядит текст,
 * сохранённый офлайн-кэшем до появления оценок, и оценка легла бы не на ту
 * версию промпта.
 *
 * Выбранная оценка запоминается в localStorage только для подсветки кнопки:
 * источник правды — сервер, а пропавшая подсветка ничего не ломает.
 */
import React, { useState } from 'react';
import { sendForecastFeedback } from '../lib/forecastApi';
import { errorText } from '../lib/netError';

const STORE_PREFIX = 'aristea_forecast_rating:';

function readSaved(key) {
  try { return Number(localStorage.getItem(STORE_PREFIX + key)) || 0; } catch { return 0; }
}

function save(key, rating) {
  try { localStorage.setItem(STORE_PREFIX + key, String(rating)); } catch { /* только подсветка */ }
}

const btn = (active) => ({
  minWidth: 44, minHeight: 36, padding: '4px 12px', fontSize: 18, lineHeight: 1,
  borderRadius: 'var(--radius-md)', cursor: 'pointer',
  border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
  background: active ? 'var(--accent-muted)' : 'transparent',
});

/** kind — today | lunation; ref — дата дня или «фаза:момент»; data — ответ прогноза. */
export default function ForecastRating({ chartId, kind, refKey, data }) {
  const key = `${chartId}:${kind}:${refKey}`;
  const [rating, setRating] = useState(() => readSaved(key));
  const [error, setError] = useState(null);

  if (typeof data?.prompt_version !== 'number') return null;

  async function vote(value) {
    if (value === rating) return;
    const before = rating;
    setRating(value);
    setError(null);
    try {
      await sendForecastFeedback(chartId, { kind, ref: refKey, rating: value, data });
      save(key, value);
    } catch (err) {
      setRating(before);
      setError(errorText(err, 'Оценка не сохранилась.', { write: true }));
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Как тебе прогноз?</span>
        <button type="button" aria-label="Нравится" aria-pressed={rating === 1} style={btn(rating === 1)} onClick={() => vote(1)}>
          👍
        </button>
        <button type="button" aria-label="Не нравится" aria-pressed={rating === -1} style={btn(rating === -1)} onClick={() => vote(-1)}>
          👎
        </button>
      </div>
      {error && <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>{error}</p>}
    </div>
  );
}
