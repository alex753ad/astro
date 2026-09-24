/**
 * chartCreateRules.test.js — правила формы и разбор трёх отказов
 * `POST /chart/calculate`.
 *
 * Живых запросов здесь нет и быть не может: успешный вызов создаёт
 * настоящую карту в базе и расходует слот тарифа (`profiles_limit`, у free
 * их два). Ошибки собираются вручную — ровно в той форме, в какой их
 * строит `createChart` (`lib/chartApi.js`): `Error` с полями `status`
 * (код), `detail` (сырое тело ответа) и `message` (текст для человека).
 *
 * Тела 400/403 взяты дословно из `backend/main.py` — если тексты или форма
 * `detail` там поменяются, эти тесты покажут, что разбор на клиенте
 * разошёлся с сервером.
 */
import { describe, expect, it } from 'vitest';
import {
  buildChartPayload,
  describeCreateError,
  validateBirthForm,
} from './chartCreateRules';

/** Как отказ строит createChart: message = detail, если он строка. */
function apiError(status, body) {
  const detail = body?.detail;
  const message = typeof detail === 'string' && detail ? detail : 'Bad Request';
  const err = new Error(message);
  err.status = status;
  err.detail = body;
  return err;
}

const TODAY = '2026-09-08';
const ok = {
  name: 'Александр',
  birthDate: '1996-05-28',
  birthTime: '11:50',
  timeUnknown: false,
  birthPlace: 'Москва, Россия',
};

describe('validateBirthForm', () => {
  it('пропускает заполненную форму', () => {
    expect(validateBirthForm(ok, TODAY)).toBeNull();
  });

  it('ловит дату: пустую, до 1900 и в будущем', () => {
    expect(validateBirthForm({ ...ok, birthDate: '' }, TODAY))
      .toEqual({ field: 'birthDate', text: 'Укажи дату рождения' });
    expect(validateBirthForm({ ...ok, birthDate: '1899-12-31' }, TODAY).field).toBe('birthDate');
    expect(validateBirthForm({ ...ok, birthDate: '2026-09-09' }, TODAY).text)
      .toBe('Дата рождения не может быть в будущем');
  });

  it('различает «дату не трогали» и «дату не дописали»', () => {
    // Поле с маской отдаёт пустой ISO в обоих случаях, и без birthDateInput
    // человек с набранным «28.05.19» получил бы «Укажите дату рождения» —
    // при заполненном на вид поле.
    expect(validateBirthForm({ ...ok, birthDate: '', birthDateInput: '' }, TODAY).text)
      .toBe('Укажи дату рождения');
    expect(validateBirthForm({ ...ok, birthDate: '', birthDateInput: '28.05.19' }, TODAY))
      .toEqual({ field: 'birthDate', text: 'Дата не дописана — нужны день, месяц и год' });
  });

  it('сегодняшняя дата — не будущее', () => {
    expect(validateBirthForm({ ...ok, birthDate: TODAY }, TODAY)).toBeNull();
  });

  it('пустое время без отметки «неизвестно» — ошибка, а не молчаливый полдень', () => {
    // Сервер принял бы null и посчитал бы карту на полдень с условными
    // домами: человек получил бы другую карту, не заметив этого.
    expect(validateBirthForm({ ...ok, birthTime: '' }, TODAY))
      .toEqual({ field: 'birthTime', text: 'Укажи время или отметь, что оно неизвестно' });
    expect(validateBirthForm({ ...ok, birthTime: '', timeUnknown: true }, TODAY)).toBeNull();
  });

  it('ловит место: короткое и с запрещёнными символами', () => {
    expect(validateBirthForm({ ...ok, birthPlace: 'М' }, TODAY).field).toBe('birthPlace');
    expect(validateBirthForm({ ...ok, birthPlace: 'Москва <b>' }, TODAY).text)
      .toBe('Название места содержит недопустимые символы');
  });

  it('ловит слишком длинное имя', () => {
    expect(validateBirthForm({ ...ok, name: 'я'.repeat(101) }, TODAY).field).toBe('name');
    expect(validateBirthForm({ ...ok, name: 'я'.repeat(100) }, TODAY)).toBeNull();
  });
});

describe('buildChartPayload', () => {
  it('обрезает пробелы, а пустое имя шлёт как null', () => {
    expect(buildChartPayload({ ...ok, name: '  ', birthPlace: '  Москва  ' }))
      .toEqual({ name: null, birth_date: '1996-05-28', birth_time: '11:50', birth_place: 'Москва' });
  });

  it('при «время неизвестно» шлёт null, даже если в поле что-то осталось', () => {
    expect(buildChartPayload({ ...ok, timeUnknown: true }).birth_time).toBeNull();
  });

  it('house_system не передаёт вовсе — умолчание сервера', () => {
    expect(buildChartPayload(ok)).not.toHaveProperty('house_system');
  });
});

describe('describeCreateError — 400 ambiguous_time', () => {
  // main.py: detail — объект, а не строка.
  const err = apiError(400, {
    detail: {
      message: 'Время 02:30 не существует: перевод часов.',
      options: ['01:30', '03:30'],
      type: 'ambiguous_time',
    },
  });

  it('это отдельная ветка с вариантами, а не текст ошибки', () => {
    const d = describeCreateError(err);
    expect(d.kind).toBe('ambiguous-time');
    expect(d.options).toEqual(['01:30', '03:30']);
    expect(d.text).toBe('Время 02:30 не существует: перевод часов.');
    // Ошибку у поля не показываем: время человек заполнил правильно.
    expect(d.field).toBeNull();
  });
});

describe('describeCreateError — 400 геокодинга', () => {
  const err = apiError(400, { detail: 'Место не найдено: Хххх. Уточните название.' });

  it('относится к полю места и несёт текст сервера', () => {
    const d = describeCreateError(err);
    expect(d.kind).toBe('place');
    expect(d.field).toBe('birthPlace');
    expect(d.text).toBe('Место не найдено: Хххх. Уточните название.');
    expect(d.options).toEqual([]);
  });
});

describe('describeCreateError — 403 лимита карт', () => {
  // Копия настоящего текста сервера (main.py). Адреса страницы в нём нет с
  // 08.09.2026: в приложении такой страницы не существует, а переход даёт
  // кнопка «Открыть тарифы» рядом (showPricing ниже). Разбор от текста не
  // зависит — вид отказа определяет код 403, — но фикстура обязана
  // оставаться правдой, иначе следующий читающий решит, что адрес там есть.
  const serverText = 'Достигнут лимит сохранённых карт (2) для тарифа Бесплатный. '
    + 'Удали ненужную карту, чтобы освободить место, или перейди на старший тариф.';
  const err = apiError(403, { detail: serverText });

  it('показывает текст сервера дословно и предлагает тарифы', () => {
    const d = describeCreateError(err);
    expect(d.kind).toBe('limit');
    expect(d.text).toBe(serverText);
    expect(d.showPricing).toBe(true);
  });

  it('своего числа слотов не сочиняет', () => {
    // Второй копии тарифных чисел в клиенте нет — только текст сервера.
    expect(describeCreateError(apiError(403, { detail: '' })).text)
      .toBe('Достигнут лимит сохранённых карт для твоего тарифа.');
  });
});

describe('describeCreateError — остальное', () => {
  it('429 объясняет, что делать', () => {
    expect(describeCreateError(apiError(429, {})).kind).toBe('rate');
  });

  it('сетевой сбой без статуса — текст сообщения', () => {
    const err = new Error('Сервер не отвечает. Проверь связь и попробуй ещё раз.');
    const d = describeCreateError(err);
    expect(d.kind).toBe('unknown');
    expect(d.text).toBe('Сервер не отвечает. Проверь связь и попробуй ещё раз.');
    expect(d.showPricing).toBe(false);
  });
});
