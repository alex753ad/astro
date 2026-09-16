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
import { Link } from 'react-router-dom';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { streamInterpretation } from '../api/client';
import { SECTION_TITLES, stripSectionTags } from '../lib/sectionStream';
import { interpretationUpsell } from '../lib/interpretationUpsell';
import { useToast } from './Toast';

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
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', minHeight: 18 }}>
        {STAGES[stageIdx]}
      </div>
      <div style={{
        width: '100%', height: 4, borderRadius: 2,
        background: 'var(--border)', overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', width: `${progress}%`, borderRadius: 2,
          background: 'linear-gradient(90deg, var(--accent), var(--accent))',
          transition: 'width 1s cubic-bezier(0.4,0,0.2,1)',
        }} />
      </div>
    </div>
  );
}

// ── Paywall helpers ────────────────────────────────────────

function renderMarkdown(text) {
  const lines = text.split('\n');
  return lines.map((raw, i) => {
    // Разметка секций до рендера не доезжает — её снимает парсер потока
    // (lib/sectionStream.js), а заголовок рисуется из sec.title. Чистка
    // осталась подстраховкой: если тег всё же просочится (текст,
    // сохранённый в БД до 07.09.2026, ошибка модели), он не должен быть
    // показан человеку как проза.
    //
    // До 07.09.2026 здесь стоял ВТОРОЙ путь отрисовки заголовков: строка
    // <section name="..."> превращалась в <h2> по собственному словарю
    // SECTION_TITLES_RU. Он и маскировал дефект flushBuffer на живой
    // генерации — утёкшие обрывки тегов склеивались в тексте обратно, и
    // заголовки рисовались отсюда, а не из sec.title (разбор —
    // INTERPRET_SSE_RECON.md §3). Словарь удалён вместе с ним: заголовки
    // секций берутся ровно из одного места — SECTION_TITLES, который с
    // 08.09.2026 лежит в lib/sectionStream.js (там же причина переноса).
    const line = stripSectionTags(raw);
    // Строка состояла только из разметки — не рисуем вовсе. Пустую строку
    // ниже ждёт <br>, и без этой ветки на месте тега появился бы разрыв.
    if (line !== raw && !line.trim()) return null;

    if (line.startsWith('### ')) {
      return (
        <h3 key={i} style={{
          fontSize: 15, fontWeight: 700,
          color: 'var(--text-primary)',
          margin: '20px 0 8px',
          borderBottom: '1px solid var(--border)',
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
          color: 'var(--accent)',
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


  const scrollRef   = useRef(null);
  const closeSSERef = useRef(null);
  const currentSectionRef = useRef(null);

  const isFree = userTier === 'free' || !userTier;
  const isLite = userTier === 'lite';

  // Тексты приписки — общий файл с мобильным клиентом
  // (lib/interpretationUpsell.js), там же правило «кому показывать».
  // Здесь остаётся только разметка: у веба это <Link> роутера, у
  // приложения — кнопка с openInBrowser.
  const upsell = interpretationUpsell(isFree ? 'free' : userTier);
  const liteUpsell = interpretationUpsell('lite');
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
        const msg = String(err);
        // 'Connection lost' — единственный текст, который _connectSSE отдаёт
        // при обрыве транспорта (api/client.js). Всё остальное пришло от
        // сервера полем error внутри потока и уже является объяснением на
        // русском — его и показываем, не заменяя общей фразой и не пряча за
        // приставкой «Не удалось загрузить интерпретацию».
        const isTransport = msg === 'Connection lost';

        // Ретраим только обрыв связи. Раньше повтор шёл на любую ошибку: если
        // сервер прислал причину (например исчерпан дневной бюджет AI), три
        // попытки по 1.5/3/4.5 сек ничего не меняли и лишь на 9 секунд
        // откладывали сообщение, которое уже было известно.
        if (!receivedAny && isTransport && retryCount < 3) {
          console.warn(`SSE retry ${retryCount + 1}`);
          setTimeout(() => start(retryCount + 1), 1500 * (retryCount + 1));
          return;
        }

        setError(isTransport
          ? 'Соединение прервалось. Проверьте связь и попробуйте снова.'
          : msg);
        setStreaming(false);
        toast.error(isTransport ? 'Соединение прервалось' : msg);
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
            <span style={{ color: 'var(--accent)' }}>✦</span>
            AI-интерпретация
          </h2>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 16px', lineHeight: 1.6 }}>
          Персональный разбор натальной карты — характер, таланты, жизненные темы.
        </p>
        <button
          onClick={() => start()}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 20px', borderRadius: 'var(--radius-md)',
            border: '1px solid rgba(var(--accent-rgb), 0.5)',
            background: 'linear-gradient(135deg, rgba(var(--accent-rgb), 0.12), rgba(var(--accent-glow-rgb), 0.12))',
            color: 'var(--accent)', fontSize: 14, fontWeight: 600,
            cursor: 'pointer', fontFamily: 'inherit',
            transition: 'all 0.2s',
          }}
        >
          Создать интерпретацию
        </button>
      </div>
    );
  }

  // Усечения для free здесь больше нет, и это не потеря функции — она не
  // работала ни разу. `getCutoffText` искал markdown-заголовки `## `/`### `,
  // а сервер их не выдаёт: промпт требует `<section name="…">`
  // (backend/interpretation/prompts.py, «Формат ответа»), и парсер снимает
  // эти теги до рендера. Проверено на настоящем разборе с боевого аккаунта
  // 09.09.2026: строк, начинающихся с `## `, — ноль, вхождений `**` — ноль.
  // Значит getCutoffText всегда возвращал null, isCut всегда был false, а
  // блок пейволла не рисовался никогда. Тестов у него не было.
  //
  // ⚠️ Понадобится усечение снова — делать его по `sections`, которые
  // парсер уже разобрал, а не поиском разметки в склеенном тексте:
  // разметки там нет по построению.
  const visibleSections = sections;

  return (
    <div className="solid-card p-6">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: 'var(--accent)' }}>✦</span>
          AI-интерпретация
        </h2>
        
      </div>

      {/* Streaming indicator */}
      {streaming && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
          fontSize: 12, color: 'var(--text-secondary)',
        }}>
          <span style={{
            width: 8, height: 8, borderRadius: 4,
            background: 'var(--accent)',
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
          padding: '16px', borderRadius: 'var(--radius-md)',
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.2)', marginBottom: 12,
        }}>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--color-danger)' }}>
            {error}
          </p>
          <button onClick={() => start()} style={{
            marginTop: 10, padding: '6px 16px', borderRadius: 'var(--radius-sm)',
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
            // Тело разбора — антиква (DESIGN_SYSTEM.md §3): это чтение, а не
            // интерфейс. Стоит на контейнере, а не на каждом абзаце — внутри
            // рендерятся ещё заголовки секций, и им нужна та же гарнитура.
            fontFamily: 'var(--font-display)',
            fontSize: 14, color: 'var(--text-primary)',
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
                    color: 'var(--accent)',
                    margin: '0 0 10px',
                    borderBottom: '1px solid var(--border)',
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
              background: 'var(--accent)',
              marginLeft: 2, borderRadius: 2,
              animation: 'blink 0.8s step-end infinite',
              verticalAlign: 'text-bottom',
            }} />
          )}
          <style>{`@keyframes blink { 50%{opacity:0} }`}</style>
        </div>
      )}

      {/* Приписка для Free: полная интерпретация — на следующем тарифе.
          Lite уже закрыт отдельным баннером ниже (isLite && done) — не дублируем. */}
      {isFree && done && (
        <p style={{
          marginTop: 20,
          fontSize: 13,
          color: 'var(--text-secondary)',
          textAlign: 'center',
          lineHeight: 1.6,
        }}>
          {upsell?.text}{' '}
          <Link to="/pricing" style={{ color: 'var(--accent)', fontWeight: 600, textDecoration: 'none' }}>
            {upsell?.cta}
          </Link>
        </p>
      )}

      {/* Inline-баннер для Lite → Pro (под интерпретацией) */}
      {isLite && done && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          marginTop: 24,
          padding: '10px 10px 10px 20px',
          borderRadius: 'var(--radius-full)',
          background: 'var(--accent)',
          boxShadow: '0 8px 32px rgba(var(--accent-rgb), 0.45)',
          whiteSpace: 'nowrap',
          cursor: 'pointer',
        }} onClick={onUpgrade}>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2, gap: 2 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-on)' }}>{liteUpsell?.title}</span>
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.75)' }}>{liteUpsell?.subtitle}</span>
          </div>
          <button
            onClick={onUpgrade}
            style={{
              padding: '8px 16px', borderRadius: 'var(--radius-full)', border: 'none',
              background: '#fff', color: 'var(--accent)',
              fontSize: 12, fontWeight: 800,
              cursor: 'pointer', fontFamily: 'inherit',
              whiteSpace: 'nowrap',
            }}
          >
            {liteUpsell?.cta}
          </button>
        </div>
      )}
    </div>
  );
}
