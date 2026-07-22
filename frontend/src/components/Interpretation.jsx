/**
 * Interpretation.jsx — AI-интерпретация натальной карты.
 * Запускается ТОЛЬКО по кнопке, автозагрузки нет.
 *
 * v2:
 * - Toast при сетевой ошибке
 * - Progress bar с этапами вместо skeleton
 * - Retry-кнопка при неудаче
 */

import { useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { streamInterpretation } from '../api/client';
import { useToast } from './Toast';
import { TIER_NAMES } from '../constants';

// ── Этапы прогресса ────────────────────────────────────────

const STAGES = [
  'Рассчитываем позиции планет...',
  'Строим аспекты...',
  'Готовим интерпретацию...',
];

function StreamingProgress() {
  const [stageIdx, setStageIdx] = useState(0);
  const [progress, setProgress] = useState(0);

  // Сдвигаем этап каждые 1.2 сек
  const timerRef = useRef(null);
  if (!timerRef.current) {
    STAGES.forEach((_, i) => {
      timerRef.current = setTimeout(() => {
        setStageIdx(i);
        setProgress([33, 66, 90][i]);
      }, (i + 1) * 1200);
    });
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 13, color: 'var(--text-secondary, var(--text-secondary))', minHeight: 18 }}>
        {STAGES[stageIdx]}
      </div>
      <div style={{
        width: '100%', height: 4, borderRadius: 2,
        background: 'var(--border, var(--bg-card))', overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', width: `${progress}%`, borderRadius: 2,
          background: 'linear-gradient(90deg, var(--accent, var(--accent)), var(--accent))',
          transition: 'width 1s cubic-bezier(0.4,0,0.2,1)',
        }} />
      </div>
    </div>
  );
}

// ── Paywall helpers ────────────────────────────────────────

const CUTOFF_KEYWORDS = [
  '## Отношения', '### Отношения',
  '## Любовь', '### Любовь',
  '## Венера', '### Венера',
  '## Луна', '### Луна',
  '## 7 дом', '### 7 дом',
  '## VII дом', '### VII дом',
  '## Партнёрство', '### Партнёрство',
];

function getCutoffText(text) {
  const lines = text.split('\n');
  let sectionCount = 0;
  let cutoffLine = -1;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('## ') || line.startsWith('### ')) {
      sectionCount++;
      const isEmotional = CUTOFF_KEYWORDS.some(k => line.includes(k.replace(/^#+\s/, '')));
      if (sectionCount >= 3 || (sectionCount >= 2 && isEmotional)) {
        cutoffLine = i;
        break;
      }
    }
  }

  if (cutoffLine === -1) return null;
  return lines.slice(0, cutoffLine).join('\n');
}

const SECTION_TITLES_RU = {
  general: 'Общий портрет личности',
  career: 'Карьера и профессиональная реализация',
  relationships: 'Отношения и партнёрство',
  health: 'Здоровье и энергия',
  finance: 'Финансы и материальные ресурсы',
  spirituality: 'Духовное развитие и внутренний рост',
};

function renderMarkdown(text) {
  const lines = text.split('\n');
  return lines.map((line, i) => {
    // Заменяем <section name="..."> на русский заголовок жирным
    const sectionMatch = line.match(/<section name="([^"]+)">/);
    if (sectionMatch) {
      const title = SECTION_TITLES_RU[sectionMatch[1]] || sectionMatch[1];
      return (
        <h2 key={i} style={{
          fontSize: 17, fontWeight: 700,
          color: 'var(--accent, var(--accent))',
          margin: '24px 0 10px',
        }}>
          {title}
        </h2>
      );
    }
    // Убираем </section>
    if (line.trim() === '</section>') return null;

    if (line.startsWith('### ')) {
      return (
        <h3 key={i} style={{
          fontSize: 15, fontWeight: 700,
          color: 'var(--text-primary, var(--border))',
          margin: '20px 0 8px',
          borderBottom: '1px solid var(--border, var(--bg-card))',
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
          color: 'var(--accent, var(--accent))',
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

// ═══════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════

export default function Interpretation({ chartId, userTier, onUpgrade }) {
  const toast = useToast();
  const prefersReduced = useReducedMotion();
  const sectionInitial = prefersReduced ? { opacity: 0 } : { opacity: 0, y: 8 };

  const [sections,   setSections]  = useState([]); // [{ name, title, text }]
  const [streaming, setStreaming] = useState(false);
  const [done,      setDone]      = useState(false);
  const [error,     setError]     = useState(null);
  const [started,   setStarted]   = useState(false);

  const text = sections.map(s => s.text).join('\n\n'); // для paywall-логики

  const scrollRef   = useRef(null);
  const closeSSERef = useRef(null);
  const currentSectionRef = useRef(null);

  const isFree = userTier === 'free' || !userTier;
  const isLite = userTier === 'lite';

  const SECTION_TITLES = {
    general: 'Личность и характер',
    career: 'Карьера и призвание',
    relationships: 'Отношения и партнёрство',
    health: 'Здоровье и энергия',
    finance: 'Финансы',
    spirituality: 'Духовный путь',
  };

  const start = useCallback((retryCount = 0) => {
    if (!chartId) return;
    setSections([]);
    setDone(false);
    setError(null);
    setStreaming(true);
    setStarted(true);
    currentSectionRef.current = null;

    let receivedAny = false;

    const close = streamInterpretation(
      chartId,
      (chunk) => {
        receivedAny = true;
        if (chunk.type === 'section_start') {
          currentSectionRef.current = chunk.name;
          setSections(prev => [...prev, { name: chunk.name, title: SECTION_TITLES[chunk.name] || chunk.name, text: '' }]);
        } else if (chunk.type === 'section_end') {
          currentSectionRef.current = null;
        } else if (chunk.type === 'text') {
          const secName = currentSectionRef.current;
          if (secName) {
            setSections(prev => prev.map(s => s.name === secName ? { ...s, text: s.text + chunk.text } : s));
          } else {
            setSections(prev => {
              if (prev.length === 0) return [{ name: '_intro', title: '', text: chunk.text }];
              const last = prev[prev.length - 1];
              return [...prev.slice(0, -1), { ...last, text: last.text + chunk.text }];
            });
          }
        }
        if (scrollRef.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
      },
      () => { setStreaming(false); setDone(true); },
      (err) => {
        if (!receivedAny && retryCount < 3) {
          console.warn(`SSE retry ${retryCount + 1}`);
          setTimeout(() => start(retryCount + 1), 1500 * (retryCount + 1));
          return;
        }
        const msg = String(err);
        setError(msg);
        setStreaming(false);
        toast.error('Не удалось загрузить интерпретацию');
      },
    );

    closeSSERef.current = close;
  }, [chartId, toast]);

  // ── Не запускались ──

  if (!started) {
    return (
      <div className="solid-card p-6">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--accent, var(--accent))' }}>✦</span>
            AI-интерпретация
          </h2>
        </div>
        <p style={{ fontSize: 13, color: 'var(--color-text-secondary, var(--text-secondary))', margin: '0 0 16px', lineHeight: 1.6 }}>
          Персональный разбор натальной карты — характер, таланты, жизненные темы.
        </p>
        <button
          onClick={() => start()}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 20px', borderRadius: 10,
            border: '1px solid rgba(124,108,255,0.5)',
            background: 'linear-gradient(135deg, rgba(124,108,255,0.12), rgba(167,139,250,0.12))',
            color: 'var(--accent, var(--accent))', fontSize: 14, fontWeight: 600,
            cursor: 'pointer', fontFamily: 'inherit',
            transition: 'all 0.2s',
          }}
        >
          Создать интерпретацию
        </button>
      </div>
    );
  }

  const cutoffText = isFree && done ? getCutoffText(text) : null;
  const isCut = !!cutoffText;
  // Для paywall: обрезаем секции
  const visibleSections = isCut
    ? (() => {
        const cutLine = cutoffText.split('\n').length;
        let total = 0;
        return sections.filter(s => {
          if (total >= cutLine) return false;
          total += s.text.split('\n').length + 2;
          return true;
        });
      })()
    : sections;

  return (
    <div className="solid-card p-6">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: 'var(--accent, var(--accent))' }}>✦</span>
          AI-интерпретация
        </h2>
        
      </div>

      {/* Streaming indicator */}
      {streaming && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
          fontSize: 12, color: 'var(--text-secondary, var(--text-secondary))',
        }}>
          <span style={{
            width: 8, height: 8, borderRadius: 4,
            background: 'var(--accent, var(--accent))',
            animation: 'pulse 1.2s ease infinite',
          }} />
          Генерирую интерпретацию…
          <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }`}</style>
        </div>
      )}

      {/* Progress bar пока нет первого чанка */}
      {streaming && sections.length === 0 && <StreamingProgress />}

      {/* Error */}
      {error && (
        <div style={{
          padding: '16px', borderRadius: 10,
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.2)', marginBottom: 12,
        }}>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--color-danger)' }}>
            Не удалось загрузить интерпретацию: {error}
          </p>
          <button onClick={() => start()} style={{
            marginTop: 10, padding: '6px 16px', borderRadius: 8,
            border: '1px solid rgba(239,68,68,0.4)', background: 'transparent',
            color: 'var(--color-danger)', fontSize: 12, fontWeight: 600, cursor: 'pointer',
          }}>
            ↺ Попробовать снова
          </button>
        </div>
      )}

      {/* Sections */}
      {sections.length > 0 && (
        <div
          ref={scrollRef}
          style={{
            fontSize: 14, color: 'var(--text-primary, var(--border))',
            lineHeight: 1.75,
            maxHeight: 'none',
            overflowY: 'visible',
            paddingRight: 4,
          }}
        >
          <AnimatePresence mode="popLayout">
            {visibleSections.map((sec) => (
              <motion.div
                key={sec.name}
                initial={sectionInitial}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: 'easeOut' }}
                style={{ marginBottom: 24 }}
              >
                {sec.title && (
                  <h2 style={{
                    fontSize: 17, fontWeight: 700,
                    color: 'var(--accent, var(--accent))',
                    margin: '0 0 10px',
                    borderBottom: '1px solid var(--border, var(--bg-card))',
                    paddingBottom: 6,
                  }}>
                    {sec.title}
                  </h2>
                )}
                {renderMarkdown(sec.text)}
              </motion.div>
            ))}
          </AnimatePresence>
          {streaming && (
            <span style={{
              display: 'inline-block', width: 7, height: 17,
              background: 'var(--accent, var(--accent))',
              marginLeft: 2, borderRadius: 2,
              animation: 'blink 0.8s step-end infinite',
              verticalAlign: 'text-bottom',
            }} />
          )}
          <style>{`@keyframes blink { 50%{opacity:0} }`}</style>
        </div>
      )}

      {/* Paywall */}
      {isCut && (
        <div style={{ position: 'relative', marginTop: -60 }}>
          <div style={{
            height: 80,
            background: 'linear-gradient(to bottom, transparent, var(--bg-card, var(--bg)))',
            pointerEvents: 'none',
          }} />
          <div style={{
            padding: '20px 0 4px',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
            textAlign: 'center',
          }}>
            <p style={{ fontSize: 13, color: 'var(--text-secondary, var(--text-secondary))', margin: 0, lineHeight: 1.6 }}>
              Это только начало. Расширенная интерпретация раскрывает<br />
              <strong style={{ color: 'var(--text-primary, var(--border))' }}>Луну, Венеру, 7-й дом и отношения</strong>.
              Открывается на тарифе {TIER_NAMES.lite}.
            </p>
            <button
              onClick={onUpgrade}
              style={{
                padding: '11px 28px', borderRadius: 12, border: 'none',
                background: 'linear-gradient(135deg, var(--accent), var(--accent))',
                color: '#fff', fontSize: 14, fontWeight: 700,
                cursor: 'pointer', fontFamily: 'inherit',
                boxShadow: '0 4px 16px -4px rgba(124,108,255,0.5)',
              }}
            >
              Читать расширенную интерпретацию
            </button>
          </div>
        </div>
      )}

      {/* Inline-баннер для Lite → Pro (под интерпретацией) */}
      {isLite && done && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          marginTop: 24,
          padding: '10px 10px 10px 20px',
          borderRadius: 50,
          background: 'linear-gradient(135deg, var(--accent), var(--accent))',
          boxShadow: '0 8px 32px rgba(124,108,255,0.45)',
          whiteSpace: 'nowrap',
          cursor: 'pointer',
        }} onClick={onUpgrade}>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2, gap: 2 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>Получить расширенную интерпретацию</span>
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.75)' }}>Открывается на тарифе {TIER_NAMES.pro}</span>
          </div>
          <button
            onClick={onUpgrade}
            style={{
              padding: '8px 16px', borderRadius: 50, border: 'none',
              background: '#fff', color: 'var(--accent)',
              fontSize: 12, fontWeight: 800,
              cursor: 'pointer', fontFamily: 'inherit',
              whiteSpace: 'nowrap',
            }}
          >
            НА 2500 СЛОВ
          </button>
        </div>
      )}
    </div>
  );
}
