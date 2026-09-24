/**
 * RegisterScreen.jsx — регистрация в приложении: два шага, OTP на почту.
 *
 * До 07.09.2026 здесь была заглушка. Причина, по которой её нельзя было
 * заменить «короткой формой»: боевая регистрация двухшаговая, а
 * `useAuth().register()` зовёт legacy-ручку `/register`, закрытую в проде
 * (404 вне debug/testing) и не принимающую ни `consent`, ни `name`. Полный
 * разбор контракта — REGISTER_API_RECON.md.
 *
 * ⚠️ Запросы идут через `useAuth().sendRegisterCode` / `verifyRegisterCode`,
 * то есть через `apiFetch`, а НЕ голым `fetch`, как это делает `AuthModal.jsx`
 * на вебе. Копирование веб-кода сюда дало бы регистрацию, которая выглядит
 * исправной, но молча разлогинивает человека через час: без заголовка
 * `X-Client-Platform` сервер не кладёт `refresh_token` в тело, а куку webview
 * не получает (§3.1-3.2 разведки).
 *
 * ⚠️ Ответ шага 2 обрабатывает `applyTokenResponse` внутри
 * `verifyRegisterCode` — она же сохраняет refresh в нативное хранилище.
 * Раскладывать токены руками нельзя по той же причине.
 *
 * Правила формы и разбор ошибок — `lib/registerRules.js`: там они покрыты
 * тестами, здесь остаётся вёрстка и переходы между шагами.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import useAuth from '../../hooks/useAuth.jsx';
import PasswordInput from '../../components/PasswordInput.jsx';
import {
  RU_EMAIL_DOMAINS_HINT,
  describeSendCodeError,
  describeVerifyError,
  normalizeOtpInput,
  validateOtpCode,
  validateRegisterForm,
} from '../lib/registerRules';

// Пауза повторной отправки на стороне сервера — 60 секунд по адресу
// (OTP_RESEND_TTL). Отсчёт здесь только показывает её человеку; источник
// истины — сервер, и при расхождении он ответит 429, который мы покажем.
const RESEND_SECONDS = 60;

function Field({ id, label, hint, children }) {
  return (
    <div>
      <label className="mobile-label" htmlFor={id}>{label}</label>
      {children}
      {hint && (
        <p style={{ margin: '6px 0 0', fontSize: 11, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
          {hint}
        </p>
      )}
    </div>
  );
}

function ErrorText({ children }) {
  if (!children) return null;
  return (
    <div style={{ color: 'var(--color-danger)', fontSize: 13, lineHeight: 1.5 }}>
      {children}
    </div>
  );
}

export default function RegisterScreen() {
  const { sendRegisterCode, verifyRegisterCode } = useAuth();
  const navigate = useNavigate();

  // 'form' — данные и согласие, 'code' — ввод кода из письма.
  const [step, setStep] = useState('form');

  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [consent, setConsent] = useState(false);

  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  // Ошибки шага 1 и шага 2 держатся раздельно: ошибка ввода кода не должна
  // выглядеть как ошибка формы, и наоборот. По той же причине эти экраны не
  // используют общий `error` из useAuth.
  const [formError, setFormError] = useState('');
  const [codeError, setCodeError] = useState('');
  // Показывать ли ссылку «войти» под ошибкой: аккаунт мог быть уже создан,
  // если ответ 201 не доехал (успешный verify стирает код на сервере).
  const [offerLogin, setOfferLogin] = useState(false);

  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef(null);

  useEffect(() => () => clearInterval(timerRef.current), []);

  const startCooldown = useCallback(() => {
    clearInterval(timerRef.current);
    setCooldown(RESEND_SECONDS);
    timerRef.current = setInterval(() => {
      setCooldown((c) => {
        if (c <= 1) { clearInterval(timerRef.current); return 0; }
        return c - 1;
      });
    }, 1000);
  }, []);

  /** Шаг 1 и повторная отправка — один и тот же запрос с тем же телом. */
  const send = useCallback(async ({ resend } = {}) => {
    const invalid = validateRegisterForm({ email, password, password2, consent });
    if (invalid) { setFormError(invalid); return; }

    setBusy(true);
    (resend ? setCodeError : setFormError)('');
    setOfferLogin(false);
    try {
      await sendRegisterCode({
        email: email.trim().toLowerCase(),
        password,
        name: name.trim() || undefined,
        consent,
      });
      setStep('code');
      startCooldown();
    } catch (err) {
      const { text } = describeSendCodeError(err);
      // Повторная отправка идёт с экрана кода — там же и показываем отказ,
      // не выбрасывая человека обратно в форму (в отличие от веба).
      (resend ? setCodeError : setFormError)(text);
    } finally {
      setBusy(false);
    }
  }, [email, name, password, password2, consent, sendRegisterCode, startCooldown]);

  const verify = useCallback(async () => {
    const invalid = validateOtpCode(code);
    if (invalid) { setCodeError(invalid); setOfferLogin(false); return; }

    setBusy(true);
    setCodeError('');
    setOfferLogin(false);
    try {
      await verifyRegisterCode({ email: email.trim().toLowerCase(), code });
      // Регистрация сразу логинит: verify отдаёт ту же пару токенов, что и
      // вход. Идём в ленту (решение владельца 07.09.2026).
      navigate('/app/feed', { replace: true });
    } catch (err) {
      const described = describeVerifyError(err);
      setCodeError(described.text);
      setOfferLogin(described.offerLogin);
    } finally {
      setBusy(false);
    }
  }, [code, email, verifyRegisterCode, navigate]);

  return (
    // Как на экране входа: padding сверху/снизу даёт класс mobile-page через
    // env(safe-area-inset-*), горизонтальный — вложенный div. Инлайновый
    // padding здесь стёр бы безопасные отступы.
    <div
      className="mobile-page"
      style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
    >
      <div style={{ padding: '0 24px' }}>
        {step === 'form' ? (
          <>
            <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 26, color: 'var(--text-primary)', textAlign: 'center', margin: '0 0 24px' }}>
              Регистрация
            </h1>

            <form
              onSubmit={(e) => { e.preventDefault(); send(); }}
              style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
            >
              <Field
                id="mobile-reg-email"
                label="Почта"
                // Ограничение сервера жёсткое и до отправки формы неочевидное:
                // без этой строки первый же адрес на gmail получает 422 после
                // заполнения всех полей (решение владельца 07.09.2026).
                hint={`Принимаем почту российских сервисов: ${RU_EMAIL_DOMAINS_HINT.join(', ')}.`}
              >
                <input
                  id="mobile-reg-email"
                  className={`mobile-input${formError ? ' has-error' : ''}`}
                  type="email"
                  inputMode="email"
                  autoComplete="username"
                  autoCapitalize="none"
                  autoCorrect="off"
                  placeholder="you@yandex.ru"
                  value={email}
                  onChange={(e) => { setEmail(e.target.value); setFormError(''); }}
                  required
                />
              </Field>

              <Field id="mobile-reg-name" label="Имя (необязательно)">
                <input
                  id="mobile-reg-name"
                  className="mobile-input"
                  type="text"
                  autoComplete="name"
                  placeholder="Как к тебе обращаться"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </Field>

              <Field id="mobile-reg-password" label="Пароль" hint="Минимум 8 символов, не только цифры.">
                <PasswordInput
                  id="mobile-reg-password"
                  className={`mobile-input${formError ? ' has-error' : ''}`}
                  autoComplete="new-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); setFormError(''); }}
                  required
                />
              </Field>

              <Field id="mobile-reg-password2" label="Пароль ещё раз">
                <PasswordInput
                  id="mobile-reg-password2"
                  className={`mobile-input${formError ? ' has-error' : ''}`}
                  autoComplete="new-password"
                  placeholder="••••••••"
                  value={password2}
                  onChange={(e) => { setPassword2(e.target.value); setFormError(''); }}
                  required
                />
              </Field>

              <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginTop: 4, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => { setConsent(e.target.checked); setFormError(''); }}
                  style={{ accentColor: 'var(--accent)', width: 16, height: 16, marginTop: 2, flexShrink: 0 }}
                />
                <span style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
                  Согласен на обработку персональных данных и принимаю условия оферты
                </span>
              </label>

              <ErrorText>{formError}</ErrorText>

              <button
                type="submit"
                className="mobile-btn-primary"
                disabled={busy}
                style={{ marginTop: 12 }}
              >
                {busy ? 'Отправляю код…' : 'Получить код'}
              </button>
            </form>

            <div style={{ textAlign: 'center', marginTop: 20 }}>
              <Link to="/login" className="mobile-link">Уже есть аккаунт — войти</Link>
            </div>
          </>
        ) : (
          <>
            <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 26, color: 'var(--text-primary)', textAlign: 'center', margin: '0 0 12px' }}>
              Введи код
            </h1>
            <p style={{ margin: '0 0 24px', fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)', textAlign: 'center' }}>
              {/* Формулировка намеренно осторожная: сервер отвечает одинаково
                  и когда код отправлен, и когда адрес уже занят (антиэнумерация,
                  §1.1 разведки) — обещать «код отправлен» нельзя. */}
              Мы отправили код на <strong style={{ color: 'var(--text-primary)' }}>{email}</strong>.
              Он действителен 10 минут.
            </p>

            <form
              onSubmit={(e) => { e.preventDefault(); verify(); }}
              style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
            >
              <input
                className={`mobile-input${codeError ? ' has-error' : ''}`}
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="123456"
                value={code}
                onChange={(e) => { setCode(normalizeOtpInput(e.target.value)); setCodeError(''); setOfferLogin(false); }}
                style={{ fontSize: 26, letterSpacing: 8, textAlign: 'center', fontWeight: 700 }}
                autoFocus
              />

              <ErrorText>{codeError}</ErrorText>

              {offerLogin && (
                <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: 'var(--text-secondary)' }}>
                  {/* Успешная проверка кода стирает его на сервере, а аккаунт к
                      этому моменту уже создан. Если ответ не доехал, повтор даёт
                      «Код устарел» при живом аккаунте — без этой подсказки
                      человек в тупике (§6 п. 3 разведки). */}
                  Возможно, аккаунт уже создан.{' '}
                  <Link to="/login" className="mobile-link" style={{ fontSize: 12, verticalAlign: 'baseline' }}>
                    Войди с этой почтой и паролем
                  </Link>.
                </p>
              )}

              <button type="submit" className="mobile-btn-primary" disabled={busy} style={{ marginTop: 8 }}>
                {busy ? 'Проверяю…' : 'Подтвердить'}
              </button>
            </form>

            <div style={{ textAlign: 'center', marginTop: 18 }}>
              {cooldown > 0 ? (
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  Отправить код повторно можно через {cooldown} сек.
                </span>
              ) : (
                <button
                  type="button"
                  className="mobile-link"
                  style={{ fontSize: 12 }}
                  disabled={busy}
                  // Повторная отправка тем же телом, прямо отсюда — человек не
                  // возвращается в форму и не набирает пароль заново (в отличие
                  // от веба, где эта ссылка просто меняет режим модалки).
                  onClick={() => send({ resend: true })}
                >
                  Отправить код повторно
                </button>
              )}
            </div>

            <div style={{ textAlign: 'center', marginTop: 14 }}>
              <button
                type="button"
                className="mobile-link"
                style={{ fontSize: 12 }}
                onClick={() => { setStep('form'); setCode(''); setCodeError(''); setOfferLogin(false); }}
              >
                Изменить данные
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
