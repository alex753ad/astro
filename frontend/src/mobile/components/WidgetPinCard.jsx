/**
 * WidgetPinCard.jsx — «Твой день на главном экране» в ленте (флаг widget).
 *
 * Для тех, у кого первая неделя прошла: в первую неделю ту же роль играет
 * день 3 (FirstWeekCard). Правило показа и «не надоедать» — lib/widgetPin.js
 * (cardAllowed), решения и тексты владельца 02.10.2026 —
 * docs/widget_pin_card_plan.md, вариант Б. Вид — тот же, что у карточки
 * первой недели: одна рамка, строка действий.
 *
 * Пока «Неделя вперёд» показывает свою карточку, эта молчит: больше одной
 * карточки сверху не ставим.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { isFlagOn, useFlag } from '../../lib/flags';
import { WEEK_AHEAD_FLAG, fetchWeekAhead } from '../lib/weekAhead';
import { WIDGET_FLAG, widgetState } from '../lib/widgetSync';
import { cardAllowed, dismiss, localDate, logShown, pin, readState } from '../lib/widgetPin';

const box = {
  margin: '8px 16px 0', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6,
  border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', background: 'var(--bg-card)',
};
const line = { margin: 0, fontSize: 13, lineHeight: 1.45, color: 'var(--text-secondary)' };
const link = { padding: 0, fontSize: 13 };

export default function WidgetPinCard({ active }) {
  const on = useFlag(WIDGET_FLAG);
  const [show, setShow] = useState(false);

  const decide = useCallback(async () => {
    const w = widgetState();
    if (!on || !w.plugin) { setShow(false); return; }
    let s;
    try { s = await w.plugin.status(); } catch { setShow(false); return; }
    const weekAhead = isFlagOn(WEEK_AHEAD_FLAG) ? Boolean(await fetchWeekAhead().catch(() => null)) : false;
    const today = localDate();
    const ok = cardAllowed(readState(), today, {
      flag: w.flag, firstWeek: w.firstWeek, pin: s.pin, placed: s.placed, weekAhead,
    });
    setShow(ok);
    if (ok) logShown('card', today);
  }, [on]);

  useEffect(() => {
    if (!active) return undefined;
    decide();
    const onResume = () => { if (document.visibilityState === 'visible') decide(); };
    document.addEventListener('visibilitychange', onResume);
    return () => document.removeEventListener('visibilitychange', onResume);
  }, [active, decide]);

  if (!show) return null;
  return (
    <div style={box}>
      <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
        Твой день на главном экране
      </p>
      <p style={line}>Фаза Луны и главное событие дня — без входа в приложение.</p>
      <div style={{ display: 'flex', gap: 16 }}>
        <button type="button" className="mobile-link" style={link} onClick={() => pin('card', widgetState())}>
          Добавить виджет
        </button>
        <button type="button" className="mobile-link" style={link} onClick={() => { dismiss(); setShow(false); }}>
          Не сейчас
        </button>
      </div>
    </div>
  );
}
