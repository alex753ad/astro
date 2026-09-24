/**
 * registerRules.test.js — разбор ответов обеих OTP-ручек и проверка формы.
 *
 * Живых запросов здесь нет и быть не может: каждый успешный вызов боевых
 * ручек создаёт настоящий аккаунт и отправляет настоящее письмо. Поэтому
 * ошибки собираются вручную — ровно в той форме, в какой их отдаёт
 * `apiFetch` (`hooks/useAuth.jsx`): `ApiError` с полями `status`, `message`
 * (уже склеенный и очищенный от «Value error, ») и `detail` (сырое тело).
 *
 * Тексты 400 и 429 взяты дословно из backend/auth/router.py — если там их
 * поменяют, эти тесты покажут, что разбор на клиенте разошёлся с сервером.
 */
import { describe, expect, it } from 'vitest';
import {
  RU_EMAIL_DOMAINS_HINT,
  describeSendCodeError,
  describeVerifyError,
  normalizeOtpInput,
  validateOtpCode,
  validateRegisterForm,
} from './registerRules';

/** Как ошибку строит apiFetch: msg = body.detail || statusText. */
function apiError(status, body) {
  const detail = body?.detail;
  const message = typeof detail === 'string' && detail ? detail : 'Too Many Requests';
  const err = new Error(message);
  err.status = status;
  err.detail = body;
  return err;
}

describe('validateRegisterForm — повторяет проверки веба', () => {
  const ok = { email: 'a@yandex.ru', password: 'Password123', password2: 'Password123', consent: true };

  it('пропускает корректную форму', () => {
    expect(validateRegisterForm(ok)).toBeNull();
  });

  it('ловит пустые поля, адрес без @, короткий и цифровой пароль', () => {
    expect(validateRegisterForm({ ...ok, email: '' })).toBe('Заполни все поля');
    expect(validateRegisterForm({ ...ok, email: 'нет-собаки' })).toBe('Введи корректный email');
    expect(validateRegisterForm({ ...ok, password: 'short', password2: 'short' }))
      .toBe('Пароль минимум 8 символов');
    expect(validateRegisterForm({ ...ok, password: '12345678', password2: '12345678' }))
      .toBe('Пароль не может состоять только из цифр');
  });

  it('ловит несовпадение паролей и отсутствие согласия', () => {
    expect(validateRegisterForm({ ...ok, password2: 'Password124' })).toBe('Пароли не совпадают');
    expect(validateRegisterForm({ ...ok, consent: false }))
      .toBe('Нужно подтвердить согласие на обработку персональных данных');
  });

  it('НЕ проверяет почтовый домен — это дело сервера', () => {
    // Клиентская проверка домена начала бы отбивать адреса, которые сервер
    // принимает, как только списки разойдутся. Список на клиенте — только
    // текст подсказки.
    expect(validateRegisterForm({ ...ok, email: 'someone@gmail.com' })).toBeNull();
  });

  it('список доменов для подсказки не пустой и содержит основные', () => {
    expect(RU_EMAIL_DOMAINS_HINT).toContain('yandex.ru');
    expect(RU_EMAIL_DOMAINS_HINT).toContain('mail.ru');
    expect(RU_EMAIL_DOMAINS_HINT).toContain('rambler.ru');
  });
});

describe('код подтверждения', () => {
  it('принимает ровно шесть цифр', () => {
    expect(validateOtpCode('123456')).toBeNull();
    expect(validateOtpCode('12345')).toBe('Введи 6-значный код');
    expect(validateOtpCode('1234567')).toBe('Введи 6-значный код');
    expect(validateOtpCode('12345a')).toBe('Введи 6-значный код');
  });

  it('ввод чистится от нецифр и обрезается до шести', () => {
    expect(normalizeOtpInput('12 34-56')).toBe('123456');
    expect(normalizeOtpInput('1234567890')).toBe('123456');
    expect(normalizeOtpInput(undefined)).toBe('');
  });
});

describe('describeSendCodeError — два разных 429', () => {
  it('наш троттл по адресу распознаётся по тексту сервера', () => {
    const err = apiError(429, { detail: 'Подожди минуту перед повторной отправкой.' });
    const out = describeSendCodeError(err);
    expect(out.kind).toBe('resend');
    expect(out.text).toMatch(/через минуту/i);
  });

  it('троттл узнаётся и в тексте сервера до перехода на «ты»', () => {
    const err = apiError(429, { detail: 'Подождите минуту перед повторной отправкой.' });
    expect(describeSendCodeError(err).kind).toBe('resend');
  });

  it('лимит по IP — другой текст, про час, а не про минуту', () => {
    // slowapi отдаёт тело другой формы (ключ error, не detail), поэтому
    // apiFetch кладёт в message statusText. Ждать тут придётся час, и
    // сказать «подождите минуту» было бы прямой ложью.
    const err = apiError(429, { error: 'Rate limit exceeded: 5 per 1 hour' });
    const out = describeSendCodeError(err);
    expect(out.kind).toBe('ip-limit');
    expect(out.text).toMatch(/час/i);
    expect(out.text).not.toMatch(/минуту/i);
  });

  it('различение не ломается, если slowapi поменяет форму тела', () => {
    // Опора — на нашу строку, а не на формат чужого пакета.
    for (const body of [{}, { detail: 'Rate limit exceeded' }, { error: 'whatever' }]) {
      expect(describeSendCodeError(apiError(429, body)).kind).toBe('ip-limit');
    }
  });

  it('422 отдаёт текст сервера как есть (префикс уже срезан apiFetch)', () => {
    const err = apiError(422, {});
    err.message = 'Принимаем только почту российских сервисов: Яндекс (yandex.ru), Mail.ru, Rambler и другие.';
    const out = describeSendCodeError(err);
    expect(out.kind).toBe('validation');
    expect(out.text).toMatch(/российских сервисов/);
  });

  it('неизвестная ошибка не оставляет человека без текста', () => {
    const err = apiError(500, {});
    err.message = '';
    expect(describeSendCodeError(err).text).toBeTruthy();
  });
});

describe('describeVerifyError — три разных 400', () => {
  it('неверный код: можно вводить дальше, вход не предлагаем', () => {
    const err = apiError(400, { detail: 'Неверный код. Осталось попыток: 4.' });
    const out = describeVerifyError(err);
    expect(out.kind).toBe('wrong-code');
    expect(out.offerLogin).toBe(false);
    expect(out.text).toMatch(/Осталось попыток: 4/);
  });

  it('код устарел: предлагаем вход — аккаунт мог быть уже создан', () => {
    // Успешный verify удаляет запись. Если ответ 201 не доехал, аккаунт
    // существует, а повтор даёт ровно этот текст.
    const err = apiError(400, { detail: 'Код устарел. Запроси новый.' });
    const out = describeVerifyError(err);
    expect(out.kind).toBe('expired');
    expect(out.offerLogin).toBe(true);
  });

  it('превышено число попыток: тоже нужен новый код и тоже предлагаем вход', () => {
    const err = apiError(400, { detail: 'Превышено число попыток. Запроси новый код.' });
    const out = describeVerifyError(err);
    expect(out.kind).toBe('expired');
    expect(out.offerLogin).toBe(true);
  });

  it('409 — аккаунт успели создать между шагами, вход предлагаем', () => {
    const err = apiError(409, { detail: 'Аккаунт с таким email уже существует.' });
    const out = describeVerifyError(err);
    expect(out.kind).toBe('exists');
    expect(out.offerLogin).toBe(true);
  });

  it('422 — код не шесть цифр', () => {
    const err = apiError(422, {});
    err.message = 'String should match pattern';
    expect(describeVerifyError(err).kind).toBe('validation');
  });

  it('текст сервера показывается человеку дословно, а не подменяется общим', () => {
    // «Осталось попыток: N» — единственный способ узнать, сколько ещё можно
    // ошибиться; подменять его общей фразой значит скрыть это от человека.
    const err = apiError(400, { detail: 'Неверный код. Осталось попыток: 1.' });
    expect(describeVerifyError(err).text).toBe('Неверный код. Осталось попыток: 1.');
  });
});
