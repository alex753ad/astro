/**
 * chartCreateRules.js — правила формы построения карты и разбор ответов
 * `POST /chart/calculate`.
 *
 * Вынесено из экрана по той же причине, что и registerRules.js: это
 * единственная часть задачи, которую можно проверить тестами без устройства
 * и без живых запросов. Живой вызов здесь дороже, чем в регистрации: каждый
 * успешный создаёт настоящую карту в базе и расходует слот тарифа
 * (`profiles_limit`, у free их всего два).
 *
 * Полный разбор — SPEC_CHART_CREATE.md §2, §4, §7, §8.
 */

import { hasDigits } from './dateMask';
import { localToday } from './feedTime';

/** Раньше этой даты эфемериды не считают (`validate_date_range`, schemas.py). */
export const MIN_BIRTH_DATE = '1900-01-01';

/**
 * ⚠️ Копия серверного набора запрещённых символов (`validate_place`,
 * `backend/schemas.py`). Осознанный второй источник — и он безопасен только
 * потому, что строже сервера быть не может: набор здесь тот же самый, а
 * расхождение в худшую сторону (клиент отбивает то, что сервер принимает)
 * даст лишь текст под полем вместо запроса. Проверка на сервере остаётся,
 * эта — чтобы человек не ждал ответа ради известного отказа.
 */
const FORBIDDEN_PLACE_CHARS = /[<>{}[\]\\]/;

const MAX_NAME_LENGTH = 100;

/**
 * Проверка формы до запроса.
 *
 * Возвращает `{ field, text }` первой ошибки или `null`. Поле возвращается
 * вместе с текстом, потому что показывать ошибку надо У ТОГО поля, к
 * которому она относится: общая красная строка внизу формы из пяти полей не
 * говорит человеку, что именно править.
 *
 * ⚠️ Пустое время при выключенном переключателе — ошибка, а не «время
 * неизвестно». Сервер принял бы `null` и посчитал карту на полдень с
 * условными домами (`time_unknown`), то есть человек молча получил бы
 * другую карту вместо той, что просил. Отметить незнание времени он должен
 * сам и явно.
 *
 * ⚠️ `birthDateInput` — то, что человек НАБРАЛ в поле («28.05.19»), в
 * отличие от `birthDate` — собранной даты в ISO. Их два, потому что у
 * «поле не трогали» и «набрано наполовину» разный текст ошибки, а
 * `displayToIso` для обоих отдаёт пустую строку. Появилось вместе с
 * маской: у прежнего системного пикера недособранной даты быть не могло —
 * он либо отдавал полную, либо ничего.
 */
export function validateBirthForm(form, today = localToday()) {
  const name = (form?.name ?? '').trim();
  const date = form?.birthDate ?? '';
  const time = form?.birthTime ?? '';
  const place = (form?.birthPlace ?? '').trim();

  if (name.length > MAX_NAME_LENGTH) {
    return { field: 'name', text: `Имя не длиннее ${MAX_NAME_LENGTH} символов` };
  }

  if (!date) {
    return hasDigits(form?.birthDateInput)
      ? { field: 'birthDate', text: 'Дата не дописана — нужны день, месяц и год' }
      : { field: 'birthDate', text: 'Укажи дату рождения' };
  }
  if (date < MIN_BIRTH_DATE) {
    return { field: 'birthDate', text: 'Даты до 1900 года не поддерживаются' };
  }
  if (date > today) {
    return { field: 'birthDate', text: 'Дата рождения не может быть в будущем' };
  }

  if (!form?.timeUnknown) {
    if (!time) {
      return { field: 'birthTime', text: 'Укажи время или отметь, что оно неизвестно' };
    }
    if (!/^\d{2}:\d{2}$/.test(time)) {
      return { field: 'birthTime', text: 'Время в формате ЧЧ:ММ' };
    }
  }

  if (place.length < 2) return { field: 'birthPlace', text: 'Укажи место рождения' };
  if (FORBIDDEN_PLACE_CHARS.test(place)) {
    return { field: 'birthPlace', text: 'Название места содержит недопустимые символы' };
  }

  return null;
}

/**
 * Форма → тело запроса.
 *
 * `house_system` не передаётся вовсе — приложение его не спрашивает, у
 * сервера умолчание `placidus` (SPEC_CHART_CREATE.md §2.2). Пустое имя
 * уходит как `null`, а не пустой строкой: поле необязательное, и пустая
 * строка записалась бы в базу как имя карты.
 */
export function buildChartPayload(form) {
  const name = (form?.name ?? '').trim();
  return {
    name: name || null,
    birth_date: form?.birthDate ?? '',
    birth_time: form?.timeUnknown ? null : (form?.birthTime || null),
    birth_place: (form?.birthPlace ?? '').trim(),
  };
}

// ── Разбор ответов ────────────────────────────────────────────────────────

/**
 * Разбирает отказ `POST /chart/calculate`.
 *
 * @returns {{ kind: 'ambiguous-time'|'place'|'limit'|'rate'|'validation'|'unknown',
 *             text: string, field: string|null, options: string[],
 *             showPricing: boolean }}
 *
 * ⚠️ У 400 два РАЗНЫХ смысла, и различать их надо по форме `detail`, а не по
 * коду ответа:
 *
 *   • `detail` объектом с `type: "ambiguous_time"` — час рождения попал в
 *     перевод часов (`main.py`, `AmbiguousTimeError`). Это единственный
 *     случай, где человек без подсказки не поймёт, что делать: время он
 *     заполнил и, на его взгляд, правильно. Поэтому отдельный вид с
 *     `options` — экран показывает их кнопками, а не красной строкой
 *     (SPEC_CHART_CREATE.md §7);
 *   • `detail` строкой — геокодинг не нашёл место. Ошибка относится к полю
 *     места, туда её и возвращаем.
 *
 * 403 — исчерпаны слоты карт тарифа. Текст берём серверный целиком и своего
 * не сочиняем: в нём уже стоит число слотов, а второй копии тарифных чисел
 * в клиенте заводить нельзя — в этом проекте они расходились не раз.
 */
export function describeCreateError(err) {
  const status = err?.status;
  const detail = err?.detail?.detail;
  const message = typeof err?.message === 'string' ? err.message : '';
  const blank = { field: null, options: [], showPricing: false };

  if (status === 400 && detail && typeof detail === 'object' && detail.type === 'ambiguous_time') {
    return {
      ...blank,
      kind: 'ambiguous-time',
      text: detail.message || 'В эту ночь переводили часы — уточни время.',
      options: Array.isArray(detail.options) ? detail.options : [],
    };
  }

  if (status === 400) {
    return {
      ...blank,
      kind: 'place',
      field: 'birthPlace',
      text: (typeof detail === 'string' && detail) || message
        || 'Не удалось определить место. Попробуй написать его иначе.',
    };
  }

  if (status === 403) {
    return {
      ...blank,
      kind: 'limit',
      // Без запасного `message`, в отличие от ветки места: у 403 текст
      // сервера либо есть, либо запрос пришёл не с нашей ручки — и тогда в
      // `message` лежит statusText «Forbidden», который человеку показывать
      // нельзя.
      text: (typeof detail === 'string' && detail)
        || 'Достигнут лимит сохранённых карт для твоего тарифа.',
      showPricing: true,
    };
  }

  if (status === 429) {
    return { ...blank, kind: 'rate', text: 'Слишком часто. Попробуй через минуту.' };
  }

  if (status === 422) {
    return { ...blank, kind: 'validation', text: message || 'Проверь правильность заполнения полей.' };
  }

  return { ...blank, kind: 'unknown', text: message || 'Не удалось построить карту. Попробуй ещё раз.' };
}
