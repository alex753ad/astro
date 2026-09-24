/**
 * MorePaymentsView.jsx — «Оплата и поддержка»: тариф и срок, история
 * платежей, сообщение в поддержку.
 *
 * Поддержка — тот же канал, что жалобы (`POST /feedback`, экран `payment`):
 * сервер сам приклеивает к сообщению тариф и последние платежи
 * (backend/feedback/router.py, `_payment_context`) — человек номер платежа не
 * знает, и спрашивать его об этом значит отложить ответ на переписку.
 *
 * ⚠️ Платёж со статусом «на проверке» (`kind: 'review'`) показывается, а не
 * прячется: деньги человек отдал, и строка без тарифа честнее отсутствия
 * строки — ровно с неё начинается «заплатила, покупки нет».
 */

import React, { useCallback, useEffect, useState } from 'react';
import MoreCenteredNotice from './MoreCenteredNotice';
import { TIER_NAMES } from '../../constants';
import { fetchPaymentHistory, sendSupportMessage } from '../lib/payApi';
import { errorText } from '../lib/netError';

const KIND_LABEL = { payment: 'Оплата', refund: 'Возврат', review: 'На проверке' };

function dateRu(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return Number.isNaN(d.getTime()) ? '' : `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

export default function MorePaymentsView() {
  const [status, setStatus] = useState('loading');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState('');

  const load = useCallback(async () => {
    setStatus('loading'); setError('');
    try {
      setData(await fetchPaymentHistory());
      setStatus('ready');
    } catch (err) {
      setError(errorText(err, 'Не удалось загрузить платежи.'));
      setStatus('error');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const send = async () => {
    if (!message.trim()) return;
    setSending(true); setSent('');
    try {
      await sendSupportMessage(message.trim());
      setMessage('');
      setSent('Отправили. Ответим на почту, которой ты входишь в приложение.');
    } catch (err) {
      setSent(errorText(err, 'Не удалось отправить сообщение.', { write: true }));
    } finally {
      setSending(false);
    }
  };

  const card = { background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '14px 16px' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 8 }}>
      {status === 'loading' && (
        <div className="mobile-skeleton" style={{ height: 120, borderRadius: 'var(--radius-lg)', background: 'var(--bg-deeper)' }} />
      )}
      {status === 'error' && (
        <MoreCenteredNotice title="Не удалось загрузить" text={error} action="Повторить" onAction={load} />
      )}
      {status === 'ready' && data && (
        <section style={card}>
          <p style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
            {TIER_NAMES[data.tier] || data.tier}
            {data.tier !== 'free' && data.active_until && ` · до ${dateRu(data.active_until)}`}
          </p>
          {data.items.length === 0 ? (
            <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>Платежей пока не было.</p>
          ) : (
            <ul style={{ margin: '10px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {data.items.map((it) => (
                <li key={it.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                  <span>{dateRu(it.at)} · {KIND_LABEL[it.kind] || it.kind}{it.tier ? ` · ${TIER_NAMES[it.tier] || it.tier}` : ''}</span>
                  <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{it.kind === 'refund' ? '−' : ''}{Math.round(it.amount)} ₽</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section style={card}>
        <p style={{ margin: '0 0 8px', fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>Написать в поддержку</p>
        <p style={{ margin: '0 0 8px', fontSize: 12.5, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
          Если деньги списались, а тариф не включился, — напиши. Номер платежа и тариф мы увидим сами.
        </p>
        <textarea
          className="mobile-input"
          rows={4}
          value={message}
          maxLength={2000}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Что случилось?"
          style={{ width: '100%', resize: 'vertical' }}
        />
        <button type="button" className="mobile-btn-primary" disabled={sending || !message.trim()} style={{ height: 44, fontSize: 14, marginTop: 8, width: '100%' }} onClick={send}>
          {sending ? 'Отправляем…' : 'Отправить'}
        </button>
        {sent && <p role="status" style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>{sent}</p>}
      </section>
    </div>
  );
}
