/**
 * ChatOfferSheet.jsx — нажали на замок у кнопки чата (решение владельца
 * 27.09.2026): сначала что такое чат, потом предложение тарифа, как на вебе.
 *
 * Тариф — по правилу lib/offerRule.js, текст о чате — из каталога витрины
 * (lib/tierCatalog.js). «Не сейчас» просто закрывает. Сам лист не открывается никогда — только по
 * нажатию на замок.
 */

import React from 'react';
import { TIER_NAMES, tierPriceLabel } from '../../constants';
import { offerFor } from '../../lib/offerRule';
import { catalogItem } from '../../lib/tierCatalog';
import { openPaySheet } from '../lib/paySheetBus';
import { tierAccusative, tierInRu } from '../lib/ruDeclension';

export const CHAT_ABOUT = catalogItem('chat').about;

export default function ChatOfferSheet({ tier, onClose }) {
  const o = offerFor('chat', tier || 'free');
  const id = o?.primary;

  const buy = () => {
    onClose();
    openPaySheet({
      focus: id,
      alt: o?.alt,
      feature: 'chat',
      returnTo: { path: '/app/feed', kind: 'chat', feature: 'chat' },
    });
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Чат с Аристеей"
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'flex-end' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', background: 'var(--bg-page)', borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0',
          padding: '18px 16px calc(18px + env(safe-area-inset-bottom))', display: 'flex', flexDirection: 'column', gap: 12,
        }}
      >
        <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
          Чат с Аристеей
        </p>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>{CHAT_ABOUT}</p>
        {id && (
          <>
            <p style={{ margin: 0, fontSize: 14, color: 'var(--text-primary)' }}>
              Открывается на {tierInRu(TIER_NAMES[id])} · {tierPriceLabel(id)} в месяц
            </p>
            <button type="button" className="mobile-btn-primary" style={{ height: 44, fontSize: 14 }} onClick={buy}>
              Оформить {tierAccusative(TIER_NAMES[id])}
            </button>
          </>
        )}
        <button type="button" className="mobile-link" style={{ alignSelf: 'center' }} onClick={onClose}>
          Не сейчас
        </button>
      </div>
    </div>
  );
}
