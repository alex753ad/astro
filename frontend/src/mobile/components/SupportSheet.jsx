/**
 * SupportSheet.jsx — «Написать в поддержку», один лист на всё приложение
 * (lib/supportBus.js). Открывается из меню «Ещё», с листа оплаты и с экранов
 * ошибок.
 *
 * Под полем ввода — всё, что уйдёт вместе с сообщением, и почта, на которую
 * придёт ответ. Человек видит это ДО отправки: версию, телефон, номер
 * аккаунта и очищенный текст ошибки (lib/supportContext.js).
 *
 * ⚠️ Черновик переживает закрытие листа и отказ сети (localStorage): без
 * сети текст не теряется, а строка отказа — из NET_WRITE_TEXT
 * («ничего не отправлено»), потому что само ничего не повторится.
 *
 * После отправки — заголовок «Получили» и под ним «Ответим на почту …» без
 * обещаний по срокам (решение владельца 27.09.2026). Слово «Получили» в
 * тексте не повторяется — оно уже в заголовке.
 */

import React, { useEffect, useState } from 'react';
import useAuth from '../../hooks/useAuth.jsx';
import { onSupport, sendSupportMessage } from '../lib/supportBus';
import { appVersionLabel, deviceLabel, scrubErrorText } from '../lib/supportContext';
import { errorText } from '../lib/netError';

const DRAFT_KEY = 'aristea_support_draft';

function readDraft() {
  try { return localStorage.getItem(DRAFT_KEY) || ''; } catch { return ''; }
}
function writeDraft(text) {
  try {
    if (text) localStorage.setItem(DRAFT_KEY, text);
    else localStorage.removeItem(DRAFT_KEY);
  } catch { /* хранилище недоступно — черновик живёт до закрытия листа */ }
}

export default function SupportSheet() {
  const { user } = useAuth();
  const [ctx, setCtx] = useState(null);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [failure, setFailure] = useState('');
  const [done, setDone] = useState(false);

  useEffect(() => onSupport((opts) => {
    setCtx({ screen: opts.screen, error: scrubErrorText(opts.error) });
    setMessage(readDraft());
    setFailure(''); setDone(false);
  }), []);

  if (!ctx) return null;
  const close = () => setCtx(null);
  const email = user?.email;

  const edit = (text) => { setMessage(text); writeDraft(text); };

  const send = async () => {
    if (!message.trim() || sending) return;
    setSending(true); setFailure('');
    try {
      await sendSupportMessage({ message: message.trim(), screen: ctx.screen, error: ctx.error });
      writeDraft('');
      setMessage('');
      setDone(true);
    } catch (err) {
      setFailure(errorText(err, 'Не удалось отправить сообщение.', { write: true }));
    } finally {
      setSending(false);
    }
  };

  const small = { margin: 0, fontSize: 12, lineHeight: 1.5, color: 'var(--text-secondary)' };

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={close}
      /* Выше листа оплаты (60): поддержку открывают и оттуда. */
      style={{ position: 'fixed', inset: 0, zIndex: 70, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'flex-end' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', maxHeight: '85%', overflowY: 'auto', background: 'var(--bg-page)',
          borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0',
          padding: '18px 16px calc(18px + env(safe-area-inset-bottom))',
          display: 'flex', flexDirection: 'column', gap: 10,
        }}
      >
        <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
          {done ? 'Получили' : 'Написать в поддержку'}
        </p>

        {done ? (
          email && (
            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: 'var(--text-secondary)' }}>
              Ответим на почту {email}
            </p>
          )
        ) : (
          <>
            <textarea
              className="mobile-input"
              rows={5}
              value={message}
              maxLength={2000}
              onChange={(e) => edit(e.target.value)}
              placeholder="Что случилось?"
              style={{ width: '100%', resize: 'vertical' }}
            />
            {email && <p style={{ ...small, color: 'var(--text-primary)' }}>Ответим на почту {email}</p>}
            <p style={small}>
              Вместе с сообщением уйдёт: версия {appVersionLabel()}, телефон {deviceLabel()}
              {user?.id ? `, номер аккаунта ${user.id}` : ''}
              {ctx.error ? `, текст ошибки: «${ctx.error}»` : ''}.
            </p>
            {failure && <p role="alert" style={{ margin: 0, fontSize: 13, color: 'var(--color-danger)' }}>{failure}</p>}
            <button
              type="button"
              className="mobile-btn-primary"
              disabled={sending || !message.trim()}
              style={{ height: 44, fontSize: 14 }}
              onClick={send}
            >
              {sending ? 'Отправляем…' : 'Отправить'}
            </button>
          </>
        )}

        <button type="button" className="mobile-link" onClick={close} style={{ alignSelf: 'center' }}>
          Закрыть
        </button>
      </div>
    </div>
  );
}
