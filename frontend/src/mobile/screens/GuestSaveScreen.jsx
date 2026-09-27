/**
 * GuestSaveScreen.jsx — третья вкладка у гостя вместо «Ещё»: зачем аккаунт и
 * как сохранить карту. Сюда же ведут действия, которым нужен аккаунт
 * (lib/signupPrompt.js) — тогда сверху причина.
 *
 * После входа или регистрации карта гостя переходит на аккаунт той же строкой
 * (ClaimGate в MobileApp.jsx) — вводить данные заново не нужно.
 */

import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import ThemeToggle from '../components/ThemeToggle';
import { openSupport } from '../lib/supportBus';
import { SIGNUP_REASONS } from '../lib/signupPrompt';

export default function GuestSaveScreen() {
  const navigate = useNavigate();
  const reason = SIGNUP_REASONS[useLocation().state?.signupReason];

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>
        Сохрани карту
      </h1>
      {reason && (
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: 'var(--text-primary)' }}>{reason}</p>
      )}
      <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
        Сейчас карта хранится 7 дней и только на этом телефоне. С аккаунтом она
        останется с тобой, и откроются разбор карты, чат с Аристеей, уведомления
        о прогнозе и вход с другого устройства. Данные вводить заново не нужно.
      </p>
      <button type="button" className="mobile-btn-primary" onClick={() => navigate('/register')}>
        Зарегистрироваться
      </button>
      <button type="button" className="mobile-link" style={{ alignSelf: 'center' }} onClick={() => navigate('/login')}>
        У меня уже есть аккаунт
      </button>
      <ThemeToggle />
      <button type="button" className="mobile-link" style={{ alignSelf: 'flex-start', fontSize: 13 }} onClick={() => openSupport({ screen: 'guest' })}>
        Написать в поддержку
      </button>
    </div>
  );
}
