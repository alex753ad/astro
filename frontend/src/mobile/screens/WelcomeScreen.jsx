/**
 * WelcomeScreen.jsx — приветствие, три полноэкранных экрана до входа
 * (SPEC_ONBOARDING.md §3).
 *
 * Показывается один раз: маршрут выбирается в MobileApp.jsx по флагу
 * `aristea.onboarding.seen`. Вошедшему не показывается вовсе (решение
 * владельца 07.09.2026) — маршрут завёрнут в RequireGuest там же.
 *
 * ⚠️ Флаг ставится ТОЛЬКО в трёх точках выхода: «Построить карту»,
 * «У меня уже есть аккаунт» и «Пропустить». Ни при показе, ни при переходе
 * между экранами — закрывший приложение на втором экране увидит приветствие
 * снова, с первого (SPEC_ONBOARDING.md §6).
 *
 * ⚠️ Вертикальной прокрутки внутри экрана нет намеренно: текст обязан
 * помещаться целиком на самом маленьком экране. Прокрутка спрятала бы
 * кнопку под сгибом, и человек решил бы, что экран сломан. Если текст
 * перестанет помещаться — это повод править текст, а не заводить скролл
 * (п. 10 чек-листа приёмки §14).
 *
 * Сеть здесь не используется вообще: ни одного запроса, ни за текстом, ни
 * за тарифом — приветствие работает в самолётном режиме (§4).
 */

import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BIRTH_FORM_URL,
  WELCOME_BUTTONS,
  WELCOME_SCREENS,
} from '../lib/onboardingCopy';
import { WELCOME_KEY, markSeen } from '../lib/onboardingFlags';
import { openInBrowser } from '../lib/openInBrowser';

// Порог свайпа. Меньше — и обычный тап с дрожанием пальца начнёт листать;
// больше — жест перестаёт срабатывать у тех, кто ведёт коротко.
const SWIPE_MIN_PX = 48;
// Вертикальный запас: если палец ушёл вниз сильнее, чем вбок, это не свайп
// листания, а попытка прокрутки — не листаем.
const SWIPE_MAX_DRIFT = 0.8;

function Dots({ count, active }) {
  return (
    <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }} aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <span
          key={i}
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: i === active ? 'var(--accent)' : 'var(--border)',
            transition: 'background 160ms ease',
          }}
        />
      ))}
    </div>
  );
}

export default function WelcomeScreen() {
  const navigate = useNavigate();
  const [index, setIndex] = useState(0);
  const touchRef = useRef(null);

  const isLast = index === WELCOME_SCREENS.length - 1;
  const screen = WELCOME_SCREENS[index];

  const leave = (to) => {
    markSeen(WELCOME_KEY);
    navigate(to, { replace: true });
  };

  const build = () => {
    markSeen(WELCOME_KEY);
    // Форма ввода данных рождения живёт на сайте, в приложении её нет
    // (SPEC_ONBOARDING.md §2). Системный браузер, а не window.open —
    // единственная точка выхода наружу, см. lib/openInBrowser.js.
    openInBrowser(BIRTH_FORM_URL);
    // Уходим на вход, не оставаясь на приветствии: человек вернётся из
    // браузера в приложение, и приветствие, которое он уже прошёл, встретило
    // бы его снова.
    navigate('/login', { replace: true });
  };

  const onTouchStart = (e) => {
    const t = e.changedTouches[0];
    touchRef.current = { x: t.clientX, y: t.clientY };
  };

  const onTouchEnd = (e) => {
    const start = touchRef.current;
    touchRef.current = null;
    if (!start) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    if (Math.abs(dx) < SWIPE_MIN_PX) return;
    if (Math.abs(dy) > Math.abs(dx) * SWIPE_MAX_DRIFT) return;
    if (dx < 0 && !isLast) setIndex((i) => i + 1);
    if (dx > 0 && index > 0) setIndex((i) => i - 1);
  };

  return (
    <div
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        // Фон не задаётся: его рисует body (--bg-page, градиент в светлой
        // теме). Плоский var(--bg) здесь закрывал бы градиент собой.
        // Полноэкранный экран: под ним нет таб-бара, который забрал бы
        // нижний safe-area на себя (как в TabShell), поэтому отступы
        // ставятся здесь со всех четырёх сторон.
        paddingTop: 'calc(env(safe-area-inset-top) + 12px)',
        paddingBottom: 'calc(env(safe-area-inset-bottom) + 20px)',
        paddingLeft: 'calc(env(safe-area-inset-left) + 24px)',
        paddingRight: 'calc(env(safe-area-inset-right) + 24px)',
      }}
    >
      {/* «Пропустить» — ссылкой в углу, не кнопкой (§3). Класс mobile-link
          уже используется на экране входа; второй стиль ссылки не заводим. */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', flexShrink: 0 }}>
        <button
          type="button"
          className="mobile-link"
          style={{ padding: '4px 0', fontSize: 14 }}
          onClick={() => leave('/login')}
        >
          {WELCOME_BUTTONS.skip}
        </button>
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 14,
        }}
      >
        <h1
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontSize: 30,
            fontWeight: 700,
            lineHeight: 1.2,
            color: 'var(--text-primary)',
          }}
        >
          {screen.title}
        </h1>
        <p
          style={{
            margin: 0,
            fontSize: 16,
            lineHeight: 1.65,
            color: 'var(--text-secondary)',
          }}
        >
          {screen.text}
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, flexShrink: 0 }}>
        <Dots count={WELCOME_SCREENS.length} active={index} />

        {isLast ? (
          <>
            <button type="button" className="mobile-btn-primary" onClick={build}>
              {WELCOME_BUTTONS.build}
            </button>
            <button
              type="button"
              className="mobile-link"
              style={{ alignSelf: 'center', fontSize: 14 }}
              onClick={() => leave('/login')}
            >
              {WELCOME_BUTTONS.haveAccount}
            </button>
          </>
        ) : (
          <button
            type="button"
            className="mobile-btn-primary"
            onClick={() => setIndex((i) => i + 1)}
          >
            {WELCOME_BUTTONS.next}
          </button>
        )}
      </div>
    </div>
  );
}
