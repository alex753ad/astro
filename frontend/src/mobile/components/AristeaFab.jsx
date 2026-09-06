/**
 * AristeaFab.jsx — кнопка чата с Аристеей, общая для приложения
 * (SPEC_FEED_SCREEN.md, SPEC_CHART_SCREEN.md). Живёт в TabShell.jsx, не на
 * каждом экране по отдельности — видна на «Ленте» и «Карте», не на «Ещё»
 * (видимостью управляет TabShell через проп `visible`).
 *
 * Гейт по тарифу — `useChatAccess()`, источник сервер. На Лире/Орионе тап
 * открывает заглушку (AristeaChatStub — сам чат не подключён). На
 * free/Веге кнопка визуально приглушена и несёт значок замка вместо ✦; тап
 * не ведёт на оплату — переключает на вкладку «Ещё» с подсветкой блока
 * тарифа (там уже есть кнопка «Тарифы»).
 *
 * ⚠️ `position: fixed`, не `absolute`. Первая версия была `absolute`
 * внутри дополнительной `position:relative` обёртки вокруг скроллера —
 * это добавляло лишний уровень вложенности в цепочку, через которую
 * `ChartSheet.jsx` считает свою высоту в `%` (45%, §5), и подсказку под
 * колесом на «Карте» перекрывало шторкой (регресс 06.09.2026, см.
 * TabShell.jsx). `fixed` позиционируется от viewport и не участвует в
 * раскладке скроллера вообще — `bottomOffset` приходит из TabShell.jsx,
 * измеренной высоты `TabBar`, а не магическим числом.
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useChatAccess from '../lib/useChatAccess';
import AristeaChatStub from './AristeaChatStub';

export default function AristeaFab({ visible, bottomOffset }) {
  const hasAccess = useChatAccess();
  const navigate = useNavigate();
  const [stubOpen, setStubOpen] = useState(false);

  if (!visible) return null;

  const onClick = () => {
    if (hasAccess) {
      setStubOpen(true);
    } else {
      navigate('/app/more', { replace: true, state: { highlightTier: true } });
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={onClick}
        aria-label={hasAccess ? 'Чат с Аристеей' : 'Чат с Аристеей — доступен на Лире и Орионе'}
        style={{
          position: 'fixed',
          right: 'calc(16px + env(safe-area-inset-right))',
          bottom: bottomOffset,
          width: 52,
          height: 52,
          borderRadius: '50%',
          border: 'none',
          background: hasAccess ? 'var(--accent)' : 'var(--border)',
          color: hasAccess ? '#fff' : 'var(--text-secondary)',
          fontSize: 20,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: hasAccess ? '0 8px 24px rgba(139,92,246,0.32)' : 'none',
          zIndex: 5,
        }}
      >
        {hasAccess ? (
          '✦'
        ) : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="5" y="11" width="14" height="9" rx="2" />
            <path d="M8 11V8a4 4 0 0 1 8 0v3" />
          </svg>
        )}
      </button>

      {stubOpen && <AristeaChatStub onClose={() => setStubOpen(false)} />}
    </>
  );
}
