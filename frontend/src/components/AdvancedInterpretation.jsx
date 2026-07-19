/**
 * Показ AI-интерпретации для соляра, синастрии и релокации.
 *
 * Interpretation.jsx переиспользовать напрямую нельзя: он жёстко вызывает
 * streamInterpretation(chartId) и завязан на paywall натальной карты. Здесь
 * поток передаётся снаружи — компонент только запускает его и рисует текст.
 */
import { useState, useRef, useEffect } from 'react';
import MotionButton from './MotionButton';

export default function AdvancedInterpretation({ start, buttonLabel = 'Получить интерпретацию', disabled }) {
  const [text,      setText]      = useState('');
  const [streaming, setStreaming] = useState(false);
  const [started,   setStarted]   = useState(false);
  const [error,     setError]     = useState(null);
  const cleanupRef = useRef(null);

  // Обрываем поток при уходе со страницы, иначе EventSource продолжит висеть.
  useEffect(() => () => cleanupRef.current?.(), []);

  function run() {
    setText('');
    setError(null);
    setStarted(true);
    setStreaming(true);

    const cleanup = start(
      (chunk) => setText(prev => prev + chunk),
      () => setStreaming(false),
      (err) => { setError(err); setStreaming(false); },
    );
    // GET-стримы возвращают функцию отписки, POST-стримы — промис.
    if (typeof cleanup === 'function') cleanupRef.current = cleanup;
  }

  return (
    <div style={{ marginTop: 28 }}>
      {!started && (
        <MotionButton onClick={run} disabled={disabled} style={{ width: '100%' }}>
          {buttonLabel}
        </MotionButton>
      )}

      {error && (
        <p style={{ color: 'var(--color-danger)', fontSize: 14, marginTop: 12 }} role="alert">
          {error}
        </p>
      )}

      {started && !error && (
        <div style={{
          marginTop: 16, padding: '20px 22px',
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 16, whiteSpace: 'pre-wrap',
          fontSize: 15, lineHeight: 1.7, color: 'var(--text-primary)',
        }}>
          {text || (streaming ? 'Готовим разбор…' : '')}
          {streaming && text && <span style={{ opacity: 0.5 }}>▍</span>}
        </div>
      )}

      {started && !streaming && !error && (
        <MotionButton onClick={run} style={{ width: '100%', marginTop: 12 }}>
          Сгенерировать заново
        </MotionButton>
      )}
    </div>
  );
}
