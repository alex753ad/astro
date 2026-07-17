/**
 * Toast.jsx — уведомления.
 * Использование: обернуть App в <ToastProvider>, вызывать useToast() в компонентах.
 */

import { createContext, useCallback, useContext, useRef, useState } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';

const ToastContext = createContext(null);

const NOOP = { error: () => {}, success: () => {}, info: () => {} };

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) return NOOP;
  return ctx;
}

let nextId = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef({});

  const dismiss = useCallback((id) => {
    clearTimeout(timers.current[id]);
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const add = useCallback((type, message) => {
    const id = ++nextId;
    setToasts(prev => [...prev, { id, type, message }]);
    timers.current[id] = setTimeout(() => dismiss(id), 4000);
  }, [dismiss]);

  const toast = {
    error:   (msg) => add('error',   msg),
    success: (msg) => add('success', msg),
    info:    (msg) => add('info',    msg),
  };

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <ToastContainer toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  );
}

const STYLES = {
  error:   { icon: '✕', color: 'var(--color-danger)', bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)' },
  success: { icon: '✓', color: 'var(--color-success)', bg: 'rgba(74,222,128,0.10)', border: 'rgba(74,222,128,0.3)' },
  info:    { icon: 'ℹ', color: 'var(--accent)', bg: 'rgba(124,108,255,0.10)', border: 'rgba(124,108,255,0.3)' },
};

function ToastContainer({ toasts, dismiss }) {
  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24,
      zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 8,
      pointerEvents: 'none',
    }}>
      <AnimatePresence>
        {toasts.map(t => (
          <ToastItem key={t.id} toast={t} dismiss={dismiss} />
        ))}
      </AnimatePresence>
    </div>
  );
}

function ToastItem({ toast, dismiss }) {
  const s = STYLES[toast.type];
  const prefersReduced = useReducedMotion();
  const variants = prefersReduced
    ? {
        hidden:  { opacity: 0 },
        visible: { opacity: 1, transition: { duration: 0.25, ease: 'easeOut' } },
        exit:    { opacity: 0, transition: { duration: 0.2, ease: 'easeOut' } },
      }
    : {
        hidden:  { opacity: 0, x: 60 },
        visible: { opacity: 1, x: 0, transition: { duration: 0.25, ease: 'easeOut' } },
        exit:    { opacity: 0, x: 60, transition: { duration: 0.2, ease: 'easeOut' } },
      };
  return (
    <motion.div
      key={toast.id}
      variants={variants} initial="hidden" animate="visible" exit="exit"
      style={{
        pointerEvents: 'auto',
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '12px 14px', borderRadius: 12, minWidth: 260, maxWidth: 360,
        background: s.bg,
        backdropFilter: 'blur(12px)',
        border: `1px solid ${s.border}`,
        boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
        fontSize: 13,
        color: 'var(--border)',
      }}
    >
      <span style={{ color: s.color, fontWeight: 700, fontSize: 15, flexShrink: 0 }}>{s.icon}</span>
      <span style={{ flex: 1, lineHeight: 1.4 }}>{toast.message}</span>
      <button
        onClick={() => dismiss(toast.id)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--text-secondary)', fontSize: 16, padding: '0 2px', lineHeight: 1,
          flexShrink: 0,
        }}
      >
        ×
      </button>
    </motion.div>
  );
}
