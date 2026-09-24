/**
 * jwt.js — срок жизни access-токена, прочитанный на клиенте.
 *
 * Общий файл для веба и мобильного клиента (по образцу sectionStream.js и
 * mobile/lib/ruDeclension.js): читателей уже двое — hooks/useAuth.jsx
 * (планирует обновление заранее) и api/client.js (не отправляет запрос с
 * заведомо мёртвым токеном). Второй такой парсер, скопированный в новый
 * файл, — это ровно тот класс дефекта, который в этом проекте уже расходился
 * не раз.
 *
 * ⚠️ Это НЕ проверка подлинности. Подпись здесь не проверяется и проверена
 * быть не может — ключ на сервере. Значение одно: не тратить запрос (и место
 * в очереди лимитера) на токен, срок которого уже вышел по его же claim'у.
 * Решение о доступе всегда за сервером.
 */

function parseJwtPayload(token) {
  try {
    return JSON.parse(atob(token.split('.')[1]));
  } catch {
    return null;
  }
}

/** Момент истечения в миллисекундах; 0 — если срок прочитать не удалось. */
export function tokenExpiresAt(token) {
  const payload = parseJwtPayload(token);
  return payload?.exp ? payload.exp * 1000 : 0;
}

/**
 * Токен заведомо мёртв и запрос с ним обречён на 401.
 *
 * Нечитаемый токен (0 из tokenExpiresAt) НЕ считается протухшим намеренно:
 * мы не знаем, что это, и подменять собой сервер на догадке нельзя — пусть
 * ответит он. Иначе любой формат токена, который мы не разобрали, молча
 * превратился бы в вечное обновление сессии.
 */
export function isTokenExpired(token, now = Date.now()) {
  const expiresAt = tokenExpiresAt(token);
  return expiresAt > 0 && now >= expiresAt;
}

/**
 * Чей токен — claim `sub` (id пользователя) или null.
 *
 * Нужен кэшу приложения (mobile/lib/offlineCache.js): сохранённое без сети
 * показывается только тому, кто его сохранил. Подпись не проверяется — см.
 * шапку файла: это не доступ, а выбор, чьи данные достать с диска.
 */
export function tokenSubject(token) {
  const sub = token ? parseJwtPayload(token)?.sub : null;
  return sub ? String(sub) : null;
}
