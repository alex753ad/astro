/**
 * RagChat.jsx — AI-чат по натальной карте (Pro/Premium)
 *
 * Props:
 *   chartId     string   — ID карты
 *   onPaywall   fn       — вызвать PaywallModal при 403
 */

import React, { useState, useRef, useEffect } from 'react';

const API_BASE = 'https://astro-production-abcc.up.railway.app/api/v1';

const SUGGESTIONS = [
  'Что говорит моя карта о карьере?',
  'Как Сатурн влияет на мои отношения?',
  'Какой период сейчас для финансовых решений?',
  'Почему мне сложно с дисциплиной?',
  'Что означает мой Асцендент?',
];

export default function RagChat({ chartId, onPaywall }) {
  const [messages, setMessages]     = useState([]);
  const [input, setInput]           = useState('');
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);
  const bottomRef                    = useRef(null);
  const abortRef                     = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Очищаем стрим при анмаунте
  useEffect(() => () => abortRef.current?.abort(), []);

  async function send(question) {
    if (!question.trim() || loading) return;
    setError(null);

    const userMsg = { role: 'user', content: question };
    const history = messages.slice(-10); // последние 10 сообщений
    setMessages(prev => [...prev, userMsg, { role: 'assistant', content: '', streaming: true }]);
    setInput('');
    setLoading(true);

    const token = localStorage.getItem('astro_access_token');
    const ctrl  = new AbortController();
    abortRef.current = ctrl;

    try {
      const resp = await fetch(`${API_BASE}/chart/${chartId}/rag-chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ question, history }),
        signal: ctrl.signal,
      });

      if (resp.status === 403) {
        const body = await resp.json().catch(() => ({}));
        setMessages(prev => prev.slice(0, -1)); // убираем пустой assistant
        onPaywall?.('lite_to_pro');
        return;
      }
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6);
          if (data.trim() === '[DONE]') break;
          try {
            const parsed = JSON.parse(data);
            if (parsed.text) {
              setMessages(prev => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === 'assistant') {
                  next[next.length - 1] = {
                    ...last,
                    content: last.content + parsed.text,
                  };
                }
                return next;
              });
            }
          } catch { /* skip */ }
        }
      }

      // Убираем флаг streaming
      setMessages(prev => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === 'assistant') {
          next[next.length - 1] = { ...last, streaming: false };
        }
        return next;
      });

    } catch (e) {
      if (e.name === 'AbortError') return;
      setError('Ошибка соединения. Попробуйте ещё раз.');
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  return (
    <div className="rc-scope" style={s.wrap}>
      <style>{`
        .rc-scope {
          --rc-bg: var(--bg-card); --rc-border: var(--border); --rc-title: var(--bg-card); --rc-sub: var(--text-secondary);
          --rc-empty: var(--text-secondary); --rc-chip-bg: var(--border); --rc-chip-fg: var(--bg-deeper); --rc-ai: var(--accent);
          --rc-assist-fg: var(--bg-card); --rc-input-bg: var(--bg-deeper); --rc-input-fg: var(--bg-card);
          --rc-hint: var(--text-secondary); --rc-err: var(--color-danger);
        }
        .dark .rc-scope {
          --rc-bg: transparent; --rc-border: rgba(139,92,246,0.16); --rc-title: var(--text-primary); --rc-sub: var(--text-secondary);
          --rc-empty: var(--text-secondary); --rc-chip-bg: rgba(139,92,246,0.14); --rc-chip-fg: var(--accent-glow); --rc-ai: var(--accent-glow);
          --rc-assist-fg: var(--text-primary); --rc-input-bg: rgba(35,28,56,0.60); --rc-input-fg: var(--text-primary);
          --rc-hint: var(--text-secondary); --rc-err: var(--color-danger);
        }
        .dark .rc-scope textarea::placeholder { color: var(--text-secondary); }
      `}</style>

      {/* Шапка */}
      <div style={s.header}>
        <span style={s.headerTitle}>💬 Чат с AI-астрологом</span>
        <span style={s.headerSub}>Задайте вопрос о своей натальной карте</span>
      </div>

      {/* Сообщения */}
      <div style={s.messages}>
        {messages.length === 0 && (
          <div style={s.emptyState}>
            <div style={s.emptyIcon}>🔮</div>
            <p style={s.emptyText}>AI знает вашу карту. Спросите что угодно.</p>
            <div style={s.suggestions}>
              {SUGGESTIONS.map(q => (
                <button key={q} style={s.suggestion} onClick={() => send(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={msg.role === 'user' ? s.msgUser : s.msgAssistant}>
            {msg.role === 'assistant' && (
              <span style={s.aiLabel}>✦ AI</span>
            )}
            <div style={msg.role === 'user' ? s.bubbleUser : s.bubbleAssistant}>
              {msg.content || (msg.streaming ? <TypingDots /> : '')}
            </div>
          </div>
        ))}

        {error && <p style={s.error}>{error}</p>}
        <div ref={bottomRef} />
      </div>

      {/* Инпут */}
      <div style={s.inputRow}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Задайте вопрос о своей карте…"
          style={s.textarea}
          rows={2}
          disabled={loading}
        />
        <button
          onClick={() => send(input)}
          disabled={loading || !input.trim()}
          style={{ ...s.sendBtn, opacity: (loading || !input.trim()) ? 0.5 : 1 }}
        >
          {loading ? '…' : '↑'}
        </button>
      </div>
      <p style={s.hint}>Enter — отправить · Shift+Enter — новая строка</p>
    </div>
  );
}

function TypingDots() {
  return (
    <span style={{ display: 'inline-flex', gap: 3, alignItems: 'center' }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 6, height: 6, borderRadius: '50%',
          background: 'var(--rc-ai)',
          animation: 'pulse 1.2s ease-in-out infinite',
          animationDelay: `${i * 0.2}s`,
          display: 'inline-block',
        }} />
      ))}
      <style>{`
        @keyframes pulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </span>
  );
}

const s = {
  wrap: {
    display: 'flex', flexDirection: 'column',
    height: '100%', minHeight: 480,
    background: 'var(--rc-bg)', borderRadius: 16,
    border: '0.5px solid var(--rc-border)',
    overflow: 'hidden',
  },
  header: {
    padding: '16px 20px 12px',
    borderBottom: '0.5px solid var(--rc-border)',
    display: 'flex', flexDirection: 'column', gap: 2,
  },
  headerTitle: { fontSize: 15, fontWeight: 600, color: 'var(--rc-title)' },
  headerSub:   { fontSize: 12, color: 'var(--rc-sub)' },
  messages: {
    flex: 1, overflowY: 'auto',
    padding: '16px 20px',
    display: 'flex', flexDirection: 'column', gap: 12,
  },
  emptyState: {
    display: 'flex', flexDirection: 'column',
    alignItems: 'center', gap: 12,
    padding: '32px 0',
  },
  emptyIcon: { fontSize: 36 },
  emptyText: { fontSize: 14, color: 'var(--rc-empty)', margin: 0 },
  suggestions: {
    display: 'flex', flexWrap: 'wrap', gap: 8,
    justifyContent: 'center', maxWidth: 480,
  },
  suggestion: {
    padding: '8px 14px', fontSize: 13,
    background: 'var(--rc-chip-bg)', color: 'var(--rc-chip-fg)',
    border: '0.5px solid var(--rc-border)', borderRadius: 20,
    cursor: 'pointer', fontFamily: 'inherit',
    transition: 'background 0.15s',
    textAlign: 'left',
  },
  msgUser: {
    display: 'flex', justifyContent: 'flex-end',
  },
  msgAssistant: {
    display: 'flex', flexDirection: 'column', gap: 4,
    alignItems: 'flex-start',
  },
  aiLabel: { fontSize: 11, fontWeight: 700, color: 'var(--rc-ai)', letterSpacing: '0.05em' },
  bubbleUser: {
    maxWidth: '75%', padding: '10px 14px',
    background: 'linear-gradient(135deg, var(--accent), var(--accent))',
    color: '#fff', borderRadius: '16px 16px 4px 16px',
    fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap',
  },
  bubbleAssistant: {
    maxWidth: '90%', padding: '12px 16px',
    background: 'var(--rc-chip-bg)',
    color: 'var(--rc-assist-fg)', borderRadius: '4px 16px 16px 16px',
    fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap',
  },
  error: { color: 'var(--rc-err)', fontSize: 13, textAlign: 'center', margin: 0 },
  inputRow: {
    display: 'flex', gap: 8, alignItems: 'flex-end',
    padding: '12px 16px 8px',
    borderTop: '0.5px solid var(--rc-border)',
  },
  textarea: {
    flex: 1, resize: 'none',
    padding: '10px 14px', fontSize: 14,
    border: '1px solid var(--rc-border)', borderRadius: 12,
    fontFamily: 'inherit', color: 'var(--rc-input-fg)',
    background: 'var(--rc-input-bg)', outline: 'none',
    lineHeight: 1.5,
  },
  sendBtn: {
    width: 40, height: 40, borderRadius: 12, flexShrink: 0,
    background: 'linear-gradient(135deg, var(--accent), var(--accent))',
    color: '#fff', border: 'none', fontSize: 18,
    cursor: 'pointer', fontFamily: 'inherit',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    transition: 'opacity 0.15s',
  },
  hint: { fontSize: 11, color: 'var(--rc-hint)', textAlign: 'center', margin: '0 0 8px', padding: 0 },
};
