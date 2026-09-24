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

/**
 * ⚠️ Реплики чата набраны ГРОТЕСКОМ (var(--font-body)), хотя это проза модели.
 * Осознанное исключение из §3 DESIGN_SYSTEM.md, решение владельца 14.09.2026.
 *
 * Правило §3 говорит: проза модели, читаемая подряд, — антиква. Чат под первую
 * половину подходит, под вторую нет: реплики читаются как ДИАЛОГ, а не как
 * текст. Они короткие и чередуются с репликами человека, а те останутся
 * гротеском при любом решении — набрать ответы Аристеи антиквой значит набрать
 * один разговор двумя гарнитурами.
 *
 * Хуже того, это размыло бы само различие, ради которого пара и заводилась:
 * антиква перестала бы означать «это длинный текст, сядь и читай» и стала бы
 * означать «это сказала модель» — а модель в приложении говорит почти везде.
 *
 * ⚠️ Поэтому место выглядит непоследовательным ровно до этого комментария.
 * Не «приводить в соответствие» с разбором транзита в FeedEventPanel.jsx:
 * там антиква стоит правильно, и это не то же самое.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { fetchChatHistory, streamChatAnswer, ChatError } from '../lib/ragChatApi';
import {
  classifyChatError,
  hasScrolledAway,
  shouldReportNoAnswer,
  shouldStickToBottom,
} from '../lib/chatRules';
import { CHAT_GREETING, CHAT_SUGGESTIONS } from '../../lib/chatSuggestions';
import { openPaySheet } from '../lib/paySheetBus';

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
  // Пришёл ли хоть один кусок текста в ТЕКУЩЕМ ответе. Ref, а не state:
  // читается синхронно сразу после завершения потока, до перерисовки.
  const gotTextRef = useRef(false);

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

  // ── Возврата из фона здесь БОЛЬШЕ НЕТ, и это правка, а не пропуск ──────
  //
  // ⚠️ Обработчик `visibilitychange` стоял здесь до 09.09.2026 и показывал
  // «Ответ не дошёл» ВСЕГДА: он судил по флагу `streaming`, а тот означает
  // «промис не разрешён», а не «текста нет». На возврате из фона он
  // гарантированно `true` — заморозить WebView можно ровно тогда, когда
  // запрос в полёте. Человек видел готовый ответ и под ним сообщение, что
  // ответ не дошёл.
  //
  // Уточнить условие нельзя: на возврате ещё не разобраны уже пришедшие
  // байты, поэтому и «пришёл ли текст» там даст `false`. Момент возврата в
  // принципе не годится как точка решения — оно перенесено на завершение
  // потока (см. ниже, shouldReportNoAnswer).
  //
  // ⚠️ Тот обработчик вдобавок звал `dropEmptyAnswer` на живом потоке: пузырёк
  // ассистента исчезал, а приходивший следом текст `appendToAnswer` выбрасывал
  // молча — он дописывает, только если последний в списке ассистент. На
  // возврате из фона это был самый вероятный случай: ответ терялся целиком.
  // Поэтому правило теперь простое — **пузырёк не трогаем, пока поток жив**.

  // ── Отправка ──────────────────────────────────────────────────────────
  const send = useCallback(async (asked) => {
    // Аргумент — для подсказок в пустом чате; без него берём поле ввода.
    const raw = typeof asked === 'string' ? asked : input;
    const question = raw.trim().slice(0, MAX_QUESTION_LEN);
    if (!question || streaming || !chartId) return;

    setInput('');
    setFailure(null);
    gotTextRef.current = false;
    scrolledAwayRef.current = false;   // свой вопрос всегда показываем целиком
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: question },
      { role: 'assistant', content: '' },
    ]);
    setStreaming(true);

    let failed = null;
    try {
      await streamChatAnswer(chartId, question, {
        onText: (chunk) => {
          gotTextRef.current = true;
          setMessages((prev) => appendToAnswer(prev, chunk));
        },
      });
    } catch (err) {
      failed = classifyChatError({
        status: err instanceof ChatError ? err.status : undefined,
        detail: err instanceof ChatError ? err.detail : '',
      });
      setFailure(failed);
    } finally {
      setStreaming(false);
    }

    // ⚠️ Решение о «не дошёл» принимается ЗДЕСЬ, после завершения потока, а не
    // на возврате из фона: раньше там оно было заведомо ложным (см. блок выше).
    // Судим по тому, пришёл ли текст.
    if (shouldReportNoAnswer({ streaming: false, gotText: gotTextRef.current, failed: !!failed })) {
      setFailure(classifyChatError({}));
    }
    // Пузырёк трогаем только теперь, когда поток точно кончился: пустой
    // убираем, с текстом — оставляем как есть, даже если ответ оборвался.
    setMessages((prev) => dropEmptyAnswer(prev));
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
          <div style={{ width: 36, height: 4, borderRadius: 'var(--radius-full)', background: 'var(--border)', margin: '0 auto 10px' }} />
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
            <div className="mobile-skeleton" style={{ height: 56, borderRadius: 'var(--radius-md)' }} />
          )}

          {/* Пустая шторка человека теряет: он не знает, что тут спрашивать и
              какими словами. Поэтому приветствие и готовые вопросы тапом —
              показываются, только пока разговора нет. Фразы общие с вебом
              (lib/chatSuggestions.js), второй копии здесь нет.

              ⚠️ Приветствие — не сообщение диалога: на сервер не уходит, в
              историю не пишется. Иначе оно съедало бы одну из десяти позиций
              серверной истории, ничего не добавляя модели. */}
          {status === 'ready' && messages.length === 0 && !historyError && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 'auto', marginBottom: 4 }}>
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div style={{
                  maxWidth: '90%', padding: '12px 14px', borderRadius: 'var(--radius-lg)', borderBottomLeftRadius: 4,
                  background: 'var(--border)', color: 'var(--text-primary)',
                  fontSize: 14.5, lineHeight: 1.7,
                }}>
                  {CHAT_GREETING}
                </div>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'flex-end' }}>
                {CHAT_SUGGESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => send(q)}
                    disabled={streaming || !chartId}
                    style={{
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-lg)',
                      border: '1px solid var(--accent)',
                      background: 'transparent',
                      color: 'var(--accent)',
                      fontSize: 13,
                      lineHeight: 1.4,
                      textAlign: 'left',
                      maxWidth: '100%',
                    }}
                  >
                    {q}
                  </button>
                ))}
              </div>
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
                  <button type="button" className="mobile-link" onClick={() => openPaySheet()}>
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

/**
 * Дописать чанк в последний пузырёк ассистента.
 *
 * ⚠️ Если последний в списке НЕ ассистент, заводим новый пузырёк, а не
 * выбрасываем чанк. Раньше здесь стоял молчаливый пропуск, и он терял ответ
 * целиком: обработчик возврата из фона успевал убрать пустой пузырёк
 * (`dropEmptyAnswer`), последним оставалось сообщение человека — и весь
 * пришедший следом текст исчезал. Замерено: после «первая часть » список
 * оставался `[{role:'user'}]`, и дописывать было некуда.
 *
 * Причина той гонки убрана (пузырёк не трогаем, пока поток жив), но
 * молчаливая потеря текста — слишком дорогой способ узнать о следующей такой
 * правке. Здесь закрыт КЛАСС: что бы ни случилось со списком, пришедший от
 * модели текст остаётся на экране.
 */
export function appendToAnswer(messages, chunk) {
  const next = [...messages];
  const last = next[next.length - 1];
  if (last?.role === 'assistant') {
    next[next.length - 1] = { ...last, content: last.content + chunk };
    return next;
  }
  next.push({ role: 'assistant', content: chunk });
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
        borderRadius: 'var(--radius-lg)',
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
