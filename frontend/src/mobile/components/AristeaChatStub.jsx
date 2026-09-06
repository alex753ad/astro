/**
 * AristeaChatStub.jsx — заглушка чата с Аристеей, открывается по тапу на
 * рабочую кнопку-FAB (Лира/Орион). Сам чат не подключён — ни RAG, ни
 * запросов к interpretation/rag_router.py — намеренно, отдельная задача.
 *
 * Тот же приём шторки снизу, что у FeedEventPanel.jsx: не отдельный
 * экран/роут, просто оверлей поверх текущей вкладки — дешевле и ничем не
 * рискует при будущей подмене содержимого на настоящий чат.
 */

import React from 'react';

export default function AristeaChatStub({ onClose }) {
  return (
    <>
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 30 }}
      />
      <div
        role="dialog"
        aria-label="Чат с Аристеей"
        style={{
          position: 'fixed',
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 31,
          background: 'var(--bg-card)',
          borderTopLeftRadius: 20,
          borderTopRightRadius: 20,
          borderTop: '1px solid var(--border)',
          padding: '8px 20px 24px',
          paddingBottom: 'calc(24px + env(safe-area-inset-bottom))',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
          textAlign: 'center',
        }}
      >
        <div style={{ width: 36, height: 4, borderRadius: 999, background: 'var(--border)' }} />
        <span
          aria-hidden="true"
          style={{
            width: 48, height: 48, borderRadius: '50%', background: 'var(--accent)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, marginTop: 4,
          }}
        >
          ✦
        </span>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 19, fontWeight: 700, color: 'var(--text-primary)' }}>
          Чат с Аристеей
        </h2>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
          Скоро здесь можно будет спросить Аристею о своей карте напрямую.
        </p>
        <button type="button" className="mobile-link" onClick={onClose} style={{ marginTop: 4 }}>
          Понятно
        </button>
      </div>
    </>
  );
}
