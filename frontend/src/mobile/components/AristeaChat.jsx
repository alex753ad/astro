/**
 * AristeaChat.jsx — чат с Аристеей. Заменил собой AristeaChatStub.jsx.
 *
 * Шторка снизу по образцу FeedEventPanel.jsx — место под неё так и
 * готовилось: не отдельный экран и не роут, а оверлей поверх текущей вкладки.
 * Низ экрана — единственное место, куда дотягивается большой палец, и лист
 * снизу закрывается тем же движением, которым открылся.
 *
 * ⚠️ **Карта берётся с того экрана, с которого открыли кнопку, а не «основная»**
 * (решение владельца). У «Ленты» и «Карты» они могут быть разными: после
 * построения новой карты «Карта» показывает её по локальному переопределению, а
 * «Лента» — по-прежнему закреплённую (SPEC_CHART_CREATE.md §11). Диалог у
 * каждой карты свой, поэтому имя карты стоит в шапке: без него переключение
 * вкладки читалось бы как пропажа истории.
 *
 * ⚠️ Высота шторки фиксированная (85%), а не по контенту. У FeedEventPanel
 * стоит `maxHeight` и высота растёт от текста — здесь так нельзя: список
 * сообщений растёт во время ответа, и шторка прыгала бы вверх на каждом
 * чанке, утаскивая поле ввода из-под пальца.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { fetchChatHistory, streamChatAnswer, ChatError } from '../lib/ragChatApi';
import {
  classifyChatError,
  hasScrolledAway,
  shouldReportInterrupted,
  shouldStickToBottom,
} from '../lib/chatRules';
import { openInBrowser } from '../lib/openInBrowser';
import { PRICING_URL } from '../lib/onboardingCopy';

const MAX_QUESTION_LEN = 1000;   // столько же принимает сервер (rag_router.py)

export default function AristeaChat({ chart, onClose }) {
  const chartId = chart?.id || null;

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState('loading');  // loading | ready | failed
  const [streaming, setStreaming] = useState(false);
  const [failure, setFailure] = useState(null);
  const [historyError, setHistoryError] = useState('');

  const listRef = useRef(null);
  // Ушёл ли человек от низа сам. Ref, а не state: читается из обработчика
  // прокрутки и из эффекта дописывания, а перерисовка от него не нужна.
  const scrolledAwayRef = useRef(false);
  // Состояние для обработчика видимости читается из ref: обработчик вешается
  // один раз и иначе видел бы значения на момент подписки (тот же приём, что
  // в InterpretView.jsx).
  const streamingRef = useRef(false);
  streamingRef.current = streaming;

  // ── История ───────────────────────────────────────────────────────────
  // Копии на клиенте нет: единственный источник — сервер. Пустой ответ здесь
  // нормальное состояние (первый вопрос по карте либо диалог истёк по TTL),
  // поэтому пустота — это не ошибка и экрана отказа не даёт.
  useEffect(() => {
    if (!chartId) return undefined;
    let alive = true;
    setStatus('loading');
    setHistoryError('');
    fetchChatHistory(chartId)
      .then((loaded) => {
        if (!alive) return;
        setMessages(loaded);
        setStatus('ready');
      })
      .catch((err) => {
        if (!alive) return;
        // ⚠️ Отказ истории НЕ закрывает чат: спросить всё равно можно, сервер
        // свою историю в промпт подмешает сам. Поэтому предупреждение сверху,
        // а не экран ошибки вместо чата.
        const { text } = classifyChatError({
          status: err instanceof ChatError ? err.status : undefined,
          detail: err instanceof ChatError ? err.detail : '',
        });
        setHistoryError(text);
        setStatus('ready');
      });
    return () => { alive = false; };
  }, [chartId]);

  // ── Прокрутка ─────────────────────────────────────────────────────────
  const stickToBottom = useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (shouldStickToBottom({ distanceFromBottom, userScrolledAway: scrolledAwayRef.current })) {
      el.scrollTop = el.scrollHeight;
    }
  }, []);

  const handleScroll = useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    scrolledAwayRef.current = hasScrolledAway({ distanceFromBottom });
  }, []);

  useEffect(() => { stickToBottom(); }, [messages, stickToBottom]);

  // ⚠️ Повтор после того, как раскладка устоялась. Локальный Inter догружается
  // и подменяет запасной шрифт — высоты всех сообщений пересчитываются уже
  // ПОСЛЕ прокрутки, и низ уезжает вниз. Тот же капкан, что у якоря ленты
  // (CLAUDE.md, «Прокрутка к якорю сбивается подменой шрифта»).
  useEffect(() => {
    if (!document.fonts?.ready) return undefined;
    let alive = true;
    document.fonts.ready.then(() => { if (alive) stickToBottom(); });
    return () => { alive = false; };
  }, [stickToBottom]);

  // ── Возврат из фона ───────────────────────────────────────────────────
  // Поток НЕ перезапрашиваем: повтор это новый вызов модели, ещё одна попытка
  // из двадцати в час и вторая пара «вопрос-ответ» в серверной истории. Вместо
  // этого честно говорим, что ответ не дошёл (см. shouldReportInterrupted).
  useEffect(() => {
    const onVisible = () => {
      if (!shouldReportInterrupted({
        visible: document.visibilityState === 'visible',
        streaming: streamingRef.current,
      })) return;
      setStreaming(false);
      setFailure(classifyChatError({}));
      setMessages((prev) => dropEmptyAnswer(prev));
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, []);

  // ── Отправка ──────────────────────────────────────────────────────────
  const send = useCallback(async () => {
    const question = input.trim().slice(0, MAX_QUESTION_LEN);
    if (!question || streaming || !chartId) return;

    setInput('');
    setFailure(null);
    scrolledAwayRef.current = false;   // свой вопрос всегда показываем целиком
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: question },
      { role: 'assistant', content: '' },
    ]);
    setStreaming(true);

    try {
      await streamChatAnswer(chartId, question, {
        onText: (chunk) => setMessages((prev) => appendToAnswer(prev, chunk)),
      });
    } catch (err) {
      setFailure(classifyChatError({
        status: err instanceof ChatError ? err.status : undefined,
        detail: err instanceof ChatError ? err.detail : '',
      }));
      // ⚠️ Уже пришедший текст оставляем видимым — убираем только пустой
      // пузырёк. Обрыв на середине ответа не повод стирать то, что человек
      // уже прочитал; и сервер эту пару, скорее всего, уже записал.
      setMessages((prev) => dropEmptyAnswer(prev));
    } finally {
      setStreaming(false);
    }
  }, [input, streaming, chartId]);

  const disabled = streaming || !input.trim() || !chartId;

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
          height: '85%',
          background: 'var(--bg-card)',
          borderTopLeftRadius: 20,
          borderTopRightRadius: 20,
          borderTop: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
        }}
      >
        {/* Шапка: имя карты — чтобы смена диалога при переключении вкладки не
            читалась как пропажа истории. */}
        <div style={{ padding: '8px 20px 12px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <div style={{ width: 36, height: 4, borderRadius: 999, background: 'var(--border)', margin: '0 auto 10px' }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span
              aria-hidden="true"
              style={{
                width: 32, height: 32, borderRadius: '50%', background: 'var(--accent)', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, flexShrink: 0,
              }}
            >
              ✦
            </span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                Аристея
              </div>
              <div style={{
                fontSize: 12, color: 'var(--text-secondary)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                по карте «{chart?.name || 'Натальная карта'}»
              </div>
            </div>
            <button type="button" className="mobile-link" onClick={onClose} style={{ flexShrink: 0 }}>
              Закрыть
            </button>
          </div>
        </div>

        {/* Лента сообщений */}
        <div
          ref={listRef}
          onScroll={handleScroll}
          onTouchStart={handleScroll}
          style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}
        >
          {historyError && (
            <div role="status" style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)', textAlign: 'center' }}>
              {historyError} Спросить всё равно можно.
            </div>
          )}

          {status === 'loading' && (
            <div className="mobile-skeleton" style={{ height: 56, borderRadius: 12 }} />
          )}

          {status === 'ready' && messages.length === 0 && !historyError && (
            <div style={{ margin: 'auto', textAlign: 'center', maxWidth: 260, color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.6 }}>
              Аристея знает эту карту. Спросите про период, аспект или сферу
              жизни — она ответит по вашей карте, а не вообще.
            </div>
          )}

          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} content={m.content} />
          ))}

          {streaming && <TypingDots />}

          {failure && (
            <div role="alert" style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)', textAlign: 'center' }}>
              {failure.text}
              {failure.showPricing && (
                <div style={{ marginTop: 8 }}>
                  <button type="button" className="mobile-link" onClick={() => openInBrowser(PRICING_URL)}>
                    Открыть тарифы
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Поле ввода */}
        <div style={{
          flexShrink: 0,
          borderTop: '1px solid var(--border)',
          padding: '10px 16px',
          paddingBottom: 'calc(10px + env(safe-area-inset-bottom))',
          display: 'flex',
          gap: 8,
          alignItems: 'flex-end',
        }}>
          <textarea
            className="mobile-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Спросить про карту…"
            rows={1}
            maxLength={MAX_QUESTION_LEN}
            style={{ flex: 1, resize: 'none', maxHeight: 96, minHeight: 40, paddingTop: 10, paddingBottom: 10 }}
          />
          <button
            type="button"
            className="mobile-btn-primary"
            onClick={send}
            disabled={disabled}
            aria-label="Отправить вопрос"
            style={{ flexShrink: 0, width: 44, height: 44, borderRadius: 22, padding: 0, minWidth: 0 }}
          >
            ↑
          </button>
        </div>
      </div>
    </>
  );
}

/** Дописать чанк в последний пузырёк ассистента. */
export function appendToAnswer(messages, chunk) {
  const next = [...messages];
  const last = next[next.length - 1];
  if (last?.role === 'assistant') {
    next[next.length - 1] = { ...last, content: last.content + chunk };
  }
  return next;
}

/** Убрать пустой пузырёк ассистента, оставив уже пришедший текст. */
export function dropEmptyAnswer(messages) {
  const last = messages[messages.length - 1];
  if (last?.role === 'assistant' && !last.content) return messages.slice(0, -1);
  return messages;
}

function Bubble({ role, content }) {
  const mine = role === 'user';
  return (
    <div style={{ display: 'flex', justifyContent: mine ? 'flex-end' : 'flex-start' }}>
      <div style={{
        maxWidth: '86%',
        padding: '10px 14px',
        borderRadius: 16,
        borderBottomRightRadius: mine ? 4 : 16,
        borderBottomLeftRadius: mine ? 16 : 4,
        // --border, а не --bg-deeper: тот почти неотличим от --bg-card в
        // светлой теме (#FDFBFF против #FFFFFF), и пузырёк пропал бы.
        background: mine ? 'var(--accent)' : 'var(--border)',
        color: mine ? '#fff' : 'var(--text-primary)',
        fontSize: 14.5,
        lineHeight: 1.7,
        // Разметки в ответе нет — сервер отдаёт обычный текст, как и разбор
        // транзита в FeedEventPanel. Markdown-рендерер здесь не нужен.
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}>
        {content}
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <div aria-live="polite" style={{ fontSize: 13, color: 'var(--text-secondary)', paddingLeft: 4 }}>
      Аристея печатает…
    </div>
  );
}
