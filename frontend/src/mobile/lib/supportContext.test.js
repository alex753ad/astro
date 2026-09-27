/**
 * supportContext.test.js — что уходит с обращением в поддержку.
 *
 * Главное здесь — `scrubErrorText`: текст ошибки человек видит перед
 * отправкой и он же уходит владельцу, поэтому в нём не должно остаться ни
 * email, ни даты, времени и места рождения.
 */

import { describe, expect, it } from 'vitest';
import { appVersionLabel, deviceLabel, scrubErrorText } from './supportContext';

describe('scrubErrorText', () => {
  const cases = [
    ['Пользователь anna.k+1@mail.ru уже существует', 'anna.k'],
    ['Не нашли место «Нижний Новгород»', 'Новгород'],
    ['Не нашли место "Kazan, Russia"', 'Kazan'],
    ['Дата 15.03.1990 вне диапазона', '15.03'],
    ['birth_date 1990-03-15 invalid', '1990'],
    ['Родился 15 марта 1990', '15 марта'],
    ['Время 07:45 неоднозначно', '07:45'],
    ['Координаты 55.7558, 37.6173', '55.7558'],
  ];
  for (const [input, leaked] of cases) {
    it(`вырезает «${leaked}»`, () => {
      expect(scrubErrorText(input)).not.toContain(leaked);
    });
  }

  it('обычный текст ошибки не трогает', () => {
    expect(scrubErrorText('Нет сети — ничего не отправлено. Подключись и попробуй ещё раз.'))
      .toBe('Нет сети — ничего не отправлено. Подключись и попробуй ещё раз.');
  });

  it('обрезает длинное', () => {
    expect(scrubErrorText('ы'.repeat(1000)).length).toBe(300);
  });

  it('пустое — пустая строка', () => {
    expect(scrubErrorText(undefined)).toBe('');
  });
});

describe('deviceLabel', () => {
  it('модель из UA WebView', () => {
    const ua = 'Mozilla/5.0 (Linux; Android 13; SM-A515F Build/TP1A.220624.014; wv) AppleWebKit/537.36';
    expect(deviceLabel(ua)).toBe('SM-A515F, Android 13');
  });
  it('урезанный UA — только версия Android', () => {
    expect(deviceLabel('Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36')).toBe('Android 10');
  });
  it('не Android — без выдумки', () => {
    expect(deviceLabel('Mozilla/5.0 (Windows NT 10.0; Win64; x64)')).toBe('неизвестно');
  });
});

describe('appVersionLabel', () => {
  it('версия и коммит', () => {
    expect(appVersionLabel('aristea-mobile@0.1.0+abc1234')).toBe('0.1.0 (abc1234)');
  });
  it('вне сборки приложения — dev', () => {
    expect(appVersionLabel('')).toBe('dev');
  });
});
