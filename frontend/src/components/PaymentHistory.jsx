/**
 * PaymentHistory.jsx — история платежей и «Написать в поддержку» (веб,
 * профиль → «Подписка»). Пара к mobile/components/MorePaymentsView.jsx.
 *
 * Поддержка — тот же канал, что жалобы (`POST /feedback`, экран `payment`):
 * сервер сам приклеивает к сообщению тариф и последние платежи.
 * Платёж «на проверке» показывается, а не прячется — см. докстринг
 * мобильной пары.
 */

import { useEffect, useState } from 'react';
import { API_BASE } from '../config';
import { TIER_NAMES } from '../constants';

const KIND_LABEL = { payment: 'Оплата', refund: 'Возврат', review: 'На проверке' };

export default function PaymentHistory({ authFetch, cardStyle, titleStyle }) {
  const [items, setItems] = useState(null);
  const [message, setMessage] = useState('');
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    authFetch(`${API_BASE}/payments/history`)
      .then((d) => setItems(d?.items || []))
      .catch(() => setItems([]));
  }, [authFetch]);

  const send = async () => {
    if (!message.trim()) return;
    setSending(true); setNote('');
    try {
      const form = new FormData();
      form.append('screen', 'payment');
      form.append('message', message.trim());
      form.append('url', window.location.href);
      form.append('user_agent', navigator.userAgent);
      const token = localStorage.getItem('astro_access_token');
      const resp = await fetch(`${API_BASE}/feedback`, {
        method: 'POST', body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) throw new Error();
      setMessage('');
      setNote('Отправили. Ответим на почту, которой ты входишь.');
    } catch {
      setNote('Не удалось отправить — попробуй ещё раз.');
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <div style={cardStyle}>
        <p style={titleStyle}>История платежей</p>
        {items === null && <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>Загрузка…</p>}
        {items?.length === 0 && <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>Платежей пока не было.</p>}
        {items?.map((it) => (
          <div key={it.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0', color: 'var(--text-secondary)' }}>
            <span>
              {it.at ? new Date(it.at).toLocaleDateString('ru-RU') : ''} · {KIND_LABEL[it.kind] || it.kind}
              {it.tier ? ` · ${TIER_NAMES[it.tier] || it.tier}` : ''}
            </span>
            <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{it.kind === 'refund' ? '−' : ''}{Math.round(it.amount)} ₽</span>
          </div>
        ))}
      </div>
      <div style={cardStyle}>
        <p style={titleStyle}>Написать в поддержку</p>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 8px' }}>
          Если деньги списались, а тариф не включился, — напиши. Номер платежа и тариф мы увидим сами.
        </p>
        <textarea
          rows={4} maxLength={2000} value={message} onChange={(e) => setMessage(e.target.value)}
          placeholder="Что случилось?"
          style={{ width: '100%', padding: 10, borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-primary)', fontFamily: 'inherit', fontSize: 14 }}
        />
        <button type="button" onClick={send} disabled={sending || !message.trim()}
          style={{ marginTop: 8, padding: '10px 18px', borderRadius: 'var(--radius-full)', border: 'none', background: 'var(--accent)', color: '#fff', fontWeight: 600, cursor: 'pointer', opacity: sending || !message.trim() ? 0.6 : 1 }}>
          {sending ? 'Отправляем…' : 'Отправить'}
        </button>
        {note && <p role="status" style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '8px 0 0' }}>{note}</p>}
      </div>
    </>
  );
}
