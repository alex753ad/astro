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

import React from 'react';
import { signRu, timePart } from '../lib/feedTime';

export default function FeedEventPanel({ event, onClose, onUpgrade }) {
  if (!event) return null;

  const meta = event.meta || {};
  const hasSigns = meta.transit_sign && meta.natal_sign;
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
        aria-label={event.text || 'Событие'}
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
            borderRadius: 999,
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
              fontFamily: 'var(--font-display)',
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
            {event.text || '—'}
          </h2>
          {hasSigns && (
            <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
              {degree}{signRu(meta.transit_sign)} → {signRu(meta.natal_sign)}
            </div>
          )}
        </div>

        {event.teaser && (
          <div style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
            {event.teaser.intro && <p style={{ margin: 0 }}>{event.teaser.intro}</p>}
            {event.teaser.outro && <p style={{ margin: '10px 0 0' }}>{event.teaser.outro}</p>}
          </div>
        )}

        <button
          type="button"
          className="mobile-btn-primary"
          disabled={!onUpgrade}
          onClick={onUpgrade ? () => onUpgrade(event) : undefined}
        >
          Открыть доступ
        </button>
        <button type="button" className="mobile-link" onClick={onClose} style={{ alignSelf: 'center' }}>
          Закрыть
        </button>
      </div>
    </>
  );
}
