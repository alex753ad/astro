/**
 * FeedLunationForecast.jsx — личный прогноз на новолуние/полнолуние в панели
 * события фазы (и затмения — оно заменяет фазу в ленте, см. forecastApi.js).
 *
 * Форма — по образцу владельца (docs/samples/): суть одной фразой, смысл
 * знака, 🌱 что делать, ⚠️ предупреждение с советами (только если есть
 * напряжение), ободряющий финал. Эмодзи-маркеры ставит интерфейс, а не
 * модель: сервер вычищает их из текста, чтобы форма не зависела от удачи
 * генерации. DESIGN_SYSTEM.md запрещает эмодзи только в тумблере темы (B5).
 *
 * Грузится при открытии панели: генерация — при первом открытии фазы, дальше
 * сервер отдаёт из кэша.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { cachedLunationForecast, fetchLunationForecast } from '../lib/forecastApi';
import { errorText, isConnectivity } from '../lib/netError';
import useReconnect from '../lib/useReconnect';
import { lunationPhase } from '../lib/lunationPhase';

const PHASE_MARK = { new_moon: '🌑', full_moon: '🌕' };

function Bullets({ items, marker }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {items.map((item) => (
        <div
          key={item}
          style={{
            display: 'flex', gap: 8, fontSize: 14, lineHeight: 1.55,
            fontFamily: 'var(--font-body)', color: 'var(--text-primary)',
          }}
        >
          <span aria-hidden="true" style={{ flexShrink: 0 }}>{marker}</span>
          <span>{item}</span>
        </div>
      ))}
    </div>
  );
}

const heading = { margin: 0, fontSize: 13.5, fontWeight: 600, color: 'var(--text-primary)' };
const prose = { margin: 0, fontFamily: 'var(--font-display)', fontSize: 15, lineHeight: 1.65, color: 'var(--text-primary)' };

export default function FeedLunationForecast({ chartId, event }) {
  const [state, setState] = useState({ status: 'loading', data: null });
  const runRef = useRef(0);

  // Тот же порядок, что у прогноза дня (FeedDayForecastCard.jsx): сначала
  // сохранённый текст этой фазы, сеть — только за запасным или за пустотой.
  const load = useCallback(async ({ background = false } = {}) => {
    if (!chartId || !event) return;
    const run = ++runRef.current;
    const hit = background ? null : await cachedLunationForecast(chartId, event);
    if (runRef.current !== run) return;
    if (hit) {
      setState({ status: 'ready', data: hit.data });
      if (hit.data?.source !== 'fallback') return;
    } else if (!background) {
      setState({ status: 'loading', data: null });
    }
    try {
      const data = await fetchLunationForecast(chartId, event);
      if (runRef.current === run) setState({ status: 'ready', data });
    } catch (err) {
      if (runRef.current === run && !hit) {
        setState((s) => (background && s.status === 'ready' ? s : { status: 'error', data: null, error: err }));
      }
    }
  }, [chartId, event]);

  useEffect(() => { load(); }, [load]);
  useReconnect(state.status === 'error' && isConnectivity(state.error), () => load({ background: true }));

  if (state.status === 'loading') {
    return (
      <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
        Личный прогноз на эту фазу готовится — это займёт несколько секунд.
      </p>
    );
  }
  if (state.status === 'error') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <p style={{ margin: 0, fontSize: 14, color: 'var(--text-secondary)' }}>
          {errorText(state.error, 'Прогноз не загрузился. Нажми «Повторить».')}
        </p>
        <button type="button" className="mobile-link" style={{ alignSelf: 'flex-start' }} onClick={() => load()}>
          Повторить
        </button>
      </div>
    );
  }

  const d = state.data;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <p style={{ ...prose, fontWeight: 600 }}>
        {PHASE_MARK[lunationPhase(event)] || ''} {d.headline}
      </p>
      {d.sign_meaning && <p style={prose}>{d.sign_meaning}</p>}

      {d.actions?.length > 0 && (
        <>
          <p style={heading}>🌱 Что делать</p>
          <Bullets items={d.actions} marker="·" />
        </>
      )}

      {d.warning && (
        <>
          <p style={heading}>⚠️ Будь внимательнее</p>
          {d.warning.text && <p style={{ ...prose, fontSize: 14.5 }}>{d.warning.text}</p>}
          {d.warning.tips?.length > 0 && <Bullets items={d.warning.tips} marker="⏺" />}
        </>
      )}

      {d.closing && <p style={{ ...prose, fontStyle: 'italic' }}>{d.closing}</p>}
    </div>
  );
}
