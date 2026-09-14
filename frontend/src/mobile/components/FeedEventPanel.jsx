/**
 * FeedEventPanel.jsx — панель события по тапу на закрытую карточку.
 *
 * Появилась правкой спецификации 05.09.2026: тизер убран из карточки в
 * потоке (он одинаковый на сотнях событий) и показывается здесь целиком —
 * intro, outro и кнопка доступа. Роль та же, что у LockedTransitPanel на
 * вебе, где разбор тоже открывается отдельной панелью рядом со списком.
 *
 * Снизу, а не по центру: на телефоне низ экрана — единственное место, куда
 * дотягивается большой палец, и лист снизу закрывается тем же движением,
 * которым открылся. Модалка по центру потребовала бы тянуться к крестику.
 *
 * ⚠️ Кнопка «Открыть доступ» пока никуда не ведёт: модалки апгрейда и
 * экрана оплаты в мобильном приложении ещё нет, оба вынесены в отдельные
 * задания. Это заявленное состояние, а не забытый провод — поэтому кнопка
 * отрисована по спецификации, но неактивна, пока не передан `onUpgrade`.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { eventTitle, signRu, timePart } from '../lib/feedTime';
import { transitTeaserText } from '../lib/transitTeaser';
import { openInBrowser } from '../lib/openInBrowser';
import { PRICING_URL } from '../lib/onboardingCopy';
import {
  canInterpretTransit,
  streamTransitInterpretation,
} from '../lib/transitInterpretApi';
import {
  TRANSIT_OUTCOMES,
  classifyTransitError,
  transitUpsellFor,
} from '../lib/transitInterpretRules';
import useTier from '../lib/useTier';

export default function FeedEventPanel({ event, chartId, onClose, onUpgrade }) {
  // ⚠️ Хуки объявлены ДО раннего выхода: порядок вызовов обязан быть
  // одинаковым на каждом рендере, иначе React ломается на первом закрытии
  // панели. Поэтому проверка на пустое событие живёт ниже, а не первой
  // строкой, как было до появления разбора.
  const { tier, known } = useTier();
  const [text, setText] = useState('');
  const [status, setStatus] = useState('idle');   // idle | loading | done | failed
  const [failure, setFailure] = useState(null);
  const runIdRef = useRef(0);

  // Смена события — сбрасываем всё: панель переиспользуется под разные
  // транзиты, и текст предыдущего в новом виден быть не должен.
  useEffect(() => {
    runIdRef.current += 1;
    setText('');
    setStatus('idle');
    setFailure(null);
  }, [event?.key]);

  const start = useCallback(async () => {
    if (!chartId || !event) return;
    const run = ++runIdRef.current;
    setText('');
    setFailure(null);
    setStatus('loading');
    try {
      await streamTransitInterpretation(chartId, event, {
        onText: (chunk) => {
          if (runIdRef.current === run) setText((prev) => prev + chunk);
        },
      });
      if (runIdRef.current === run) setStatus('done');
    } catch (err) {
      if (runIdRef.current !== run) return;
      // authenticated: true — панель существует только внутри сессии; ветка
      // анонима остаётся в правилах ради полноты, но досюда не доходит.
      setFailure(classifyTransitError({
        status: err?.status,
        detail: err?.detail,
        authenticated: true,
      }));
      setStatus('failed');
    }
  }, [chartId, event]);

  if (!event) return null;

  const meta = event.meta || {};
  const isTransit = event.kind === 'transit';
  const canAsk = isTransit && !!chartId && canInterpretTransit(event);
  const upsell = transitUpsellFor({
    tier, known, finished: status === 'done', failed: status === 'failed',
  });
  const hasSigns = meta.transit_sign && meta.natal_sign;
  // null, если данных в meta не хватило — тогда покажется серверный текст.
  const composedTeaser = transitTeaserText(event);
  const degree = typeof meta.transit_degree === 'number'
    ? `${meta.transit_degree.toFixed(1)}° `
    : '';

  return (
    <>
      {/* Затемнение: тап мимо панели закрывает её — привычнее, чем искать
          крестик, и не требует объяснения. */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.45)',
          zIndex: 20,
        }}
      />
      <div
        role="dialog"
        aria-label={eventTitle(event)}
        style={{
          position: 'fixed',
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 21,
          background: 'var(--bg-card)',
          borderTopLeftRadius: 20,
          borderTopRightRadius: 20,
          borderTop: '1px solid var(--border)',
          padding: '8px 20px 20px',
          paddingBottom: 'calc(20px + env(safe-area-inset-bottom))',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          maxHeight: '80%',
          overflowY: 'auto',
        }}
      >
        {/* Полоска-ручка: показывает, что лист снизу и его можно закрыть. */}
        <div
          style={{
            alignSelf: 'center',
            width: 36,
            height: 4,
            borderRadius: 'var(--radius-full)',
            background: 'var(--border)',
            marginBottom: 4,
          }}
        />

        <div>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.09em',
              fontFamily: 'var(--font-body)',
              color: 'var(--text-secondary)',
            }}
          >
            {timePart(event.at)}
          </div>
          <h2
            style={{
              margin: '4px 0 0',
              fontSize: 22,
              fontWeight: 700,
              fontFamily: 'var(--font-display)',
              color: 'var(--text-primary)',
              lineHeight: 1.25,
            }}
          >
            {eventTitle(event)}
          </h2>
          {hasSigns && (
            <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
              {degree}{signRu(meta.transit_sign)} → {signRu(meta.natal_sign)}
            </div>
          )}
        </div>

        {/* Тизер прячется, как только пошёл разбор: он подводка к тексту, а
            не спутник ему.

            ⚠️ Строка собирается из meta КОНКРЕТНОГО события
            (transitTeaser.js). Прежде сервер отдавал одну и ту же фразу на
            все транзиты подряд («Это активный период по одной из ключевых
            тем вашей карты…»), и десять открытых карточек читались
            одинаково — продать такое нельзя.

            Серверный текст остаётся запасным путём: не хватило данных на
            осмысленную строку — показываем общую правду, а не частное
            правдоподобие. Он же остаётся у периодов планера, где своей
            сборки нет. */}
        {(composedTeaser || event.teaser) && status === 'idle' && (
          <div style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
            {composedTeaser
              ? <p style={{ margin: 0 }}>{composedTeaser}</p>
              : (
                <>
                  {event.teaser.intro && <p style={{ margin: 0 }}>{event.teaser.intro}</p>}
                  {event.teaser.outro && <p style={{ margin: '10px 0 0' }}>{event.teaser.outro}</p>}
                </>
              )}
          </div>
        )}

        {status === 'loading' && !text && (
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            Разбор готовится. Первые строки появятся через несколько секунд.
          </p>
        )}

        {/* pre-wrap: секций в транзитном тексте нет, разбирать нечего — это
            проза с переводами строк (см. шапку transitInterpretApi.js). */}
        {text && (
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 14.5, lineHeight: 1.7, color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
            {text}
          </div>
        )}

        {/* Отказ — ПОД уже набранным текстом: то, что успело прийти, человек
            уже прочитал, и убирать это нельзя. */}
        {failure && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <p
              role="alert"
              style={{
                margin: 0, fontSize: 13.5, lineHeight: 1.6,
                color: failure.outcome === TRANSIT_OUTCOMES.BROKEN
                  ? 'var(--text-secondary)' : 'var(--color-danger)',
              }}
            >
              {failure.text}
            </p>
            {failure.showPricing && (
              <button
                type="button"
                className="mobile-btn-primary"
                style={{ height: 44, fontSize: 14 }}
                onClick={() => openInBrowser(PRICING_URL)}
              >
                Открыть тарифы
              </button>
            )}
            {failure.canRetry && (
              <button type="button" className="mobile-link" style={{ alignSelf: 'flex-start' }} onClick={start}>
                Повторить
              </button>
            )}
          </div>
        )}

        {/* Приписка про старший тариф — только на успешно завершённом разборе
            и только при известном тарифе (transitUpsellFor). */}
        {upsell?.kind === 'free' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)', textAlign: 'center' }}>
              {upsell.text}
            </p>
            <button type="button" className="mobile-link" onClick={() => openInBrowser(PRICING_URL)}>
              {upsell.cta}
            </button>
          </div>
        )}
        {upsell?.kind === 'lite' && (
          <div style={{ padding: '12px 14px', borderRadius: 'var(--radius-lg)', background: 'var(--bg-deeper)', border: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div>
              <p style={{ margin: 0, fontSize: 13.5, fontWeight: 600, color: 'var(--text-primary)' }}>{upsell.title}</p>
              <p style={{ margin: '2px 0 0', fontSize: 12.5, color: 'var(--text-secondary)' }}>{upsell.subtitle}</p>
            </div>
            <button type="button" className="mobile-btn-primary" style={{ height: 42, fontSize: 13 }} onClick={() => openInBrowser(PRICING_URL)}>
              {upsell.cta}
            </button>
          </div>
        )}

        {/* «Разобрать транзит» — только у транзитов и только пока разбора нет.
            Доступ решает сервер: своей копии тарифной сетки клиент не держит и
            заранее ничего не запрещает. */}
        {canAsk && status === 'idle' && (
          <button type="button" className="mobile-btn-primary" onClick={start}>
            Разобрать транзит
          </button>
        )}

        {!isTransit && (
          <button
            type="button"
            className="mobile-btn-primary"
            disabled={!onUpgrade}
            onClick={onUpgrade ? () => onUpgrade(event) : undefined}
          >
            Открыть доступ
          </button>
        )}
        <button type="button" className="mobile-link" onClick={onClose} style={{ alignSelf: 'center' }}>
          Закрыть
        </button>
      </div>
    </>
  );
}
