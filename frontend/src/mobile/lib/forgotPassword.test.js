import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { validateNewPassword } from '../screens/ForgotPasswordScreen';

const read = (p) => readFileSync(fileURLToPath(new URL(p, import.meta.url)), 'utf-8');

describe('сброс пароля кодом в приложении', () => {
  it('правила нового пароля — как у регистрации', () => {
    expect(validateNewPassword('', '')).toBeTruthy();
    expect(validateNewPassword('1234567', '1234567')).toMatch(/8/);
    expect(validateNewPassword('12345678', '12345678')).toMatch(/цифр/);
    expect(validateNewPassword('abcdefg1', 'abcdefg2')).toMatch(/не совпадают/);
    expect(validateNewPassword('abcdefg1', 'abcdefg1')).toBeNull();
  });

  it('экран входа ведёт на сброс в приложении, а не в браузер', () => {
    const login = read('../screens/LoginScreen.jsx');
    expect(login).toMatch(/to="\/forgot"/);
    expect(read('../MobileApp.jsx')).toMatch(/path="\/forgot"/);
    expect(read('../screens/ForgotPasswordScreen.jsx')).not.toMatch(/openInBrowser/);
  });

  it('текст первого шага не выдаёт, есть ли такая почта', () => {
    expect(read('../screens/ForgotPasswordScreen.jsx')).toMatch(/Если аккаунт с почтой/);
  });
});
