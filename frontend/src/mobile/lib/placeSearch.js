/**
 * placeSearch.js — подсказки городов для поля «место рождения».
 *
 * ⚠️ Это УКРАШЕНИЕ, а не часть расчёта, и форма обязана работать без него
 * (SPEC_CHART_CREATE.md §5). Координаты в запрос не попадают вообще:
 * `POST /chart/calculate` их из тела не принимает и геокодирует строку
 * `birth_place` сам (CLAUDE.md, «координаты из тела не принимает»). Отсюда
 * из ответа Nominatim здесь читается только текст — `lat`/`lon` не
 * трогаются намеренно, чтобы следующий читающий не завёл вторую, неверную
 * дорогу к координатам.
 *
 * ⚠️ Запрос уходит из webview с origin `https://localhost` и на устройстве
 * НЕ ПРОВЕРЯЛСЯ ни разу; политика Nominatim к тому же требует
 * опознаваемого User-Agent, которого webview не даёт. Поэтому любой сбой
 * гасится пустым списком, а не ошибкой на экране: показывать человеку
 * отказ подсказчика, когда он может просто дописать строку руками, значит
 * пугать его тем, что ни на что не влияет. Если подсказки не заведутся на
 * приёмке — перестать звать эту функцию, форма от этого не изменится.
 *
 * Копия `nominatimSearch` из `components/BirthForm.jsx` (там функция
 * модуль-локальная и не экспортируется): вытаскивать её оттуда значило бы
 * править файл веба ради мобильного экрана.
 */

const ENDPOINT = 'https://nominatim.openstreetmap.org/search';

/** Ниже трёх символов не ищем — Nominatim на таких запросах отдаёт мусор. */
export const MIN_QUERY_LENGTH = 3;

/**
 * @returns {Promise<Array<{ display: string, short: string }>>} — пустой
 * массив при любом сбое, включая отсутствие сети.
 */
export async function searchPlaces(query) {
  if (!query || query.trim().length < MIN_QUERY_LENGTH) return [];
  try {
    const url = `${ENDPOINT}?q=${encodeURIComponent(query)}`
      + '&format=json&limit=5&addressdetails=1&accept-language=ru';
    const resp = await fetch(url, { headers: { 'Accept-Language': 'ru,en' } });
    if (!resp.ok) return [];
    const data = await resp.json();
    if (!Array.isArray(data)) return [];
    return data.map((d) => ({
      display: d.display_name,
      short: [d.address?.city || d.address?.town || d.address?.village, d.address?.country]
        .filter(Boolean).join(', '),
    })).filter((s) => s.display);
  } catch {
    return [];
  }
}
