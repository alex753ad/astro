/**
 * Один системный вызов «Поделиться»/«Открыть» за раз на всё приложение.
 *
 * Share.share держит промис, пока системный лист открыт, и второй вызов
 * плагин отклоняет английским «Can't share while sharing is in progress».
 * Повторное нажатие в это время — не ошибка, а ничего: once возвращает false,
 * экран молчит. Флаг общий для PDF (pdfApi.js) и карточки дня (storyCard.js)
 * намеренно: лист в системе один, кто бы его ни открыл.
 */
let inFlight = false;

export async function once(fn) {
  if (inFlight) return false;
  inFlight = true;
  try {
    await fn();
    return true;
  } finally {
    inFlight = false;
  }
}
