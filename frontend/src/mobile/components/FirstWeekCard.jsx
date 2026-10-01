/**
 * FirstWeekCard.jsx — карточка «Сегодня: …» первой недели (флаг first_week).
 *
 * Что показывать, решает сервер (backend/first_week.py): самое раннее
 * неоткрытое из наступивших дней, в день 7 — итог недели. Здесь — только
 * показ и кнопка. Вид — тот же, что у карточки «включи уведомления»
 * (PushNudge.jsx): одна рамка, одна строка действий, без нового стиля.
 *
 * Отметку «открыл» карточка ставит сама только за прогноз (событие
 * FORECAST_SEEN_EVENT: прогноз загрузился в ленте) и за итог недели (при
 * сворачивании);
 * остальные ставят экраны, где функция живёт.
 *
 * Кнопки: карта и разбор — переход на вкладку «Карта», чат — открыть чат,
 * прогноз, разбор транзитов и периоды — действие ленты (`onAction` из
 * FeedScreen: развернуть «Сегодня» / открыть текущий период).
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useFlag } from '../../lib/flags';
import { TIER_NAMES } from '../../constants';
import { FORECAST_SEEN_EVENT } from '../lib/pushNudge';
import { openPaySheet } from '../lib/paySheetBus';
import {
  FIRST_WEEK_EVENT, FIRST_WEEK_FLAG, OPEN_CHAT_EVENT, OPEN_INTERPRET_EVENT,
  emit, fetchFirstWeek, markSeen,
} from '../lib/firstWeek';

const BUTTON = {
  chart: 'Открыть карту',
  forecast: 'К прогнозу',
  interpret: 'Открыть разбор',
  transit: 'К событиям дня',
  periods: 'Открыть период',
  chat: 'Открыть чат',
  summary: 'Показать итог',
};

const box = {
  margin: '8px 16px 0', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6,
  border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', background: 'var(--bg-card)',
};
const line = { margin: 0, fontSize: 13, lineHeight: 1.45, color: 'var(--text-secondary)' };

export default function FirstWeekCard({ active, onAction }) {
  const on = useFlag(FIRST_WEEK_FLAG);
  const navigate = useNavigate();
  const [card, setCard] = useState(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    fetchFirstWeek().then(setCard).catch(() => {});
  }, []);

  useEffect(() => {
    if (!on) { setCard(null); return undefined; }
    load();
    const onForecast = () => markSeen('forecast');
    const onResume = () => { if (document.visibilityState === 'visible') load(); };
    window.addEventListener(FIRST_WEEK_EVENT, load);
    window.addEventListener(FORECAST_SEEN_EVENT, onForecast);
    document.addEventListener('visibilitychange', onResume);
    return () => {
      window.removeEventListener(FIRST_WEEK_EVENT, load);
      window.removeEventListener(FORECAST_SEEN_EVENT, onForecast);
      document.removeEventListener('visibilitychange', onResume);
    };
  }, [on, load]);

  // Возврат на вкладку «Лента» — день мог смениться, отметка — прийти.
  useEffect(() => { if (on && active) load(); }, [on, active, load]);

  if (!on || !card) return null;

  const act = () => {
    const { key } = card;
    if (key === 'summary') {
      // Отметка — при сворачивании: после неё сервер отдаёт уже другую
      // карточку, и итог пропал бы из-под глаз, пока его читают.
      if (open) markSeen('summary');
      setOpen(!open);
    } else if (key === 'chart') navigate('/app/chart');
    else if (key === 'interpret') { navigate('/app/chart'); emit(OPEN_INTERPRET_EVENT); }
    else if (key === 'chat') emit(OPEN_CHAT_EVENT);
    else onAction?.(key);
  };

  const s = card.summary;
  return (
    <div style={box}>
      <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{card.title}</p>
      <p style={line}>{card.text}</p>
      {open && s && (
        <>
          <p style={line}>{s.visits}</p>
          {s.past && <p style={line}>Главное за неделю: {s.past}</p>}
          <p style={line}>
            {s.tried.map((t) => `${t.done ? '✓' : '·'} ${t.title}`).join('   ')}
          </p>
          {s.ahead && <p style={line}>Впереди: {s.ahead}</p>}
          {s.free && (
            <button
              type="button"
              className="mobile-link"
              style={{ padding: 0, fontSize: 13, alignSelf: 'flex-start' }}
              onClick={() => openPaySheet({ focus: 'lite', context: 'Первая неделя' })}
            >
              Что открывается на {TIER_NAMES.lite}
            </button>
          )}
        </>
      )}
      <button
        type="button"
        className="mobile-link"
        style={{ padding: 0, fontSize: 13, alignSelf: 'flex-start' }}
        onClick={act}
      >
        {card.key === 'summary' && open ? 'Свернуть' : BUTTON[card.key]}
      </button>
    </div>
  );
}
