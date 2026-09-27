/**
 * SupportLink.jsx — строка «Написать в поддержку» под сообщением об ошибке.
 * Открывает общий лист (SupportSheet.jsx) и передаёт, где и какую ошибку
 * человек видел; текст ошибки чистится там же (supportContext.js).
 */

import React from 'react';
import { openSupport } from '../lib/supportBus';

export default function SupportLink({ screen, error, style }) {
  return (
    <button
      type="button"
      className="mobile-link"
      onClick={() => openSupport({ screen, error })}
      style={{ fontSize: 13, color: 'var(--text-secondary)', alignSelf: 'center', ...style }}
    >
      Написать в поддержку
    </button>
  );
}
