/**
 * WeekAheadCard.jsx — «Неделя вперёд» (флаг week_ahead).
 *
 * Что и когда показывать, решает сервер (backend/week_ahead.py): с
 * воскресенья 19:00 до конца понедельника, события — по правилу главного
 * события дня. Вид — тот же, что у FirstWeekCard: одна рамка, без нового
 * стиля. Строка — кнопка: `onOpen(row)` из FeedScreen открывает событие
 * ленты или доезжает до его дня.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useFlag } from '../../lib/flags';
import { WEEK_AHEAD_FLAG, fetchWeekAhead } from '../lib/weekAhead';

const box = {
  margin: '8px 16px 0', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6,
  border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', background: 'var(--bg-card)',
};
const line = { margin: 0, fontSize: 13, lineHeight: 1.45, color: 'var(--text-secondary)' };
const row = {
  padding: 0, border: 0, background: 'none', textAlign: 'left', cursor: 'pointer',
  display: 'flex', flexDirection: 'column', gap: 2, font: 'inherit',
};

export default function WeekAheadCard({ active, onOpen }) {
  const on = useFlag(WEEK_AHEAD_FLAG);
  const [card, setCard] = useState(null);

  const load = useCallback(() => {
    fetchWeekAhead().then(setCard).catch(() => {});
  }, []);

  useEffect(() => {
    if (!on) { setCard(null); return undefined; }
    load();
    const onResume = () => { if (document.visibilityState === 'visible') load(); };
    document.addEventListener('visibilitychange', onResume);
    return () => document.removeEventListener('visibilitychange', onResume);
  }, [on, load]);

  // Возврат на вкладку «Лента» — могло наступить воскресенье 19:00.
  useEffect(() => { if (on && active) load(); }, [on, active, load]);

  if (!on || !card) return null;

  return (
    <div style={box}>
      <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
        {card.title} · {card.range}
      </p>
      {card.calm && <p style={line}>{card.calm_text}</p>}
      {card.events.map((r) => (
        <button key={r.date} type="button" style={row} onClick={() => onOpen?.(r)}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.when}</span>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{r.what}</span>
          <span style={line}>{r.advice}</span>
        </button>
      ))}
    </div>
  );
}
