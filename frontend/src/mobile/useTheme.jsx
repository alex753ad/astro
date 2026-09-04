/**
 * useTheme.jsx — тема мобильного приложения: светлая по умолчанию, тёмная —
 * полноценная альтернатива, переключается и запоминается между запусками.
 *
 * Обратное вебу умолчание — раздел «Принципы» DESIGN_SYSTEM.md: строка
 * «Тёмная тема — основная» относится к вебу, для мобильного приложения
 * умолчание обратное. Токены обеих тем те же (§2 документа), только базовый
 * `:root` в mobile.css держит светлые значения вместо тёмных — сам механизм
 * переключения (класс `.dark` на корневом элементе) скопирован с веба
 * (App.jsx, useDarkMode) один в один, чтобы в проекте не было двух разных
 * способов переключать тему.
 *
 * Персист — localStorage, тот же способ, что у access-токена и пользователя
 * (hooks/useAuth.jsx): это не секрет, в отличие от refresh-токена, которому
 * потребовалось нативное Preferences (см. api/authTransport.js) — обычная
 * настройка интерфейса хранится там же, где и остальное состояние экрана.
 *
 * Ключ хранилища — `astrea_theme`, буквально тот же, что использует веб
 * (App.jsx, useDarkMode). Коллизии нет: веб и приложение — разные origin
 * (https://www.aristeatime.ru и https://localhost), у каждого свой
 * localStorage. Ключ оставлен тем же намеренно — это один и тот же концепт,
 * заведение отдельного имени добавило бы путаницы без единой причины.
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const THEME_KEY = 'astrea_theme';
const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [dark, setDark] = useState(() => {
    try {
      const stored = localStorage.getItem(THEME_KEY);
      if (stored) return stored === 'dark';
    } catch {
      // localStorage недоступен (приватный режим и т.п.) — тихо падаем на умолчание ниже.
    }
    return false; // мобильное умолчание — светлая тема
  });

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    try {
      localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light');
    } catch {
      // см. выше — потеря персиста не должна ронять переключение в рамках сессии
    }
  }, [dark]);

  const toggle = useCallback(() => setDark((d) => !d), []);

  return (
    <ThemeContext.Provider value={{ dark, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export default function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within <ThemeProvider>');
  }
  return ctx;
}
