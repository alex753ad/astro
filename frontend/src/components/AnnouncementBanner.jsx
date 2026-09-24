/**
 * AnnouncementBanner.jsx — баннер объявления (смена цен, оферта п. 10.1).
 * Общий для веба и приложения: вёрстка на токенах, которые есть в обоих
 * наборах (`--bg-card`, `--border`, `--accent`, `--text-*`, `--radius-lg`).
 */

import React, { useEffect, useState } from 'react';
import { dismissAnnouncement, fetchAnnouncements, visibleAnnouncements } from '../lib/announcements';

export default function AnnouncementBanner({ style, onLink }) {
  const [items, setItems] = useState([]);

  useEffect(() => {
    let alive = true;
    fetchAnnouncements().then((all) => { if (alive) setItems(visibleAnnouncements(all)); });
    return () => { alive = false; };
  }, []);

  if (!items.length) return null;
  const a = items[0];
  const close = () => { dismissAnnouncement(a.ref); setItems(items.slice(1)); };

  return (
    <section
      role="status"
      style={{
        background: 'var(--bg-card)', border: '1px solid var(--accent)', borderRadius: 'var(--radius-lg)',
        padding: '12px 14px', display: 'flex', gap: 10, alignItems: 'flex-start', ...style,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{a.title}</p>
        {a.body && (
          <p style={{ margin: '4px 0 0', fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)', whiteSpace: 'pre-line' }}>
            {a.body}
          </p>
        )}
        {a.link && onLink && (
          <button type="button" onClick={() => onLink(a.link)}
            style={{ marginTop: 6, padding: 0, border: 'none', background: 'none', color: 'var(--accent)', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
            Подробнее
          </button>
        )}
      </div>
      <button type="button" aria-label="Скрыть" onClick={close}
        style={{ border: 'none', background: 'none', color: 'var(--text-secondary)', fontSize: 18, lineHeight: 1, cursor: 'pointer', padding: 2 }}>
        ×
      </button>
    </section>
  );
}
