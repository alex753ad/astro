/**
 * GuestSaveNote.jsx — строка над лентой у гостя: карта живёт 7 дней, чтобы не
 * потерять — сохранить. Не окно и не блокировка (решение владельца
 * 27.09.2026), закрывается крестиком и больше не показывается.
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const DISMISS_KEY = 'aristea_guest_note_dismissed';

function dismissed() {
  try { return localStorage.getItem(DISMISS_KEY) === '1'; } catch { return false; }
}

export default function GuestSaveNote() {
  const navigate = useNavigate();
  const [hidden, setHidden] = useState(dismissed);
  if (hidden) return null;

  const close = () => {
    try { localStorage.setItem(DISMISS_KEY, '1'); } catch { /* до перезапуска */ }
    setHidden(true);
  };

  return (
    <div style={{
      margin: '8px 16px 0', padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10,
      border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', background: 'var(--bg-card)',
    }}
    >
      <p style={{ margin: 0, flex: 1, fontSize: 13, lineHeight: 1.45, color: 'var(--text-primary)' }}>
        Карта хранится 7 дней.{' '}
        <button type="button" className="mobile-link" style={{ padding: 0, fontSize: 13 }} onClick={() => navigate('/app/more')}>
          Зарегистрируйся, чтобы не потерять
        </button>
      </p>
      <button
        type="button"
        onClick={close}
        aria-label="Скрыть"
        style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: 18, lineHeight: 1, padding: 4 }}
      >
        ×
      </button>
    </div>
  );
}
