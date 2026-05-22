/**
 * Interpretation.jsx — AI-интерпретация натальной карты.
 * Запускается ТОЛЬКО по кнопке, автозагрузки нет.
 */

import { useState, useRef, useCallback } from 'react';
import { streamInterpretation } from '../api/client';

function renderMarkdown(text) {
  const lines = text.split('\n');
  return lines.map((line, i) => {
    if (line.startsWith('### ')) {
      return (
        <h3 key={i} style={{
          fontSize: 15, fontWeight: 700,
          color: 'var(--text-primary, #E8EAF0)',
          margin: '20px 0 8px',
          borderBottom: '1px solid var(--border, #1E2235)',
          paddingBottom: 6,
        }}>
          {line.slice(4)}
        </h3>
      );
    }
    if (line.startsWith('## ')) {
      return (
        <h2 key={i} style={{
          fontSize: 17, fontWeight: 700,
          color: 'var(--accent, #7C6CFF)',
          margin: '24px 0 10px',
        }}>
          {line.slice(3)}
        </h2>
      );
    }
    if (!line.trim()) return <br key={i} />;
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    return (
      <p key={i} style={{ margin: '0 0 8px', lineHeight: 1.75 }}>
        {parts.map((p, j) =>
          p.startsWith('**') && p.endsWith('**')
            ? <strong key={j}>{p.slice(2, -2)}</strong>
            : p
        )}
      </p>
    );
  });
}

export default function Interpretation({ chartId }) {
  const [text,      setText]      = useState('');
  const [streaming, setStreaming] = useState(false);
  const [done,      setDone]      = useState(false);
  const [error,     setError]     = useState(null);
  const [started,   setStarted]   = useState(false); // ← ключевое: не стартовали

  const scrollRef   = useRef(null);
  const closeSSERef = useRef(null);

  const start = useCallback((retryCount = 0) => {
    if (!chartId) return;
    setText('');
    setDone(false);
    setError(null);
    setStreaming(true);
    setStarted(true);

    let receivedAny = false;

    const close = streamInterpretation(
      chartId,
      (chunk) => {
        receivedAny = true;
        setText(prev => prev + chunk);
        if (scrollRef.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
      },
      () => { setStreaming(false); setDone(true); },
      (err) => {
        // Reconnect up to 3 times if connection dropped mid-stream
        if (!receivedAny && retryCount < 3) {
          console.warn(`SSE retry ${retryCount + 1}`);
          setTimeout(() => start(retryCount + 1), 1500 * (retryCount + 1));
          return;
        }
        setError(String(err));
        setStreaming(false);
      },
    );

    closeSSERef.current = close;
  }, [chartId]);

  // ── Не запускались — показываем кнопку ──
  if (!started) {
    return (
      <div className="glass-card p-6">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--accent, #7C6CFF)' }}>✦</span>
            AI-интерпретация
          </h2>
        </div>
        <p style={{ fontSize: 13, color: 'var(--color-text-secondary, #8B8FA3)', margin: '0 0 16px', lineHeight: 1.6 }}>
          Персональный разбор натальной карты — характер, таланты, жизненные темы. Генерируется на основе положений всех планет и домов.
        </p>
        <button
          onClick={start}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 20px', borderRadius: 10,
            border: '1px solid rgba(124,108,255,0.5)',
            background: 'linear-gradient(135deg, rgba(124,108,255,0.12), rgba(167,139,250,0.12))',
            color: 'var(--accent, #7C6CFF)', fontSize: 14, fontWeight: 600,
            cursor: 'pointer', fontFamily: 'inherit',
            transition: 'all 0.2s',
          }}
        >
          <span>✦</span> Создать интерпретацию
        </button>
      </div>
    );
  }

  return (
    <div className="glass-card p-6">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: 'var(--accent, #7C6CFF)' }}>✦</span>
          AI-интерпретация
        </h2>
        {done && (
          <button
            onClick={start}
            style={{
              background: 'none', border: '1px solid var(--border, #1E2235)',
              color: 'var(--text-secondary, #8B8FA3)',
              borderRadius: 8, padding: '4px 10px',
              fontSize: 12, cursor: 'pointer', transition: 'all 0.2s',
            }}
          >
            ↺ Заново
          </button>
        )}
      </div>

      {/* Streaming indicator */}
      {streaming && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
          fontSize: 12, color: 'var(--text-secondary, #8B8FA3)',
        }}>
          <span style={{
            width: 8, height: 8, borderRadius: 4,
            background: 'var(--accent, #7C6CFF)',
            animation: 'pulse 1.2s ease infinite',
          }} />
          Генерирую интерпретацию…
          <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }`}</style>
        </div>
      )}

      {/* Skeleton while starting */}
      {streaming && !text && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[80, 100, 60, 90, 75].map((w, i) => (
            <div key={i} style={{
              height: 13, width: `${w}%`, borderRadius: 4,
              background: 'linear-gradient(90deg, var(--border, #1E2235) 25%, rgba(255,255,255,0.04) 50%, var(--border, #1E2235) 75%)',
              backgroundSize: '200% 100%',
              animation: `shimmer 1.8s ease-in-out ${i * 0.1}s infinite`,
            }} />
          ))}
          <style>{`@keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          padding: '16px', borderRadius: 10,
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.2)', marginBottom: 12,
        }}>
          <p style={{ margin: 0, fontSize: 13, color: '#FCA5A5' }}>
            Не удалось загрузить интерпретацию: {error}
          </p>
          <button onClick={start} style={{
            marginTop: 10, padding: '6px 16px', borderRadius: 8,
            border: '1px solid rgba(239,68,68,0.4)', background: 'transparent',
            color: '#FCA5A5', fontSize: 12, fontWeight: 600, cursor: 'pointer',
          }}>
            Попробовать снова
          </button>
        </div>
      )}

      {/* Text */}
      {text && (
        <div
          ref={scrollRef}
          style={{
            fontSize: 14, color: 'var(--text-primary, #E8EAF0)',
            lineHeight: 1.75, maxHeight: 520, overflowY: 'auto', paddingRight: 4,
          }}
        >
          {renderMarkdown(text)}
          {streaming && (
            <span style={{
              display: 'inline-block', width: 7, height: 17,
              background: 'var(--accent, #7C6CFF)',
              marginLeft: 2, borderRadius: 2,
              animation: 'blink 0.8s step-end infinite',
              verticalAlign: 'text-bottom',
            }} />
          )}
          <style>{`@keyframes blink { 50%{opacity:0} }`}</style>
        </div>
      )}
    </div>
  );
}
