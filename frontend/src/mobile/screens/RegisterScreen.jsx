/**
 * RegisterScreen.jsx — заглушка, а не второй функциональный экран.
 *
 * Задание прямо говорит: экран входа — «единственный экран с настоящим
 * содержимым в этом задании». Ссылка на регистрацию с LoginScreen обязана
 * вести куда-то настоящее (не в никуда), поэтому маршрут есть, но экран за
 * ним — заглушка, как и три вкладки таб-бара.
 *
 * Почему не полноценная форма: боевая регистрация — двухшаговый OTP-флоу
 * (send-code → verify), см. AuthModal.jsx на вебе; useAuth().register()
 * вызывает register_legacy, который в проде закрыт (404 вне debug/testing,
 * backend/auth/router.py). Реализовать здесь короткую форму — значит либо
 * молча звать неработающую в проде ручку, либо тащить весь OTP-экран из
 * AuthModal.jsx, что уже не «заглушка» и не то, что просили в этом заходе.
 */

import React from 'react';
import { Link } from 'react-router-dom';

export default function RegisterScreen() {
  return (
    <div
      className="mobile-page"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 20,
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 700,
          fontSize: 22,
          color: 'var(--text-primary)',
        }}
      >
        Регистрация
      </span>
      <Link to="/login" className="mobile-link">
        Назад ко входу
      </Link>
    </div>
  );
}
