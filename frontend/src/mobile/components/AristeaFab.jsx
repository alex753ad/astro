/**
 * AristeaFab.jsx — кнопка чата с Аристеей, общая для приложения
 * (SPEC_FEED_SCREEN.md, SPEC_CHART_SCREEN.md). Живёт в TabShell.jsx, не на
 * каждом экране по отдельности — видна на «Ленте» и «Карте», не на «Ещё»
 * (видимостью управляет TabShell через проп `visible`).
 *
 * Гейт по тарифу — `useChatAccess()`, источник сервер. На Лире/Орионе тап
 * открывает чат (AristeaChat.jsx). На free/Веге кнопка визуально приглушена
 * и несёт значок замка вместо ✦; тап не ведёт на оплату — переключает на
 * вкладку «Ещё» с подсветкой блока тарифа (там уже есть кнопка «Тарифы»).
 * Это поведение free/Веги оставлено как было, решение владельца 09.09.2026.
 *
 * ⚠️ `chart` приходит СВЕРХУ, от TabShell, а не берётся здесь основной
 * картой: чат обязан открыться по той карте, которую человек видит на
 * экране, с которого нажал кнопку. У «Ленты» и «Карты» они могут быть
 * разными (SPEC_CHART_CREATE.md §11), и своя `resolvePrimaryChartId` здесь
 * дала бы «Ленте» правильную карту, а «Карте» — чужую.
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
import AristeaChat from './AristeaChat';

export default function AristeaFab({ visible, bottomOffset, chart, innerRef }) {
  const hasAccess = useChatAccess();
  const navigate = useNavigate();
  const [chatOpen, setChatOpen] = useState(false);

  if (!visible) return null;

  const onClick = () => {
    if (hasAccess) {
      setChatOpen(true);
    } else {
      navigate('/app/more', { replace: true, state: { highlightTier: true } });
    }
  };

  return (
    <>
      <button
        ref={innerRef}
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
          boxShadow: hasAccess ? '0 8px 24px rgba(var(--accent-rgb), 0.32)' : 'none',
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

      {chatOpen && <AristeaChat chart={chart} onClose={() => setChatOpen(false)} />}
    </>
  );
}
