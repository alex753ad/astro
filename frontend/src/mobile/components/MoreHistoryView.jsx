/**
 * MoreHistoryView.jsx — «История разборов» (SPEC_MORE_SCREEN.md §6).
 *
 * ⚠️ `preview` приходит с сырой, неразобранной разметкой — начинается с
 * `<section name="general">` (MORE_API_RECON.md §2). Чистим все теги перед
 * показом, иначе они видны пользователю как текст.
 *
 * Тап по записи никуда не ведёт (§9): разбора карты в приложении ещё нет.
 * Карта в строке подписывается по дате рождения и месту — у истории нет
 * имени, и у карты его тоже нет (§5.1) — сопоставление по `chart_id`.
 */

import React, { useCallback, useEffect, useState } from 'react';
import MoreCenteredNotice from './MoreCenteredNotice';
import { fetchHistory } from '../lib/moreApi';
import { birthDateWords, shortPlace } from '../lib/chartFormat';

function cleanPreview(text) {
  return typeof text === 'string' ? text.replace(/<[^>]*>/g, '').trim() : '';
}

export default function MoreHistoryView({ chartsById }) {
  const [status, setStatus] = useState('loading');
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      const data = await fetchHistory();
      setItems(data.history || []);
      setStatus('ready');
    } catch (err) {
      setError(err?.message || 'Не удалось загрузить историю разборов.');
      setStatus('error');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (status === 'loading') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 8 }}>
        {[0, 1, 2].map((i) => (
          <div key={i} className="mobile-skeleton" style={{ height: 64, borderRadius: 'var(--radius-lg)', background: 'var(--bg-deeper)' }} />
        ))}
      </div>
    );
  }

  if (status === 'error') {
    return <MoreCenteredNotice title="Не удалось загрузить историю" text={error} action="Повторить" onAction={load} />;
  }

  if (items.length === 0) {
    return <MoreCenteredNotice title="Разборов пока нет" text="Здесь появится история интерпретаций твоих карт." />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
      {items.map((h) => {
        const chart = chartsById.get(h.chart_id);
        return (
          <div
            key={h.id}
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '12px 14px' }}
          >
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)' }}>
              {chart ? `${birthDateWords(chart.birth_date)} · ${shortPlace(chart.birth_place)}` : 'Карта'}
            </p>
            <p style={{ margin: '4px 0 0', fontSize: 13.5, lineHeight: 1.5, color: 'var(--text-primary)', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
              {cleanPreview(h.preview)}
            </p>
          </div>
        );
      })}
    </div>
  );
}
